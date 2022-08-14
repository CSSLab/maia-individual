import multiprocessing
import collections.abc
import time
import sys
import traceback
import functools
import pickle

class Multiproc(object):
    def __init__(self, num_procs, max_queue_size = 1000, proc_check_interval = .1):
        self.num_procs = num_procs
        self.max_queue_size = max_queue_size
        self.proc_check_interval = proc_check_interval

        self.reader = MultiprocIterable
        self.reader_args = []
        self.reader_kwargs = {}

        self.processor = MultiprocWorker
        self.processor_args = []
        self.processor_kwargs = {}

        self.writer = MultiprocWorker
        self.writer_args = []
        self.writer_kwargs = {}

    def reader_init(self, reader_cls, *reader_args, **reader_kwargs):
        self.reader = reader_cls
        self.reader_args = reader_args
        self.reader_kwargs = reader_kwargs

    def processor_init(self, processor_cls, *processor_args, **processor_kwargs):
        self.processor = processor_cls
        self.processor_args = processor_args
        self.processor_kwargs = processor_kwargs

    def writer_init(self, writer_cls, *writer_args, **writer_kwargs):
        self.writer = writer_cls
        self.writer_args = writer_args
        self.writer_kwargs = writer_kwargs


    def run(self):
        with multiprocessing.Pool(self.num_procs + 2) as pool, multiprocessing.Manager() as manager:
            inputQueue = manager.Queue(self.max_queue_size)
            resultsQueue = manager.Queue(self.max_queue_size)
            reader_proc = pool.apply_async(reader_loop, (inputQueue, self.num_procs, self.reader, self.reader_args, self.reader_kwargs))

            worker_procs = []
            for _ in range(self.num_procs):
                wp = pool.apply_async(processor_loop, (inputQueue, resultsQueue, self.processor, self.processor_args, self.processor_kwargs))
                worker_procs.append(wp)

            writer_proc = pool.apply_async(writer_loop, (resultsQueue, self.num_procs, self.writer, self.writer_args, self.writer_kwargs))

            self.cleanup(reader_proc, worker_procs, writer_proc)

    def cleanup(self, reader_proc, worker_procs, writer_proc):
        reader_working = True
        processor_working = True
        writer_working = True
        while reader_working or processor_working or writer_working:
            if reader_working and reader_proc.ready():
                reader_proc.get()
                reader_working = False

            if processor_working:
                new_procs = []
                for p in worker_procs:
                    if p.ready():
                        p.get()
                    else:
                        new_procs.append(p)
                if len(new_procs) < 1:
                    processor_working = False
                else:
                    worker_procs = new_procs

            if writer_working and writer_proc.ready():
                writer_proc.get()
                writer_working = False
            time.sleep(self.proc_check_interval)

def catch_remote_exceptions(wrapped_function):
    """ https://stackoverflow.com/questions/6126007/python-getting-a-traceback """

    @functools.wraps(wrapped_function)
    def new_function(*args, **kwargs):
        try:
            return wrapped_function(*args, **kwargs)

        except:
            raise Exception( "".join(traceback.format_exception(*sys.exc_info())) )

    return new_function

@catch_remote_exceptions
def reader_loop(inputQueue, num_workers, reader_cls, reader_args, reader_kwargs):
    with reader_cls(*reader_args, **reader_kwargs) as R:
        for dat in R:
            inputQueue.put(dat)
    for i in range(num_workers):
        inputQueue.put(_QueueDone(count = i))

@catch_remote_exceptions
def processor_loop(inputQueue, resultsQueue, processor_cls, processor_args, processor_kwargs):
    with processor_cls(*processor_args, **processor_kwargs) as Proc:
        while True:
            dat = inputQueue.get()
            if isinstance(dat, _QueueDone):
                resultsQueue.put(dat)
                break
            try:
                if isinstance(dat, tuple):
                    procced_dat = Proc(*dat)
                else:
                    procced_dat = Proc(dat)
            except SkipCallMultiProc:
                pass
            except:
                raise
            resultsQueue.put(procced_dat)

@catch_remote_exceptions
def writer_loop(resultsQueue, num_workers, writer_cls, writer_args, writer_kwargs):
    complete_workers = 0
    with writer_cls(*writer_args, **writer_kwargs) as W:
        if W is None:
            raise AttributeError(f"Worker was created, but closure failed to form")
        while complete_workers < num_workers:
            dat = resultsQueue.get()
            if isinstance(dat, _QueueDone):
                complete_workers += 1
            else:
                if isinstance(dat, tuple):
                    W(*dat)
                else:
                    W(dat)

class SkipCallMultiProc(Exception):
    pass

class _QueueDone(object):
    def __init__(self, count = 0):
        self.count = count

class MultiprocWorker(collections.abc.Callable):

    def __call__(self, *args):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass

class MultiprocIterable(MultiprocWorker, collections.abc.Iterator):
    def __next__(self):
        raise StopIteration

    def __call__(self, *args):
        return next(self)
