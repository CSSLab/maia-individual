import bz2
import csv
import argparse
import os
import numpy as np
import tensorflow as tf
from sklearn.naive_bayes import GaussianNB

def parse_argument():
    parser = argparse.ArgumentParser(description='arg parser')

    parser.add_argument('--input_dir', default='cp_loss_count_per_game')
    parser.add_argument('--gpu', default=0, type=int)

    return parser.parse_args()

def normalize(data):
    norm = np.linalg.norm(data)
    data_norm = data/norm
    return data_norm

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

        player_data[player_name]['train'] = np.load(train_path, allow_pickle=True)
        player_data[player_name]['train'] = player_data[player_name]['train'].item()
        player_data[player_name]['validation'] = np.load(val_path, allow_pickle=True)
        player_data[player_name]['validation'] = player_data[player_name]['validation'].item()
        player_data[player_name]['test'] = np.load(test_path, allow_pickle=True)
        player_data[player_name]['test'] = player_data[player_name]['test'].item()

    return player_data

def construct_datasets(player_data):
    player_index = {}
    train_list = []
    train_labels = []
    validation_list = []
    validation_labels = []
    test_list = []
    test_labels = []
    i = 0
    for player in player_data.keys():
        label = i
        player_index[player] = i
        for key, value in player_data[player]['train'].items():
            train_list.append(normalize(value))
            train_labels.append(label)

        for key, value in player_data[player]['validation'].items():
            validation_list.append(normalize(value))
            validation_labels.append(label)

        for key, value in player_data[player]['test'].items():
            test_list.append(normalize(value))
            test_labels.append(label)

        i += 1
    # convert lists into numpy arrays
    train_list_np = np.stack(train_list, axis=0)
    validation_list_np = np.stack(validation_list, axis=0)
    test_list_np = np.stack(test_list, axis=0)

    train_labels_np = np.stack(train_labels, axis=0)
    validation_labels_np = np.stack(validation_labels, axis=0)
    test_labels_np = np.stack(test_labels, axis=0)

    return train_list_np, train_labels_np, validation_list_np, validation_labels_np, test_list_np, test_labels_np, player_index


def init_net(output_size):
    l2reg = tf.keras.regularizers.l2(l=0.5 * (0.0001))
    input_var = tf.keras.Input(shape=(50, ))
    dense_1 = tf.keras.layers.Dense(40, kernel_initializer='glorot_normal', kernel_regularizer=l2reg, bias_regularizer=l2reg, activation='relu')(input_var)
    dense_2 = tf.keras.layers.Dense(30, kernel_initializer='glorot_normal', kernel_regularizer=l2reg, bias_regularizer=l2reg)(dense_1)

    model= tf.keras.Model(inputs=input_var, outputs=dense_2)
    return model

def train(train_dataset, train_labels, val_dataset, val_labels, test_dataset, test_labels, player_index):
    net = init_net(max(test_labels) + 1)
    net.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.0001, clipnorm=1),
              loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
              metrics=['accuracy'])

    net.fit(train_dataset, train_labels, batch_size=32, epochs=10, validation_data=(val_dataset, val_labels))

    test_loss, test_acc = net.evaluate(test_dataset,  test_labels, verbose=2)

    print('\nTest accuracy:', test_acc)

    return net

# predict is to verify if keras test is correct
def predict(net, test, test_labels):
    probability_model = tf.keras.Sequential([net, 
                                            tf.keras.layers.Softmax()])
    predictions = probability_model.predict(test)

    correct = 0
    total = 0
    for i, prediction in enumerate(predictions):
        if test_labels[i] == np.argmax(prediction):
            correct += 1
        total += 1

    print('test accuracy is: {}'.format(correct / total))

if __name__ == '__main__':
    args = parse_argument()

    gpus = tf.config.experimental.list_physical_devices('GPU')
    tf.config.experimental.set_visible_devices(gpus[args.gpu], 'GPU')
    tf.config.experimental.set_memory_growth(gpus[args.gpu], True)

    player_data = read_npy(args.input_dir)

    train_dataset, train_labels, val_dataset, val_labels, test_dataset, test_labels, player_index = construct_datasets(player_data)

    net = train(train_dataset, train_labels, val_dataset, val_labels, test_dataset, test_labels, player_index)

    # predict is to verify if test is correct
    # predict(net, test_dataset, test_labels)
