import functools
import sys
import time
import datetime
import os
import os.path
import traceback

import pytz


min_run_time = 60 * 10 # 10 minutes
infos_dir_name = 'runinfos'
tz = pytz.timezone('Canada/Eastern')

colours = {
    'blue' : '\033[94m',
    'green' : '\033[92m',
    'yellow' : '\033[93m',
    'red' : '\033[91m',
    'pink' : '\033[95m',
}
endColour = '\033[0m'

def printWithDate(s, colour = None, **kwargs):
    if colour is None:
        print(f"{datetime.datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')} {s}", **kwargs)
    else:
        print(f"{datetime.datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')}{colours[colour]} {s}{endColour}", **kwargs)

class Tee(object):
    #Based on https://stackoverflow.com/a/616686
    def __init__(self, fname, is_err = False):
        self.file = open(fname, 'a')
        self.is_err = is_err
        if is_err:
            self.stdstream = sys.stderr
            sys.stderr = self
        else:
            self.stdstream = sys.stdout
            sys.stdout = self
    def __del__(self):
        if self.is_err:
            sys.stderr = self.stdstream
        else:
            sys.stdout = self.stdstream
        self.file.close()
    def write(self, data):
        self.file.write(data)
        self.stdstream.write(data)
    def flush(self):
        self.file.flush()

class LockedName(object):
    def __init__(self, script_name, start_time):
        self.script_name = script_name
        self.start_time = start_time
        os.makedirs(infos_dir_name, exist_ok = True)
        os.makedirs(os.path.join(infos_dir_name, self.script_name), exist_ok = True)

        self.file_prefix = self.get_name_prefix()
        self.full_prefix = self.file_prefix + f"-{start_time.strftime('%Y-%m-%d-%H%M')}_"
        self.lock = None
        self.lock_name = None

    def __enter__(self):
        try:
            self.lock_name = self.file_prefix + '.lock'
            self.lock = open(self.lock_name, 'x')
        except FileExistsError:
            self.file_prefix = self.get_name_prefix()
            self.full_prefix = self.file_prefix + f"-{start_time.strftime('%Y-%m-%d-%H%M')}_"
            return self.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        try:
            self.lock.close()
            os.remove(self.lock_name)
        except:
            pass

    def get_name_prefix(self):
        fdir = os.path.join(infos_dir_name, self.script_name)
        prefixes = [n.name.split('-')[0] for n in os.scandir(fdir) if n.is_file()]
        file_num = 1
        nums = []
        for p in set(prefixes):
            try:
                nums.append(int(p))
            except ValueError:
                pass
        if len(nums) > 0:
            file_num = max(nums) + 1

        return os.path.join(fdir, f"{file_num:04.0f}")

def logged_main(mainFunc):
    @functools.wraps(mainFunc)
    def wrapped_main(*args, **kwds):
        start_time = datetime.datetime.now(tz)
        script_name = os.path.basename(sys.argv[0])[:-3]

        with LockedName(script_name, start_time) as name_lock:
            tee_out = Tee(name_lock.full_prefix + 'stdout.log', is_err = False)
            tee_err = Tee(name_lock.full_prefix + 'stderr.log', is_err = True)
            logs_prefix = name_lock.full_prefix
            printWithDate(' '.join(sys.argv), colour = 'blue')
            printWithDate(f"Starting {script_name}", colour = 'blue')
        try:
            tstart = time.time()
            val = mainFunc(*args, **kwds)
        except (Exception, KeyboardInterrupt) as e:
            printWithDate(f"Error encountered", colour = 'blue')
            if (time.time() - tstart) > min_run_time:
                makeLog(logs_prefix, start_time, tstart, True, 'Error', e, traceback.format_exc())
            raise
        else:
            printWithDate(f"Run completed", colour = 'blue')
            if (time.time() - tstart) > min_run_time:
                makeLog(logs_prefix, start_time, tstart, False, 'Successful')
        tee_out.flush()
        tee_err.flush()
        return val
    return wrapped_main

def makeLog(logs_prefix, start_time, tstart, is_error, *notes):
    fname = f'error.log' if is_error else f'run.log'
    with open(logs_prefix + fname, 'w') as f:
        f.write(f"start: {start_time.strftime('%Y-%m-%d-%H:%M:%S')}\n")
        f.write(f"stop: {datetime.datetime.now(tz).strftime('%Y-%m-%d-%H:%M:%S')}\n")
        f.write(f"duration: {int(tstart > min_run_time)}s\n")
        f.write(f"dir: {os.path.abspath(os.getcwd())}\n")
        f.write(f"{' '.join(sys.argv)}\n")
        f.write('\n'.join([str(n) for n in notes]))
