import backend

import pandas
import lockfile

import argparse
import bz2
import os
import os.path

@backend.logged_main
def main():
    parser = argparse.ArgumentParser(description='Write pgns of games with slected players in them', formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('target', help='target players list as csv')
    parser.add_argument('inputs', nargs = '+', help='input pgns')
    parser.add_argument('output', help='output dir')
    parser.add_argument('--exclude_bullet', action='store_false', help='Remove bullet games from counts')
    parser.add_argument('--pool_size', type=int, help='Number of models to run in parallel', default = 48)
    args = parser.parse_args()

    df_targets = pandas.read_csv(args.target)
    targets = set(df_targets['player'])

    os.makedirs(args.output, exist_ok=True)

    multiProc = backend.Multiproc(args.pool_size)
    multiProc.reader_init(Files_lister, args.inputs)
    multiProc.processor_init(Games_processor, targets, args.output, args.exclude_bullet)
    multiProc.run()
    backend.printWithDate("done")

class Files_lister(backend.MultiprocIterable):
    def __init__(self, inputs):
        self.inputs = list(inputs)
        backend.printWithDate(f"Found {len(self.inputs)}")
    def __next__(self):
        try:
            backend.printWithDate(f"Pushed target {len(self.inputs)} remaining", end = '\r', flush = True)
            return self.inputs.pop()
        except IndexError:
            raise StopIteration

class Games_processor(backend.MultiprocWorker):
    def __init__(self, targets, output_dir, exclude_bullet):
        self.output_dir = output_dir
        self.targets = targets
        self.exclude_bullet = exclude_bullet

        self.c = 0

    def __call__(self, path):
        games = backend.GamesFile(path)
        self.c = 0
        for i, (d, s) in enumerate(games):
            if self.exclude_bullet and 'Bullet' in d['Event']:
                continue
            else:
                if d['White'] in self.targets:
                    self.write_player(d['White'], s)
                    self.c += 1
                if d['Black'] in self.targets:
                    self.write_player(d['Black'], s)
                    self.c += 1
            if i % 10000 == 0:
                backend.printWithDate(f"{path} {i} done with {self.c} writes", end = '\r')

    def write_player(self, p_name, s):

        p_path = os.path.join(self.output_dir, f"{p_name}.pgn.bz2")
        lock_path = p_path + '.lock'
        lock = lockfile.FileLock(lock_path)
        with lock:
            with bz2.open(p_path, 'at') as f:
                f.write(s)


if __name__ == '__main__':
    main()
