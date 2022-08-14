import backend

import argparse
import bz2
import random

@backend.logged_main
def main():
    parser = argparse.ArgumentParser(description='Split games into some numbe of subsets, by percentage', formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('input', help='input pgn')

    parser.add_argument('outputs', nargs='+', help='output pgn files ', type = str)

    parser.add_argument('--ratios', nargs='+', help='ratios of games for the outputs', required = True, type = float)

    parser.add_argument('--no_shuffle', action='store_false', help='Stop output shuffling')
    parser.add_argument('--seed', type=int, help='random seed', default = 1)
    args = parser.parse_args()

    if len(args.ratios) != len(args.outputs):
        raise RuntimeError(f"Invalid outputs specified: {args.outputs} and {args.ratios}")

    random.seed(args.seed)
    games = backend.GamesFile(args.input)

    game_strs = []

    for i, (d, l) in enumerate(games):
        game_strs.append(l)
        if i % 10000 == 0:
            backend.printWithDate(f"{i} done from {args.input}", end = '\r')
    backend.printWithDate(f"{i} done total from {args.input}")
    if not args.no_shuffle:
        random.shuffle(game_strs)

    split_indices = [int(r * len(game_strs) / sum(args.ratios)) for r in args.ratios]

    #Correction for rounding, not very precise
    split_indices[0] += len(game_strs) - sum(split_indices)

    for p, c in zip(args.outputs, split_indices):
        backend.printWithDate(f"Writing {c} games to: {p}")
        with bz2.open(p, 'wt') as f:
            f.write(''.join(
                [game_strs.pop() for i in range(c)]
                ))

    backend.printWithDate("done")

if __name__ == '__main__':
    main()
