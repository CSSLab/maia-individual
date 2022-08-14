import bz2
import csv
import argparse
import os
import numpy as np
from sklearn.naive_bayes import GaussianNB
import multiprocessing
from functools import partial

def parse_argument():
    parser = argparse.ArgumentParser(description='arg parser')

    parser.add_argument('--train_dir', default='cp_loss_hist')
    parser.add_argument('--input_dir', default='cp_loss_count_per_game')
    parser.add_argument('--use_bayes', default=True)
    parser.add_argument('--num_games_list', default=[1, 2, 4, 8, 16], type=list)
    parser.add_argument('--output_csv', default='games_accuracy.csv')

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

        player_data[player_name]['train'] = np.load(train_path)
        player_data[player_name]['validation'] = np.load(val_path, allow_pickle=True)
        player_data[player_name]['validation'] = player_data[player_name]['validation'].item()
        player_data[player_name]['test'] = np.load(test_path, allow_pickle=True)
        player_data[player_name]['test'] = player_data[player_name]['test'].item()

    return player_data

def normalize(data):
    norm = np.linalg.norm(data)
    data_norm = data/norm
    return data_norm

# =============================== Naive Bayes ===============================
def construct_train_set(player_data):
    player_index = {}
    train_list = []
    train_label = []

    i = 0
    for player in player_data.keys():
        player_index[player] = i
        train_label.append(i)
        train_list.append(player_data[player]['train'])
        i += 1

    train_label = np.asarray(train_label)
    # one_hot = np.zeros((train_label.size, train_label.max()+1))
    # one_hot[np.arange(train_label.size),train_label] = 1
    # print(one_hot.shape)

    train_data = np.stack(train_list, 0)
    return train_data, train_label, player_index

def predict(train_data, train_label, player_data, num_games_list, player_index):
    print(player_index)

    model = GaussianNB()
    model.fit(train_data, train_label)

    accuracies = []

    for num_games in num_games_list:
        results = None
        print("evaluating with {} games".format(num_games))

        for player in player_data.keys():
            test = player_data[player]['test']
            count = 1
            test_game = None
            test_games = []
            for key, value in test.items():
                if test_game is None:
                    test_game = value
                else:
                    test_game = test_game + value
                if count == num_games:
                    # test_game is addition of counts, need to normalize before testing
                    test_game = normalize(test_game)
                    test_games.append(test_game)

                    # reset
                    test_game = None
                    count = 1
                    
                else:
                    count += 1

            test_games = np.stack(test_games, axis=0)
            predicted = model.predict(test_games)
            result = (predicted == player_index[player]).astype(float)

            if results is None:
                results = result
            else:
                results = np.append(results, result, 0)

        if results is None:
            accuracy = 0
        else:
            accuracy = np.mean(results)

        accuracies.append([num_games, accuracy])
        print("num_games: {}, accuracy: {}".format(num_games, accuracy))

    return accuracies

# =============================== Euclidean Distance ===============================
def construct_train_list(player_data):
    # player_index is {player_name: id} mapping
    player_index = {}
    train_list = []
    i = 0
    for player in player_data.keys():
        player_index[player] = i
        train_list.append(player_data[player]['train'])
        i += 1

    return train_list, player_index


def test_euclidean_dist(train_list, player_data, num_games_list, player_index):
    accuracies = []

    for num_games in num_games_list:
        print("evaluating with {} games".format(num_games))
        correct = 0
        total = 0

        # loop through each player and test their 'test set'
        for player in player_data.keys():
            test = player_data[player]['test']
            count = 1
            test_game = None

            for key, value in test.items():
                if test_game is None:
                    test_game = value
                else:
                    test_game = test_game + value

                if count == num_games:
                    test_game = normalize(test_game)

                    dist_list = []
                    # save distance for each (test, train)
                    for train_data in train_list:
                        dist = np.linalg.norm(train_data - test_game)
                        dist_list.append(dist)

                    # find minimum distance and its index
                    min_index = dist_list.index(min(dist_list))
                    if min_index == player_index[player]:
                        correct += 1
                    total += 1

                    # reset
                    test_game = None
                    count = 1
                
                else:
                    count += 1

        accuracies.append([num_games, correct / total])
        print("num_games: {}, accuracy: {}".format(num_games, correct / total))

    return accuracies

# =============================== run bayes or euclidean ===============================
def run_bayes(player_data, output_csv, num_games_list):

    train_data, train_label, player_index = construct_train_set(player_data)
    accuracies = predict(train_data, train_label, player_data, num_games_list, player_index)

    output_csv = open(output_csv, 'w', newline='')
    writer = csv.writer(output_csv)
    writer.writerow(['num_games', 'accuracy'])
    for i in range(len(accuracies)):
        writer.writerow(accuracies[i])

def run_euclidean_dist(player_data, output_csv, num_games_list):
    train_list, player_index = construct_train_list(player_data)
    accuracies = test_euclidean_dist(train_list, player_data, num_games_list, player_index)

    output_csv = open(output_csv, 'w', newline='')
    writer = csv.writer(output_csv)
    writer.writerow(['num_games', 'accuracy'])
    for i in range(len(accuracies)):
        writer.writerow(accuracies[i])

if __name__ == '__main__':
    args = parse_argument()

    player_data = read_npy(args.train_dir, args.input_dir)

    if args.use_bayes:
        run_bayes(player_data, args.output_csv, args.num_games_list)
    else:
        run_euclidean_dist(player_data, args.output_csv, args.num_games_list)


