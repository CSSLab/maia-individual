
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
    parser.add_argument('--saved_dir', default='cp_loss_hist_per_move_per_game_count')
    parser.add_argument('--will_save', default=True)

    return parser.parse_args()

def normalize(data):
    data_norm = data

    if any(v != 0 for v in data):
        norm = np.linalg.norm(data)
        data_norm = data/norm

    return data_norm

def prepare_dataset(players, player_name, games, dataset):
    # add up black and white games
    if players[player_name][dataset] is None:
        players[player_name][dataset] = games
    else:
        players[player_name][dataset].update(games)


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
        print(path)
        # parse bz2 file
        source_file = bz2.BZ2File(path, "r")
        games, num_games = get_cp_loss_from_csv(player_name, source_file)

        if csv_fname.startswith('train'):
            prepare_dataset(players, player_name, games, 'train')

        elif csv_fname.startswith('validate'):
            prepare_dataset(players, player_name, games, 'validation')

        elif csv_fname.startswith('test'):
            prepare_dataset(players, player_name, games, 'test')

    # save for future use, parsing takes too long...
    if save:
        save_npy(saved_dir, players, player_name, 'train')
        save_npy(saved_dir, players, player_name, 'validation')
        save_npy(saved_dir, players, player_name, 'test')

def construct_datasets(player_names, input_dir, saved_dir, will_save):
    players = {}

    pool = multiprocessing.Pool(40)
    func = partial(multi_parse, input_dir, saved_dir, players, will_save)
    pool.map(func, player_names)
    pool.close()
    pool.join()


def get_cp_loss_start_after(cp_losses, move_start=0):
    return cp_losses[move_start:]

# 0 will be empty
def get_cp_loss_stop_after(cp_losses, move_stop=100):
    return cp_losses[:move_stop]

# move_stop is in range [0, 100]
def get_cp_loss_from_csv(player_name, path):
    # cp_losses = []
    games = {}
    with bz2.open(path, 'rt') as f:
        for i, line in enumerate(path):
            if i > 0:
                line = line.decode("utf-8")
                row = line.rstrip().split(',')
                # avoid empty line
                if row[0] == '':
                    continue

                active_player = row[25]
                if player_name != active_player:
                    continue

                # move_ply starts from 0, need to add 1, move will be parsed in order
                move_ply = int(row[13])
                move = move_ply // 2 + 1

                game_id = row[0]
                cp_loss = row[17]

                if game_id in games:
                    if cp_loss == str(-1 * np.inf) or cp_loss == str(np.inf) or cp_loss == 'nan':
                        cp_loss = float(-100)

                # ignore cases like -inf, inf, nan
                if cp_loss != str(-1 * np.inf) and cp_loss != str(np.inf) and cp_loss != 'nan':
                    if game_id not in games:
                        games[game_id] = [float(cp_loss)]
                    else:
                        games[game_id].append(float(cp_loss))

    final_games = {key: {'start_after': {}, 'stop_after': {}} for key, value in games.items() if len(value) > 25 and len(value) < 50}
    # final_games = {key: {'start_after': {}, 'stop_after': {}} for key in games.keys()}

    # get per game histogram
    for i in range(101):
        for key, value in games.items():
            if len(value) > 25 and len(value) < 50:
                if key not in final_games:
                    print(key)

                final_games[key]['start_after'][i] = get_cp_loss_start_after(value, i)
                final_games[key]['stop_after'][i] = get_cp_loss_stop_after(value, i)

                final_games[key]['start_after'][i] = np.histogram(final_games[key]['start_after'][i], density=False, bins=50, range=(0, 5))[0]
                final_games[key]['stop_after'][i] = np.histogram(final_games[key]['stop_after'][i], density=False, bins=50, range=(0, 5))[0]

                # final_games[key]['start_after'][i] = normalize(final_games[key]['start_after'][i])
                # final_games[key]['stop_after'][i] = normalize(final_games[key]['stop_after'][i])

    print("number of games: {}".format(len(games)))
    return final_games, len(games)


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
