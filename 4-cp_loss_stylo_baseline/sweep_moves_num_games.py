import bz2
import csv
import argparse
import os
import numpy as np
from sklearn.naive_bayes import GaussianNB
from matplotlib import pyplot as plt

def parse_argument():
    parser = argparse.ArgumentParser(description='arg parser')

    parser.add_argument('--train_dir', default='cp_loss_hist_per_move')
    parser.add_argument('--input_dir', default='cp_loss_hist_per_move_per_game_count')
    parser.add_argument('--output_start_after_csv', default='start_after_4games.csv')
    parser.add_argument('--output_stop_after_csv', default='stop_after_4games.csv')
    parser.add_argument('--num_games', default=4)
    parser.add_argument('--saved_plot', default='plot_4games.png')

    return parser.parse_args()

def read_npy(train_dir, input_dir):

    player_list = {}
    for input_data in os.listdir(input_dir):
        # will split into [player_name, 'train/test/val']
        input_name = input_data.split('_')
        if len(input_name) > 2:
            player_name = input_name[:-1]
            player_name = '_'.join(player_name)
        else:
            player_name = input_name[0]
        # add into player list
        if player_name not in player_list:
            player_list[player_name] = 1

    player_list = list(player_list.keys())

    player_data = {}
    for player_name in player_list:
        player_data[player_name] = {'train': None, 'validation': None, 'test': None}
        train_path = os.path.join(train_dir, player_name + '_{}.npy'.format('train'))
        val_path = os.path.join(input_dir, player_name + '_{}.npy'.format('validation'))
        test_path = os.path.join(input_dir, player_name + '_{}.npy'.format('test'))

        player_data[player_name]['train'] = np.load(train_path, allow_pickle=True)
        player_data[player_name]['train'] = player_data[player_name]['train'].item()
        player_data[player_name]['validation'] = np.load(val_path, allow_pickle=True)
        player_data[player_name]['validation'] = player_data[player_name]['validation'].item()
        player_data[player_name]['test'] = np.load(test_path, allow_pickle=True)
        player_data[player_name]['test'] = player_data[player_name]['test'].item()

    return player_data

def normalize(data):
    data_norm = data

    if any(v != 0 for v in data):
        norm = np.linalg.norm(data)
        data_norm = data/norm

    return data_norm

def construct_train_set(player_data, is_start_after, move_stop):
    player_index = {}
    train_list = []
    train_label = []

    i = 0
    for player in player_data.keys():
        # if player in os.listdir('/data/csvs'):
        player_index[player] = i
        train_label.append(i)
        if is_start_after:
            train_list.append(player_data[player]['train']['start_after'][move_stop])
        else:
            train_list.append(player_data[player]['train']['stop_after'][move_stop])

        i += 1

    train_label = np.asarray(train_label)
    # one_hot = np.zeros((train_label.size, train_label.max()+1))
    # one_hot[np.arange(train_label.size),train_label] = 1
    # print(one_hot.shape)

    train_data = np.stack(train_list, 0)
    return train_data, train_label, player_index


def predict(train_data, train_label, player_data, player_index, is_start_after, move_stop, num_games):
    accurcies = []
    correct = 0
    total = 0
    model = GaussianNB()
    model.fit(train_data, train_label)
    results = None
    for player in player_data.keys():
        test_game = None
        tmp_game = None
        test_games = []
        test = player_data[player]['test']
        count = 1

        # key is game id
        for key, value in test.items():
            # get which game to use
            if is_start_after:
                tmp_game = test[key]['start_after'][move_stop]
                # ignore all 0 cases, essentially there's no more move in this game
                if all(v == 0 for v in tmp_game):
                    continue
            else:
                tmp_game = test[key]['stop_after'][move_stop]

            # add up counts in each game
            if test_game is None:
                test_game = tmp_game
            else:
                test_game = test_game + tmp_game

            if count == num_games:
                # test_game is addition of counts, need to normalize before testing
                test_game = normalize(test_game)
                test_games.append(test_game)

                # reset
                test_game = None
                tmp_game = None
                count = 1

            else:
                count += 1

        # skip player if all games are beyond move_stop
        if not test_games:
            continue

        test_games = np.stack(test_games, axis=0)
        predicted = model.predict(test_games)
        result = (predicted == player_index[player]).astype(float)

        # append to the overall result
        if results is None:
            results = result
        else:
            results = np.append(results, result, 0)

    if results is None:
        accuracy = 0

    else:
        accuracy = np.mean(results)

    print(accuracy)

    return accuracy


def make_plots(moves, start_after_accuracies, stop_after_accuracies, plot_name):
    plt.plot(moves, start_after_accuracies, label="Start after x moves")
    plt.plot(moves, stop_after_accuracies, label="Stop after x moves")
    plt.legend()
    plt.xlabel("Moves")
    plt.savefig(plot_name)


if __name__ == '__main__':
    args = parse_argument()

    player_data = read_npy(args.train_dir, args.input_dir)
    moves = [i for i in range(101)]
    start_after_accuracies = []
    stop_after_accuracies = []
    output_start_csv = open(args.output_start_after_csv, 'w', newline='')
    writer_start = csv.writer(output_start_csv)
    writer_start.writerow(['move', 'accuracy'])

    output_stop_csv = open(args.output_stop_after_csv, 'w', newline='')
    writer_stop = csv.writer(output_stop_csv)
    writer_stop.writerow(['move', 'accuracy'])

    for is_start_after in (True, False):
        for i in range(101):
            print('testing {} move {}'.format('start_after' if is_start_after else 'stop_after', i))
            train_data, train_label, player_index = construct_train_set(player_data, is_start_after, i)

            accuracy = predict(train_data, train_label, player_data, player_index, is_start_after, i, args.num_games)

            if is_start_after:
                start_after_accuracies.append(accuracy)
                writer_start.writerow([i, accuracy])
            else:
                stop_after_accuracies.append(accuracy)
                writer_stop.writerow([i, accuracy])

    make_plots(moves, start_after_accuracies, stop_after_accuracies, args.saved_plot)
