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

    parser.add_argument('model', help='model dir or file')
    parser.add_argument('input', help='input CSV')
    parser.add_argument('output', help='CSV')
    parser.add_argument('model_name', nargs='?',help='model name')
    parser.add_argument('--target_player', type=str, help='Only look at board by this player', default = None)
    parser.add_argument('--nrows', type=int, help='number of rows to read in', default = None)
    parser.add_argument('--pool_size', type=int, help='Number of models to run in parallel', default = 4)
    parser.add_argument('--overwrite', help='Overwrite successful runs', default = False, action="store_true")
    args = parser.parse_args()
    backend.printWithDate(f"Starting model {args.model} analysis of {args.input} to {args.output}")

    if not args.overwrite and os.path.isfile(args.output):
        try:
            df_out = pandas.read_csv(args.output, low_memory=False)
            out_player_name = df_out.iloc[0]['player_name']
        except (EOFError, KeyError):
            backend.printWithDate("Found corrupted output file, overwriting")
        else:
            df_in = pandas.read_csv(args.input,low_memory=False)
            if len(df_out) < .9 * len(df_in) * (.5 if args.target_player else 1.):
                backend.printWithDate(f"Found truncated {len(df_out)} instead of {len(df_in) * (.5 if args.target_player else 1.)} output file, overwriting")
            elif out_player_name != args.target_player:
                backend.printWithDate(f"Found incorrect player {out_player_name} instead of {args.target_player}")
            elif 'player_name' not in df_out.columns:
                backend.printWithDate("Found output file missing player, overwriting")
                df_out['player_name'] = args.target_player if args.target_player is not None else ''
                df_out.to_csv(args.output, index = None)
                return
            else:
                backend.printWithDate(f"Found completed output file, ending job")
                return
    model = None
    model_name = args.model_name
    if os.path.isfile(args.model):
        model = args.model
    else:
        for name, _, files in os.walk(args.model):
            if 'config.yaml' in files:
                model = name
                break
        if model is None:
            model_files = sorted([p.path for p in os.scandir(args.model) if p.name.endswith('pb.gz')], key = lambda x : int(x.split('/')[-1].split('-')[1]))
            if len(model_files) > 0:
                model = model_files[-1]
                if model_name is None:
                    model_name = f"{os.path.basename(os.path.dirname(model))}_{model.split('/')[-1].split('-')[1]}"
            else:
                raise RuntimeError(f"No model or config found for: {args.model}")
    backend.printWithDate(f"Found model: {model}")
    multiProc = backend.Multiproc(args.pool_size)
    multiProc.reader_init(CSV_reader, args.input, args.nrows, args.target_player)
    multiProc.processor_init(line_processor, model, model_name)
    multiProc.writer_init(CSV_writer, args.output, args.target_player)

    multiProc.run()

class CSV_reader(backend.MultiprocIterable):
    def __init__(self, path, max_rows, target_player):
        self.path = path
        self.max_rows = max_rows
        self.target_player = target_player
        self.f = bz2.open(self.path, 'rt')
        self.reader = csv.DictReader(self.f)
        self.reader_iter = enumerate(self.reader)
        self.board = chess.Board()
        self.current_game = None
        self.tstart = time.time()

    def __del__(self):
        try:
            self.f.close()
        except:
            pass

    def __next__(self):
        i, row = next(self.reader_iter)
        if self.max_rows is not None and i >= self.max_rows:
            raise StopIteration("Hit max number of rows")
        if row['game_id'] != self.current_game:
            self.current_game = row['game_id']
            self.board = chess.Board(fen = row['board'])
        send_board = self.board.copy()
        try:
            self.board.push_uci(row['move'])
        except ValueError:
            self.current_game = row['game_id']
        if i % 1000 == 0:
                backend.printWithDate(f"Row {i} in {self.delta_start()}", end = '\r', flush = True)
        if self.target_player is None or row['active_player'] == self.target_player:
            return (send_board, {
                            'game_id' : row['game_id'],
                            'move_ply' : row['move_ply'],
                            'move' : row['move'],
                            }
                        )
        else:
            return next(self)

    def delta_start(self):
        return humanize.naturaldelta(time.time() - self.tstart)

class line_processor(backend.MultiprocWorker):
    def __init__(self, model_path, model_name):
        self.model_path = model_path
        self.model_name = model_name

        if os.path.isdir(self.model_path):
            self.model = backend.model_from_config(self.model_path)
            self.name = self.model.config['name']
            self.display_name = self.model.config['display_name']
        else:
            self.model = backend.LC0_Engine(self.model_path)
            if self.model_name is not None:
                self.name = self.model_name
                self.display_name = self.model_name
            else:
                self.name = os.path.basename(self.model_path)
                self.display_name = os.path.basename(self.model_path)

    def __call__(self, board, row):
        try:
            v, ps = self.model.board_pv(board)
        except KeyError:
            raise backend.SkipCallMultiProc(f"No moves for this board: {board.fen()}")
        top_move = sorted(ps.items(), key = lambda x : x[1])[-1][0]
        move_dat = {
                'model_move': top_move,
                'top_p' : ps[top_move],
            }
        try:
            move_dat['act_p'] = ps[row['move']]
        except KeyError:
            move_dat['act_p'] = 0.
        try:
            second_move = sorted(ps.items(), key = lambda x : x[1])[-2][0]
            move_dat['second_move'] = second_move
            move_dat['second_p'] = ps[second_move]
        except IndexError:
            pass
        return (v,
                move_dat,
                row,
                self.name,
                self.display_name,
                )

class CSV_writer(backend.MultiprocWorker):
    def __init__(self, output_path, player_name):
        self.output_path = output_path
        self.player_name = player_name if player_name is not None else ''
        self.f = bz2.open(self.output_path, 'wt')
        self.writer = csv.DictWriter(self.f,
            ['game_id', 'move_ply', 'player_move', 'model_move', 'model_v', 'model_correct', 'model_name', 'model_display_name', 'player_name', 'rl_depth', 'top_p', 'act_p', 'second_move', 'second_p'
            ])
        self.writer.writeheader()
        self.c = 0

    def __del__(self):
        try:
            self.f.close()
        except:
            pass

    def __call__(self, v, move_dat, row, name, display_name):
        write_dict = {
                'game_id' : row['game_id'],
                'move_ply' : row['move_ply'],
                'player_move' : row['move'],
                'model_correct' : row['move'] == move_dat['model_move'],
                'model_name' : name,
                'model_display_name' : display_name,
                'player_name' : self.player_name,
                'rl_depth' : 0,
                'model_v' : v
                }
        write_dict.update(move_dat)
        self.writer.writerow(write_dict)
        self.c += 1
        if self.c % 10000 == 0:
            self.f.flush()

if __name__ == "__main__":
    main()
