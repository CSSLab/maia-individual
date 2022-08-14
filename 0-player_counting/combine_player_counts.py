import backend

import argparse
import bz2

import pandas

@backend.logged_main
def main():
    parser = argparse.ArgumentParser(description='Collect counts and create list from them', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputs', nargs = '+', help='input csvs')
    parser.add_argument('output', help='output csv')
    args = parser.parse_args()

    counts = {}
    for p in args.inputs:
        backend.printWithDate(f"Processing {p}", end = '\r')
        df = pandas.read_csv(p)
        for i, row in df.iterrows():
            try:
                counts[row['player']] += row['count']
            except KeyError:
                counts[row['player']] = row['count']
    backend.printWithDate(f"Writing")
    with bz2.open(args.output, 'wt') as f:
        f.write('player,count\n')
        for p, c in sorted(counts.items(), key = lambda x: x[1], reverse=True):
            f.write(f"{p},{c}\n")

if __name__ == '__main__':
    main()
