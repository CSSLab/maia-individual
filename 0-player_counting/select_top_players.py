import backend

import argparse
import bz2
import glob
import random
import os.path
import multiprocessing

import pandas

@backend.logged_main
def main():
    parser = argparse.ArgumentParser(description='Read all the metadata and select top n players for training/validation/testing', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputs', help='input csvs dir')
    parser.add_argument('output_train', help='output csv for training data')
    parser.add_argument('num_train', type=int, help='num for main training')
    parser.add_argument('output_val', help='output csv for validation data')
    parser.add_argument('num_val', type=int, help='num for big validation run')
    parser.add_argument('output_test', help='output csv for testing data')
    parser.add_argument('num_test', type=int, help='num for holdout set')
    parser.add_argument('--pool_size', type=int, help='Number of models to run in parallel', default = 48)
    parser.add_argument('--min_elo', type=int, help='min elo to select', default = 1100)
    parser.add_argument('--max_elo', type=int, help='max elo to select', default = 2000)
    parser.add_argument('--seed', type=int, help='random seed', default = 1)
    args = parser.parse_args()
    random.seed(args.seed)

    targets = glob.glob(os.path.join(args.inputs, '*csv.bz2'))

    with multiprocessing.Pool(args.pool_size) as pool:
        players = pool.starmap(check_player, ((t, args.min_elo, args.max_elo) for t in targets))

    players_top = sorted(
        (p for p in players if p is not None),
        key = lambda x : x[1],
        reverse=True,
        )[:args.num_train + args.num_val + args.num_test]

    random.shuffle(players_top)

    write_output_file(args.output_train, args.num_train, players_top)
    write_output_file(args.output_val, args.num_val, players_top)
    write_output_file(args.output_test, args.num_test, players_top)

def write_output_file(path, count, targets):
    with open(path, 'wt') as f:
        f.write("player,count,ELO\n")
        for i in range(count):
            t = targets.pop()
            f.write(f"{t[0]},{t[1]},{t[2]}\n")

def check_player(path, min_elo, max_elo):
    df = pandas.read_csv(path, low_memory=False)
    elo = df['ELO'][-10000:].mean()
    count = len(df)
    if elo > min_elo and elo < max_elo:
        return path.split('/')[-1].split('.')[0], count, elo
    else:
        return None

if __name__ == "__main__":
    main()
