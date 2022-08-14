import bz2
import csv
import argparse
import os
import numpy as np
from sklearn.naive_bayes import GaussianNB

def parse_argument():
    parser = argparse.ArgumentParser(description='arg parser')

    parser.add_argument('--input_dir', default='cp_loss_hist')
    parser.add_argument('--use_bayes', default=True)

    return parser.parse_args()

def read_npy(input_dir):

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
        train_path = os.path.join(input_dir, player_name + '_{}.npy'.format('train'))
        val_path = os.path.join(input_dir, player_name + '_{}.npy'.format('validation'))
        test_path = os.path.join(input_dir, player_name + '_{}.npy'.format('test'))

        player_data[player_name]['train'] = np.load(train_path)
        player_data[player_name]['validation'] = np.load(val_path)
        player_data[player_name]['test'] = np.load(test_path)

    return player_data

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

    train_data = np.stack(train_list, 0)
    return train_data, train_label, player_index

def predict(train_data, train_label, player_data, player_index):
    print(player_index)
    correct = 0
    total = 0
    model = GaussianNB()
    model.fit(train_data, train_label)

    for player in player_data.keys():
        test = player_data[player]['test']
        predicted = model.predict(np.expand_dims(test, axis=0))
        index = predicted[0]
        if index == player_index[player]:
            correct += 1
        total += 1

    print('accuracy is {}'.format(correct / total))

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

def test_euclidean_dist(train_list, player_data, player_index):
    print(player_index)
    correct = 0
    total = 0
    # loop through each player and test their 'test set'
    for player in player_data.keys():
        dist_list = []
        test = player_data[player]['test']

        # save distance for each (test, train)
        for train_data in train_list:
            dist = np.linalg.norm(train_data - test)
            dist_list.append(dist)

        # find minimum distance and its index
        min_index = dist_list.index(min(dist_list))
        if min_index == player_index[player]:
            correct += 1
        total += 1

    print('accuracy is {}'.format(correct / total))

# =============================== run bayes or euclidean ===============================
def run_bayes(player_data):
    print("Using Naive Bayes")
    train_data, train_label, player_index = construct_train_set(player_data)
    predict(train_data, train_label, player_data, player_index)

def run_euclidean_dist(player_data):
    print("Using Euclidean Distance")
    train_list, player_index = construct_train_list(player_data)
    test_euclidean_dist(train_list, player_data, player_index)


if __name__ == '__main__':
    args = parse_argument()

    player_data = read_npy(args.input_dir)

    if args.use_bayes:
        run_bayes(player_data)
    else:
        run_euclidean_dist(player_data)