
import bz2
import csv
import argparse
import os
import numpy as np
# import matplotlib
# matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import multiprocessing
from functools import partial

def parse_argument():
    parser = argparse.ArgumentParser(description='arg parser')

    parser.add_argument('--input_dir', default='/data/transfer_players_validate')
    parser.add_argument('--player_name_dir', default='../transfer_training/final_models_val/unfrozen_copy')
    parser.add_argument('--saved_dir', default='cp_loss_hist')
    parser.add_argument('--will_save', default=True)

    return parser.parse_args()

def normalize(data):
    norm = np.linalg.norm(data)
    data_norm = data/norm
    return data_norm

def prepare_dataset(players, player_name, cp_hist, dataset):
    # add up black and white games (counts can be directly added)
    if players[player_name][dataset] is None:
        players[player_name][dataset] = cp_hist
    else:
        players[player_name][dataset] = players[player_name][dataset] + cp_hist

def save_npy(saved_dir, players, player_name, dataset):
    if not os.path.exists(saved_dir):
        os.mkdir(saved_dir)

    saved = os.path.join(saved_dir, player_name + '_{}.npy'.format(dataset))
    print('saving data to {}'.format(saved))
    np.save(saved, players[player_name][dataset])

def multi_parse(input_dir, saved_dir, players, save, player_name):

    print("=============================================")
    print("parsing data for {}".format(player_name))
    players[player_name] = {'train': None, 'validation': None, 'test': None}

    csv_dir = os.path.join(input_dir, player_name, 'csvs')
    # for each csv, add up black and white games (counts can be directly added)
    for csv_fname in os.listdir(csv_dir):
        path = os.path.join(csv_dir, csv_fname)
        # parse bz2 file
        source_file = bz2.BZ2File(path, "r")
        cp_hist, num_games = get_cp_loss_from_csv(player_name, source_file)
        print(path)

        if csv_fname.startswith('train'):
            prepare_dataset(players, player_name, cp_hist, 'train')

        elif csv_fname.startswith('validate'):
            prepare_dataset(players, player_name, cp_hist, 'validation')

        elif csv_fname.startswith('test'):
            prepare_dataset(players, player_name, cp_hist, 'test')

    # normalize the histogram to range [0, 1]
    players[player_name]['train'] = normalize(players[player_name]['train'])
    players[player_name]['validation'] = normalize(players[player_name]['validation'])
    players[player_name]['test'] = normalize(players[player_name]['test'])

    # save for future use, parsing takes too long...
    if save:
        save_npy(saved_dir, players, player_name, 'train')
        save_npy(saved_dir, players, player_name, 'validation')
        save_npy(saved_dir, players, player_name, 'test')

def construct_datasets(player_names, input_dir, saved_dir, will_save):
    players = {}

    pool = multiprocessing.Pool(25)
    func = partial(multi_parse, input_dir, saved_dir, players, will_save)
    pool.map(func, player_names)
    pool.close()
    pool.join()

def get_cp_loss_from_csv(player_name, path):
    cp_losses = []
    games = {}
    with bz2.open(path, 'rt') as f:
        for i, line in enumerate(path):
            if i > 0:
                line = line.decode("utf-8")
                row = line.rstrip().split(',')
                # avoid empty line
                if row[0] == '':
                    continue

                game_id = row[0]
                cp_loss = row[17]
                active_player = row[25]
                if player_name != active_player:
                    continue

                # ignore cases like -inf, inf, nan
                if cp_loss != str(-1 * np.inf) and cp_loss != str(np.inf) and cp_loss != 'nan':
                    # append cp loss per move
                    cp_losses.append(float(cp_loss))

                    # for purpose of counting how many games
                    if game_id not in games:
                        games[game_id] = 1


    ######################## plot for viewing ########################
    # plt.hist(cp_losses, density=False, bins=50)
    # plt.ylabel('Count')
    # plt.xlabel('Cp Loss')
    # plt.show()

    cp_hist = np.histogram(cp_losses, density=False, bins=50, range=(0, 5)) # density=False for counts

    cp_hist = cp_hist[0] # cp_hist in format of (hist count, range)

    print("number of games: {}".format(len(games)))

    return cp_hist, len(games)


def get_player_names(player_name_dir):

    player_names = []
    for player_name in os.listdir(player_name_dir):
        player = player_name.replace("_unfrozen_copy", "")
        player_names.append(player)

    # print(player_names)
    return player_names


if __name__ == '__main__':
    args = parse_argument()

    player_names = get_player_names(args.player_name_dir)

    construct_datasets(player_names, args.input_dir, args.saved_dir, args.will_save)
