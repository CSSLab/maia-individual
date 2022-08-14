import backend

import argparse
import bz2

@backend.logged_main
def main():
    parser = argparse.ArgumentParser(description='Count number of times each player occurs in pgn', formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('input', help='input pgn')
    parser.add_argument('output', help='output csv')
    parser.add_argument('--exclude_bullet', action='store_false', help='Remove bullet games from counts')
    args = parser.parse_args()

    games = backend.GamesFile(args.input)

    counts = {}

    for i, (d, _) in enumerate(games):
        if args.exclude_bullet and 'Bullet' in d['Event']:
            continue
        else:
            add_player(d['White'], counts)
            add_player(d['Black'], counts)
        if i % 10000 == 0:
            backend.printWithDate(f"{i} done with {len(counts)} players from {args.input}", end = '\r')

    backend.printWithDate(f"{i} found total of {len(counts)} players from {args.input}")
    with bz2.open(args.output, 'wt') as f:
        f.write("player,count\n")
        for p, c in sorted(counts.items(), key = lambda x: x[1], reverse=True):
            f.write(f"{p},{c}\n")
    backend.printWithDate("done")

def add_player(p, d):
    try:
        d[p] += 1
    except KeyError:
        d[p] = 1

if __name__ == '__main__':
    main()
