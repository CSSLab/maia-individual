import argparse
import os
import os.path
import yaml
import sys
import glob
import gzip
import random
import multiprocessing
import shutil

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import tensorflow as tf


import backend
import backend.tf_transfer

SKIP = 32

@backend.logged_main
def main(config_path, name, collection_name, player_name, gpu, num_workers):
    output_name = os.path.join('models', collection_name, name + '.txt')

    with open(config_path) as f:
        cfg = yaml.safe_load(f.read())

    if player_name is not None:
        cfg['dataset']['name'] = player_name
    if gpu is not None:
        cfg['gpu'] = gpu

    backend.printWithDate(yaml.dump(cfg, default_flow_style=False))

    train_chunks_white, train_chunks_black = backend.tf_transfer.get_latest_chunks(os.path.join(
                cfg['dataset']['path'],
                cfg['dataset']['name'],
                'train',
                ))
    val_chunks_white, val_chunks_black = backend.tf_transfer.get_latest_chunks(os.path.join(
                cfg['dataset']['path'],
                cfg['dataset']['name'],
                'validate',
                ))

    shuffle_size = cfg['training']['shuffle_size']
    total_batch_size = cfg['training']['batch_size']
    backend.tf_transfer.ChunkParser.BATCH_SIZE = total_batch_size
    tfprocess = backend.tf_transfer.TFProcess(cfg, name, collection_name)

    train_parser = backend.tf_transfer.ChunkParser(
                backend.tf_transfer.FileDataSrc(train_chunks_white.copy(), train_chunks_black.copy()),
                shuffle_size=shuffle_size,
                sample=SKIP,
                batch_size=backend.tf_transfer.ChunkParser.BATCH_SIZE,
                workers=num_workers,
                )
    train_dataset = tf.data.Dataset.from_generator(
            train_parser.parse,
            output_types=(
                tf.string, tf.string, tf.string, tf.string
                ),
            )
    train_dataset = train_dataset.map(
            backend.tf_transfer.ChunkParser.parse_function)
    train_dataset = train_dataset.prefetch(4)

    test_parser = backend.tf_transfer.ChunkParser(
            backend.tf_transfer.FileDataSrc(val_chunks_white.copy(), val_chunks_black.copy()),
            shuffle_size=shuffle_size,
            sample=SKIP,
            batch_size=backend.tf_transfer.ChunkParser.BATCH_SIZE,
            workers=num_workers,
            )
    test_dataset = tf.data.Dataset.from_generator(
        test_parser.parse,
        output_types=(tf.string, tf.string, tf.string, tf.string),
        )
    test_dataset = test_dataset.map(
        backend.tf_transfer.ChunkParser.parse_function)
    test_dataset = test_dataset.prefetch(4)

    tfprocess.init_v2(train_dataset, test_dataset)

    tfprocess.restore_v2()

    num_evals = cfg['training'].get('num_test_positions', (len(val_chunks_white) + len(val_chunks_black)) * 10)
    num_evals = max(1, num_evals // backend.tf_transfer.ChunkParser.BATCH_SIZE)
    print("Using {} evaluation batches".format(num_evals))
    try:
        tfprocess.process_loop_v2(total_batch_size, num_evals, batch_splits=1)
    except KeyboardInterrupt:
        backend.printWithDate("KeyboardInterrupt: Stopping")
        train_parser.shutdown()
        test_parser.shutdown()
        raise
    tfprocess.save_leelaz_weights_v2(output_name)

    train_parser.shutdown()
    test_parser.shutdown()
    return cfg

def make_model_files(cfg, name, collection_name, save_dir):
    output_name = os.path.join(save_dir, collection_name, name)
    models_dir = os.path.join('models', collection_name, name)
    models = [(int(p.name.split('-')[1]), p.name, p.path) for p in os.scandir(models_dir) if p.name.endswith('.pb.gz')]
    top_model = max(models, key = lambda x : x[0])

    os.makedirs(output_name, exist_ok=True)
    model_file_name = top_model[1].replace('ckpt', name)
    shutil.copy(top_model[2], os.path.join(output_name, model_file_name))
    with open(os.path.join(output_name, "config.yaml"), 'w') as f:
        cfg_yaml = yaml.dump(cfg).replace('\n', '\n  ').strip()
        f.write(f"""
%YAML 1.2
---
name: {name}
display_name: {name.replace('_', ' ')}
engine: lc0_23
options:
  weightsPath: {model_file_name}
full_config:
  {cfg_yaml}
...""")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Tensorflow pipeline for training Leela Chess.', formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('config', help='config file for model / training')
    parser.add_argument('player_name', nargs='?', help='player name to train on', default=None)
    parser.add_argument('--gpu', help='gpu to use', default = 0, type = int)
    parser.add_argument('--num_workers', help='number of worker threads to use', default = max(1, multiprocessing.cpu_count() - 2), type = int)
    parser.add_argument('--copy_dir', help='dir to save final models in', default = 'final_models')
    args = parser.parse_args()

    collection_name = os.path.basename(os.path.dirname(args.config)).replace('configs_', '')
    name = os.path.basename(args.config).split('.')[0]

    if args.player_name is not None:
        name = f"{args.player_name}_{name}"

    multiprocessing.set_start_method('spawn')
    cfg = main(args.config, name, collection_name, args.player_name, args.gpu, args.num_workers)
    make_model_files(cfg, name, collection_name, args.copy_dir)
