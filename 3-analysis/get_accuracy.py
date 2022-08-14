import argparse
import os
import os.path

import pandas

def main():
    parser = argparse.ArgumentParser(description='Quick helper for getting model accuracies', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputs', nargs = '+', help='input CSVs')
    parser.add_argument('--nrows', help='num lines', type = int, default=None)
    args = parser.parse_args()

    for p in args.inputs:
        try:
            df = pandas.read_csv(p, nrows = args.nrows)
        except EOFError:
            print(f"{os.path.abspath(p).split('.')[0]} EOF")
        else:
            print(f"{os.path.abspath(p).split('.')[0]} {df['model_correct'].mean() * 100:.2f}%")

if __name__ == "__main__":
    main()
