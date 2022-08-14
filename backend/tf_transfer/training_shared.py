from ..utils import printWithDate

import tensorflow as tf

import glob
import os
import os.path
import random
import gzip
import sys

def get_latest_chunks(path):
    chunks = []
    printWithDate(f"found {glob.glob(path)} chunk dirs")
    whites = []
    blacks = []

    for d in glob.glob(path):
        for root, dirs, files in os.walk(d):
            for fpath in files:
                if fpath.endswith('.gz'):
                    #TODO: Make less sketchy
                    if 'black' in root:
                        blacks.append(os.path.join(root, fpath))
                    elif 'white' in root:
                        whites.append(os.path.join(root, fpath))
                    else:
                        raise RuntimeError(
                            f"invalid chunk path found:{os.path.join(root, fpath)}")

        printWithDate(
            f"found {len(whites)} white {len(blacks)} black chunks", end='\r')
    printWithDate(f"found {len(whites) + len(blacks)} chunks total")
    if len(whites) < 1 or len(blacks) < 1:
        print("Not enough chunks {}".format(len(blacks)))
        sys.exit(1)

    print("sorting {} B chunks...".format(len(blacks)), end='')
    blacks.sort(key=os.path.getmtime, reverse=True)
    print("sorting {} W chunks...".format(len(whites)), end='')
    whites.sort(key=os.path.getmtime, reverse=True)
    print("[done]")
    print("{} - {}".format(os.path.basename(whites[-1]), os.path.basename(whites[0])))
    print("{} - {}".format(os.path.basename(blacks[-1]), os.path.basename(blacks[0])))
    random.shuffle(blacks)
    random.shuffle(whites)
    return whites, blacks


class FileDataSrc:
    """
        data source yielding chunkdata from chunk files.
    """
    def __init__(self, white_chunks, black_chunks):
        self.white_chunks = []
        self.white_done = white_chunks

        self.black_chunks = []
        self.black_done = black_chunks

        self.next_is_white = True

    def next(self):
        self.next_is_white = not self.next_is_white
        return self.next_by_colour(not self.next_is_white)

    def next_by_colour(self, is_white):
        if is_white:
            if not self.white_chunks:
                self.white_chunks, self.white_done = self.white_done, self.white_chunks
                random.shuffle(self.white_chunks)
            if not self.white_chunks:
                return None
            while len(self.white_chunks):
                filename = self.white_chunks.pop()
                try:
                    with gzip.open(filename, 'rb') as chunk_file:
                        self.white_done.append(filename)
                        return chunk_file.read(), True
                except:
                    print("failed to parse {}".format(filename))
        else:
            if not self.black_chunks:
                self.black_chunks, self.black_done = self.black_done, self.black_chunks
                random.shuffle(self.black_chunks)
            if not self.black_chunks:
                return None, False
            while len(self.black_chunks):
                filename = self.black_chunks.pop()
                try:
                    with gzip.open(filename, 'rb') as chunk_file:
                        self.black_done.append(filename)
                        return chunk_file.read(), False
                except:
                    print("failed to parse {}".format(filename))

