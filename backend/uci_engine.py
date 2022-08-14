import subprocess
import os.path
import re
import datetime
import concurrent

import yaml

import chess
import chess.engine
import chess.pgn

from .utils import tz
#from .proto import Board, Node, Game

p_re = re.compile(r"(\S+) [^P]+P\: +([0-9.]+)")

#You will probably need to set these manually

lc0_path = 'lc0'

sf_path = 'stockfish'

def model_from_config(config_dir_path, nodes = None):
    with open(os.path.join(config_dir_path, 'config.yaml')) as f:
        config = yaml.safe_load(f.read())

    if config['engine'] == 'stockfish':
        model = Stockfish_Engine(**config['options'])

    elif config['engine'] in ['lc0', 'lc0_23']:
        config['options']['weightsPath'] = os.path.join(config_dir_path, config['options']['weightsPath'])
        if nodes is not None:
            config['options']['nodes'] = nodes
        model = LC0_Engine(**config['options'])
    else:
        raise NotImplementedError(f"{config['engine']} is not a known engine type")

    model.config = config

    return model

class Shallow_Board_Query(Exception):
    pass

def is_shallow_board(board):
    #https://github.com/niklasf/python-chess/blob/master/chess/engine.py#L1183
    if len(board.move_stack) < 1 and board.fen().split()[0] != chess.STARTING_BOARD_FEN:
        return True
    return False


class UCI_Engine(object):
    def __init__(self, engine, movetime = None, nodes = None, depth = None):
        self.engine = engine
        self.limits = chess.engine.Limit(
            time = movetime,
            depth = depth,
            nodes = nodes,
        )
        self.config = None
        self.query_counter = 0

    def __del__(self):
        try:
            try:
                self.engine.quit()
            except (chess.engine.EngineTerminatedError, concurrent.futures._base.TimeoutError):
                pass
        except AttributeError:
            pass

    def getMove(self, board, allow_shallow = False):
        return self.board_info(board, multipv = 1, allow_shallow = allow_shallow)[0][0]

    def board_info(self, board, multipv = 1, allow_shallow = False):
        """Basic board info"""
        if is_shallow_board(board) and not allow_shallow:
            raise Shallow_Board_Query(f"{board.fen()} has no history")
        r = self.engine.analyse(
                board,
                self.limits,
                multipv = multipv,
                info = chess.engine.INFO_ALL,
                game = self.query_counter,
                )
        self.query_counter += 1
        return [(p['pv'][0], p) for p in r]

    def board_info_full(self, board, multipv = 1, allow_shallow = False):
        """All the info string stuff"""
        if is_shallow_board(board) and not allow_shallow:
            raise Shallow_Board_Query(f"{board.fen()} has no history")
        r = self.engine.analysis(
                board,
                self.limits,
                multipv = multipv,
                info = chess.engine.INFO_ALL,
                game = self.query_counter,
                )
        self.query_counter += 1
        r.wait()
        info_strs = []
        while not r.empty():
            try:
                info_strs.append(r.get()['string'])
            except KeyError:
                pass
        return [(p['pv'][0], p) for p in r.multipv], '\n'.join(info_strs)

class LC0_Engine(UCI_Engine):
    def __init__(self, weightsPath, movetime = None, nodes = 1, depth = None, binary_path = lc0_path, threads = 2):
        E = chess.engine.SimpleEngine.popen_uci([binary_path, '-w', weightsPath, '--verbose-move-stats', f'--threads={threads}'], stderr=subprocess.DEVNULL)

        super().__init__(E, movetime = movetime, nodes = nodes, depth = depth)

    def board_parsed_p_values(self, board, allow_shallow = False):
        dat, info_str = self.board_info_full(board, multipv = 1, allow_shallow = allow_shallow)
        p_vals = {}
        for l in info_str.split('\n'):
            r = p_re.match(l)
            p_vals[r.group(1)] = float(r.group(2))
        return dat, p_vals

    def board_pv(self, board, allow_shallow = False):
        d, p = self.board_parsed_p_values(board, allow_shallow = allow_shallow)
        return d[0][1]['score'].relative.cp, p

    def make_tree_node(self, board, depth = 2, width = 10, allow_shallow = False):
        N = Node()
        try:
            v, p_dict = self.board_pv(board, allow_shallow=allow_shallow)
        except KeyError:
            if board.is_game_over():
                N.depth = depth
                N.value = 0
                return N
            else:
                raise
        N.depth = depth
        N.value = v
        children = sorted(p_dict.items(), key = lambda x : x[1], reverse=True)[:width]
        N.child_values.extend([p for m, p in children])
        N.child_moves.extend([m for m, p in children])
        chunks = []
        if depth > 0:
            for m, pv in children:
                b = board.copy()
                b.push_uci(m)
                chunks.append(self.make_tree_node(b, depth = depth - 1, width = width, allow_shallow=allow_shallow))
        N.children.extend(chunks)
        return N

    def make_game_file(self, game, depth = 2, width = 10, intial_skip = 4, allow_shallow = False):
        G = Game()
        G.game_id = game.headers['Site'].split('/')[-1]
        G.black_elo = int(game.headers['BlackElo'])
        G.white_elo = int(game.headers['WhiteElo'])
        boards = []
        for i, (mm, mb) in list(enumerate(zip(list(game.mainline())[1:], list(game.mainline())[:-1])))[intial_skip:-1]:
            board = mb.board()
            b_node = self.make_tree_node(board, depth = depth, width = width, allow_shallow = allow_shallow)
            proto_board = Board()
            proto_board.tree.MergeFrom(b_node)
            proto_board.fen = mb.board().fen()
            proto_board.ply = i
            proto_board.move = str(mm.move)
            try:
                proto_board.move_index = list(b_node.child_moves).index(str(mm.move))
            except ValueError:
                proto_board.move_index = -1
            boards.append(proto_board)
        G.boards.extend(boards)
        return G

class Stockfish_Engine(UCI_Engine):
    def __init__(self, movetime = None, nodes = None, depth = 15, binary_path = sf_path, threads = 2, hash = 256):
        E = chess.engine.SimpleEngine.popen_uci([binary_path])

        super().__init__(E, movetime = movetime, nodes = nodes, depth = depth)
        self.engine.configure({"Threads": threads, "Hash": hash})

def play_game(E1, E2, round = None, startingFen = None, notes = None):

    timeStarted = datetime.datetime.now(tz)
    i = 0
    if startingFen is not None:
        board = chess.Board(fen=startingFen)
    else:
        board = chess.Board()

    players = [E1, E2]

    while not board.is_game_over():
        E = players[i % 2]
        board.push(E.getMove(board))
        i += 1
    pgnGame = chess.pgn.Game.from_board(board)

    pgnGame.headers['Event'] = f"{E1.config['name']} vs {E2.config['name']}"
    pgnGame.headers['White'] = E1.config['name']
    pgnGame.headers['Black'] = E2.config['name']
    pgnGame.headers['Date'] = timeStarted.strftime("%Y-%m-%d %H:%M:%S")
    if round is not None:
        pgnGame.headers['Round'] = round
    if notes is not None:
        for k, v in notes.items():
            pgnGame.headers[k] = v
    return pgnGame
