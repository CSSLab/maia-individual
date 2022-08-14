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
    parser.add_argument('csvs_dir', help='dir of csvs')
    parser.add_argument('output_list', help='list of targets')
    parser.add_argument('bin_size', type=int, help='players per bin')
    parser.add_argument('bins', type=int, nargs = '+', help='bins')
    parser.add_argument('--pool_size', type=int, help='Number of threads to use for reading', default = 48)
    parser.add_argument('--seed', type=int, help='random seed', default = 1)
    args = parser.parse_args()
    random.seed(args.seed)

    bins = [int(b // 100 * 100) for b in args.bins]

    with multiprocessing.Pool(args.pool_size) as pool:
        players = pool.map(load_player, glob.glob(os.path.join(args.csvs_dir, '*.csv.bz2')))
    backend.printWithDate(f"Found {len(players)} players, using {len(bins)} bins")
    binned_players = {b : [] for b in bins}
    for p in players:
        pe_round = int(p['elo'] // 100 * 100)
        if pe_round in bins:
            binned_players[pe_round].append(p)
    backend.printWithDate(f"Found: " + ', '.join([f"{b} : {len(p)}" for b, p in binned_players.items()]))

    with open(args.output_list, 'wt') as f:
        for b, p in binned_players.items():
                random.shuffle(p)
                print(b, [d['name'] for d in p[:args.bin_size]])
                f.write('\n'.join([d['name'] for d in p[:args.bin_size]]) +'\n')

def load_player(path):
    df = pandas.read_csv(path, low_memory=False)
    elo = df['ELO'][-10000:].mean()
    count = len(df)
    return {
        'name' : df['player'].iloc[0],
        'elo' : elo,
        'count' : count,
    }
if __name__ == "__main__":
    main()
