import backend

import os
import os.path
import csv
import bz2
import argparse

@backend.logged_main
def main():
    parser = argparse.ArgumentParser(description='Get some stats about each of the games')
    parser.add_argument('targets_dir', help='input pgns dir')
    parser.add_argument('output_dir', help='output csvs dir')
    parser.add_argument('--pool_size', type=int, help='Number of models to run in parallel', default = 64)
    args = parser.parse_args()
    multiProc = backend.Multiproc(args.pool_size)
    multiProc.reader_init(Files_lister, args.targets_dir)
    multiProc.processor_init(Games_processor, args.output_dir)

    multiProc.run()

class Files_lister(backend.MultiprocIterable):
    def __init__(self, targets_dir):
        self.targets_dir = targets_dir
        self.targets = [(p.path, p.name.split('.')[0]) for p in os.scandir(targets_dir) if '.pgn.bz2' in p.name]
        backend.printWithDate(f"Found {len(self.targets)} targets in {targets_dir}")
    def __next__(self):
        try:
            backend.printWithDate(f"Pushed target {len(self.targets)} remaining", end = '\r', flush = True)
            return self.targets.pop()
        except IndexError:
            raise StopIteration

class Games_processor(backend.MultiprocWorker):
    def __init__(self, output_dir):
        self.output_dir = output_dir

    def __call__(self, path, name):
        games = backend.GamesFile(path)
        with bz2.open(os.path.join(self.output_dir, f"{name}.csv.bz2"), 'wt') as f:
            writer = csv.DictWriter(f, ["player", "opponent","game_id", "ELO",  "opp_ELO", "was_white", "result", "won", "UTCDate", "UTCTime", "TimeControl"])

            writer.writeheader()
            for d, _ in games:
                game_dat = {}
                game_dat['player'] = name
                game_dat['game_id'] = d['Site'].split('/')[-1]
                game_dat['result'] = d['Result']
                game_dat['UTCDate'] = d['UTCDate']
                game_dat['UTCTime'] = d['UTCTime']
                game_dat['TimeControl'] = d['TimeControl']
                if d['Black'] == name:
                    game_dat['was_white'] = False
                    game_dat['opponent'] = d['White']
                    game_dat['ELO'] = d['BlackElo']
                    game_dat['opp_ELO'] = d['WhiteElo']
                    game_dat['won'] = d['Result'] == '0-1'
                else:
                    game_dat['was_white'] = True
                    game_dat['opponent'] = d['Black']
                    game_dat['ELO'] = d['WhiteElo']
                    game_dat['opp_ELO'] = d['BlackElo']
                    game_dat['won'] = d['Result'] == '1-0'
                writer.writerow(game_dat)

if __name__ == '__main__':
    main()
