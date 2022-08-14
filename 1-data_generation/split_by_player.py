import backend

import argparse
import bz2
import random

@backend.logged_main
def main():
    parser = argparse.ArgumentParser(description='Split games into games were the target was White or Black', formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('input', help='input pgn')
    parser.add_argument('player', help='target player name')
    parser.add_argument('output', help='output pgn prefix')
    parser.add_argument('--no_shuffle', action='store_false', help='Stop output shuffling')
    parser.add_argument('--seed', type=int, help='random seed', default = 1)
    args = parser.parse_args()

    random.seed(args.seed)

    games = backend.GamesFile(args.input)

    outputs_white = []
    outputs_black = []

    for i, (d, l) in enumerate(games):
        if d['White'] == args.player:
            outputs_white.append(l)
        elif d['Black'] == args.player:
            outputs_black.append(l)
        else:
            raise ValueError(f"{args.player} not found in game {i}:\n{l}")
        if i % 10000 == 0:
            backend.printWithDate(f"{i} done with {len(outputs_white)}:{len(outputs_black)} players from {args.input}", end = '\r')
    backend.printWithDate(f"{i} found totals of {len(outputs_white)}:{len(outputs_black)} players from {args.input}")
    backend.printWithDate("Writing white")
    with bz2.open(f"{args.output}_white.pgn.bz2", 'wt') as f:
        if not args.no_shuffle:
            random.shuffle(outputs_white)
        f.write(''.join(outputs_white))
    backend.printWithDate("Writing black")
    with bz2.open(f"{args.output}_black.pgn.bz2", 'wt') as f:
        if not args.no_shuffle:
            random.shuffle(outputs_black)
        f.write(''.join(outputs_black))
    backend.printWithDate("done")

if __name__ == '__main__':
    main()
