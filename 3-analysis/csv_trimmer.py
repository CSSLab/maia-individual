import argparse
import os
import os.path
import bz2
import csv
import multiprocessing
import humanize
import time
import queue
import json
import pandas

import chess

import backend

#@backend.logged_main
def main():
    parser = argparse.ArgumentParser(description='Run model on all the lines of the csv', formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('input', help='input CSV')
    parser.add_argument('output', help='output CSV')
    parser.add_argument('--ngames', type=int, help='number of games to read in', default = 10)
    parser.add_argument('--min_ply', type=int, help='look at games with ply above this', default = 50)
    parser.add_argument('--max_ply', type=int, help='look at games with ply below this', default = 100)
    args = parser.parse_args()
    backend.printWithDate(f"Starting {args.input} to {args.output}")

    with bz2.open(args.input, 'rt') as fin, bz2.open(args.output, 'wt') as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, reader.fieldnames)
        writer.writeheader()
        games_count = 0
        current_game = None
        for row in reader:
            if args.min_ply is not None and int(row['num_ply']) <= args.min_ply:
                continue
            elif args.max_ply is not None and int(row['num_ply']) >= args.max_ply:
                continue
            elif row['game_id'] != current_game:
                current_game = row['game_id']
                games_count += 1
                if args.ngames is not None and games_count >args.ngames:
                    break
            writer.writerow(row)


if __name__ == "__main__":
    main()
