import os
import io
import sys
import json
import time
import struct
import pickle
import weakref
import errno
import logging
import threading
from typing import *
from queue import Empty
from threading import Thread
from copy import deepcopy
from multiprocessing import queues, Process, context, resource_tracker
from multiprocessing.queues import Queue

# 这里 IDE 会检查错误，忽略
from multiprocessing.util import debug, info, Finalize, register_after_fork, \
    is_exiting
from multiprocessing.shared_memory import SharedMemory

from watch_dog.utils.util_log import set_scripts_logging, time_cost_log
from watch_dog.utils.util_stack import find_caller
from watch_dog.utils.util_process import new_process


@new_process()
def clear_queue_cache_async(queue: Queue, queue_msg=None):
    clear_queue_cache(queue, queue_msg=queue_msg)


def clear_queue_cache_by_process(queue: Queue, queue_msg=None):
    worker = Process(target=clear_queue_cache, args=(queue,),
                     kwargs=dict(queue_msg=queue_msg))
    worker.start()
    return worker


def clear_queue_by_process(queue: Queue, queue_msg=None,
                           wait_clear_again=0):
    worker = Process(target=clear_queue, args=(queue,),
                     kwargs=dict(queue_msg=queue_msg,
                                 wait_clear_again=wait_clear_again))
    worker.start()
    return worker


def clear_queue_by_thread(queue: Queue, queue_msg=None,
                          wait_clear_again=0):
    worker = Thread(target=clear_queue, args=(queue,),
                    kwargs=dict(queue_msg=queue_msg,
                                wait_clear_again=wait_clear_again))
    worker.start()
    return worker


def clear_queue_cache_by_thread(queue: Queue, queue_msg=None):
    worker = Thread(target=clear_queue_cache, args=(queue,),
                    kwargs=dict(queue_msg=queue_msg))
    worker.start()
    return worker


@time_cost_log
def clear_queue_cache(queue: Queue, queue_msg=None, time_out=0.01):
    buffer_size = queue.qsize()
    if queue_msg is None and hasattr(queue, "name"):
        queue_msg = getattr(queue, "name")

    logging.info(f"[clear_queue_cache]: {queue_msg}, caller: {find_caller()}, "
                 f"buffer_size: {buffer_size} ")
    if not buffer_size:
        return
    logging.info(f"[clear_queue_cache]: pid:　{os.getpid()} "
                 f"Detect queue-{queue_msg} buffer, "
                 f"buffer size: {buffer_size}, clearing ....")
    clear_count = 0
    empty_try_time = 3
    for _ in range(buffer_size):
        try:
            logging.info(f"{queue_msg} getting queue, "
                         f"timeout: {time_out}, qsize: {queue.qsize()}")
            queue.get(timeout=time_out)
            logging.info(f"{queue_msg} get queue done")
            clear_count += 1
            logging.info(f"[clear_queue_cache]:Cleared-{queue_msg} "
                         f"{clear_count} buffer, buffer remain {queue.qsize()}")
        except Empty:
            print(f"{queue_msg} empty")
            if empty_try_time > 0:
                empty_try_time -= 1
                continue
            else:
                break

    logging.info(f"[clear_queue_cache]: Queue-{queue_msg}"
                 f" buffer clear complete")


@time_cost_log
def clear_queue(queue: Queue, time_out=0.5, wait_clear_again=0,
                queue_msg=None):
    """

    :param queue:
    :param time_out: 默认为 0.5, 为了保证清除干净
    :param wait_clear_again: 秒 , 等待这么多秒后，再清理一次
    :param queue_msg: 秒 , 等待这么多秒后，再清理一次
    :return:
    """
    logging.info(f"[clear_queue]: caller: {find_caller()}")
    i = 0
    while True:
        try:
            queue.get(timeout=time_out)
            logging.debug(f"[clear_queue]Cleared-{queue_msg} {i + 1} buffer, "
                          f"buffer remain {queue.qsize()}")
            i += 1
        except Empty:
            break

    logging.debug(f"[clear_queue]Queue-{queue_msg} buffer clear complete")
    if wait_clear_again > 0:
        time.sleep(0.01)
        clear_queue(queue, time_out=time_out, queue_msg=queue_msg,
                    wait_clear_again=wait_clear_again - 1)


class Pickle5(object):
    PROTOCOL = 5

    def __init__(self, use_out_band=False):
        self._use_out_band = use_out_band

    def dumps(self, obj):
        buf = io.BytesIO()
        buffers = []

        def _buffer_callback(b):
            return buffers.append(b.raw())

        buffer_callback = _buffer_callback if self._use_out_band else None
        pickle.Pickler(buf, protocol=pickle.HIGHEST_PROTOCOL,
                       buffer_callback=buffer_callback).dump(obj)
        obj = buf.getbuffer()
        return obj, buffers

    # @time_cost_log
    def loads(self, obj_p, buffers=None):
        if not self._use_out_band and buffers is not None:
            buffers = None

        file = io.BytesIO(obj_p)
        return pickle.Unpickler(file, buffers=buffers).load()


class SharedBufferHeader(object):

    def __init__(self, shared_name, shared_size,
                 memory_views_ranges: List[Tuple[int, int]],
                 **kwargs):
        self.shared_name = shared_name
        self.memory_views_ranges = memory_views_ranges
        self.shared_size = shared_size

        self._buf_memory_views: List[memoryview] = None
        self._shared_mem: Optional[SharedMemory] = None
        self._recv_datas = None

    # @time_cost_log_with_desc(min_cost=0.5)
    def __enter__(self):
        self._buf_memory_views, self._shared_mem = self.recv_from_shared_mem()

    # @time_cost_log_with_desc(min_cost=0.5)
    def __exit__(self, exc_type, exc_val, exc_tb):
        # start = time.perf_counter()
        if self._buf_memory_views is not None:
            del self._buf_memory_views
        # print(f"t1 cost: {round((time.perf_counter() - start) * 1000)} ms")
        if self._recv_datas is not None:
            del self._recv_datas

        # print(f"t2 cost: {round((time.perf_counter() - start) * 1000)} ms")

        def _release():
            if self._shared_mem is not None:
                self._shared_mem.close()
                self._shared_mem.unlink()

        # _release()
        threading.Thread(target=_release).start()
        # print(f"t3 cost: {round((time.perf_counter() - start) * 1000)} ms")

    def pickle_load(self, pickle_engine: Pickle5, datas, abandon=False):
        """ call in `with context` """
        self._recv_datas = pickle_engine.loads(
            datas, buffers=self._buf_memory_views)
        # start = time.perf_counter()
        if abandon:
            return None

        recv_datas = deepcopy(self._recv_datas)
        # print(f"copy cost: {round((time.perf_counter() - start) * 1000)} ms")
        return recv_datas

    def pack_header(self):
        buf_headers = json.dumps(self.__dict__).encode()
        buf_headers_len = len(buf_headers)
        buf_headers_len_pack = struct.pack("Q", buf_headers_len)
        return buf_headers_len_pack + buf_headers

    @classmethod
    def unpack_header(cls, bytes_obj) -> Tuple["SharedBufferHeader", bytes]:
        headers_len = struct.unpack("Q", bytes_obj[0:8])[0]
        try:
            headers = json.loads(bytes_obj[8: 8 + headers_len])
        except Exception:
            print(bytes_obj)
            raise
        return SharedBufferHeader(**headers), bytes_obj[8 + headers_len:]

    @classmethod
    def nbytes(cls, frame_or_memoryview, _bytes_like=(bytes, bytearray)):
        """Extract number of bytes of a frame or memoryview."""
        if isinstance(frame_or_memoryview, _bytes_like):
            return len(frame_or_memoryview)
        else:
            try:
                return frame_or_memoryview.nbytes
            except AttributeError:
                return len(frame_or_memoryview)

    @classmethod
    def create_one(cls, mem_views: List[memoryview]) -> "SharedBufferHeader":
        lengths = [cls.nbytes(memory_view) for memory_view in mem_views]

        memory_views_ranges = []
        memory_views_size = sum(lengths)
        if memory_views_size == 0:
            memory_views_size = 1
        shared_mem = SharedMemory(create=True, size=memory_views_size)

        write_offset = 0
        for i, length in enumerate(lengths):
            write_end = write_offset + length
            memory_views_ranges.append((write_offset, write_end))
            shared_mem.buf[write_offset:write_end] = mem_views[i]
            write_offset = write_end

        # clean up
        shared_mem.close()
        return SharedBufferHeader(shared_name=shared_mem.name,
                                  shared_size=memory_views_size,
                                  memory_views_ranges=memory_views_ranges)

    def recv_from_shared_mem(self) -> Tuple[
        List[memoryview], SharedMemory]:
        shared_mem = SharedMemory(name=self.shared_name)
        datas = shared_mem.buf[:self.shared_size]
        memory_views = []
        for mem_view_range in self.memory_views_ranges:
            memory_view = datas[mem_view_range[0]: mem_view_range[1]]
            memory_views.append(memory_view)
        return memory_views, shared_mem


class FastQueue(Queue):
    """
    """
    if os.name == "posix":
        # 确保 resource_tracker 在 FastQueue 使用共享内存之前启动，
        # 防止多个子进程重复创建 resource_tracker 进程
        resource_tracker.ensure_running()

    def __init__(self, maxsize=0, name="queue", use_out_band=True):
        super().__init__(maxsize=maxsize, ctx=context._default_context)
        self.name = name
        self._use_out_band = use_out_band
        self._pickler = Pickle5(self._use_out_band)

    def abandon_one(self, block=True, timeout=None):
        return self.get(block=block, timeout=timeout, abandon=True)

    def get(self, block=True, timeout=None, abandon=False):

        if self._closed:
            raise ValueError(f"Queue {self!r} is closed")
        if block and timeout is None:
            with self._rlock:
                # start = time.perf_counter()
                res = self._recv_bytes()
            self._sem.release()
        else:
            if block:
                deadline = time.monotonic() + timeout
            if not self._rlock.acquire(block, timeout):
                raise Empty
            try:
                if block:
                    timeout = deadline - time.monotonic()
                    if not self._poll(timeout):
                        raise Empty
                elif not self._poll():
                    raise Empty
                # start = time.perf_counter()
                res = self._recv_bytes()
                self._sem.release()
            finally:
                self._rlock.release()
        # unserialize the data after having released the lock

        if self._use_out_band:
            buf_header, real_datas = SharedBufferHeader.unpack_header(res)

            with buf_header:
                recv_datas = buf_header.pickle_load(pickle_engine=self._pickler,
                                                    datas=real_datas,
                                                    abandon=abandon)
        else:
            recv_datas = self._pickler.loads(res)

        # cost = round((time.perf_counter() - start) * 1000, 2)
        # if cost > 1:
        #     print(f"test-{self.queue_name}, "
        #           f"\t\t\t unpickle cost: {cost} ms")
        return recv_datas

    def _start_thread(self):
        debug('Queue._start_thread()')

        # Start thread which transfers data from buffer to pipe
        self._buffer.clear()
        self._thread = threading.Thread(
            target=self._feed,
            args=(self._buffer, self._notempty, self._send_bytes,
                  self._wlock, self._writer.close, self._ignore_epipe,
                  self._on_queue_feeder_error, self._sem),
            name='QueueFeederThread'
        )
        self._thread.daemon = True

        debug('doing self._thread.start()')
        self._thread.start()
        debug('... done self._thread.start()')

        if not self._joincancelled:
            self._jointhread = Finalize(
                self._thread, Queue._finalize_join,
                [weakref.ref(self._thread)],
                exitpriority=-5
            )

        # Send sentinel to the thread queue object when garbage collected
        self._close = Finalize(
            self, Queue._finalize_close,
            [self._buffer, self._notempty],
            exitpriority=10
        )

    def _feed(self, buffer, notempty, send_bytes, writelock, close,
              ignore_epipe,
              onerror, queue_sem):
        debug('starting thread to feed data to pipe')
        nacquire = notempty.acquire
        nrelease = notempty.release
        nwait = notempty.wait
        bpopleft = buffer.popleft
        sentinel = queues._sentinel
        if sys.platform != 'win32':
            wacquire = writelock.acquire
            wrelease = writelock.release
        else:
            wacquire = None

        while 1:
            try:
                nacquire()
                try:
                    if not buffer:
                        nwait()
                finally:
                    nrelease()
                try:
                    while 1:
                        obj = bpopleft()
                        if obj is sentinel:
                            debug('feeder thread got sentinel -- exiting')
                            close()
                            return

                        if self.name == "analysis":
                            print(f"{obj.__dict__}, {obj}")

                        # serialize the data before acquiring the lock
                        # start = time.perf_counter()
                        obj, buf_mem_views = self._pickler.dumps(obj)
                        # cost = round((time.perf_counter() - start) * 1000, 2)
                        # if cost > 1:
                        #     print(f"test-{self.queue_name}, "
                        #           f"pickle cost: {cost} ms")

                        # if buf_mem_views:
                        if self._use_out_band:
                            shared_buf_header = SharedBufferHeader.create_one(
                                buf_mem_views)
                            buf_header_pack = shared_buf_header.pack_header()
                            obj = buf_header_pack + obj

                        if wacquire is None:
                            send_bytes(obj)
                        else:
                            wacquire()
                            try:
                                send_bytes(obj)
                            finally:
                                wrelease()
                except IndexError:
                    pass
            except Exception as e:
                if ignore_epipe and getattr(e, 'errno', 0) == errno.EPIPE:
                    return
                # Since this runs in a daemon thread the resources it uses
                # may be become unusable while the process is cleaning up.
                # We ignore errors which happen after the process has
                # started to cleanup.
                if is_exiting():
                    info('error in queue thread: %s', e)
                    return
                else:
                    # Since the object has not been sent in the queue, we need
                    # to decrease the size of the queue. The error acts as
                    # if the object had been silently removed from the queue
                    # and this step is necessary to have a properly working
                    # queue.
                    queue_sem.release()
                    onerror(e, obj)


if __name__ == "__main__":
    import multiprocessing as mp

    set_scripts_logging(__file__)

    test_queue = FastQueue()
    test_queue.put(323)
    t = test_queue.get()
    print("debug")
