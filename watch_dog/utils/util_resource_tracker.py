import os
import time
import atexit
import signal
import _posixshmem
import multiprocessing as mp
from queue import Queue, Empty
from threading import Lock, Thread
import psutil


class ResourceTracker(object):
    REGISTER_QUEUE = mp.Queue()
    UNREGISTER_QUEUE = mp.Queue()

    @classmethod
    def register(cls, name):
        cls.REGISTER_QUEUE.put(name)
        # cls.register_num.value += 1

    @classmethod
    def unregister(cls, name):
        cls.UNREGISTER_QUEUE.put(name)
        # cls.unregister_num.value += 1


def _keep_tracking():
    cache_map = {}
    lock = Lock()

    def _track_register():
        while True:
            name = ResourceTracker.REGISTER_QUEUE.get()
            with lock:
                cache_map[name] = 1

    def _track_unregister():
        while True:
            name = ResourceTracker.UNREGISTER_QUEUE.get()
            with lock:
                if name in cache_map:
                    cache_map.pop(name)

    def _tracking():
        while True:

            for _ in range(300):
                try:
                    name = ResourceTracker.REGISTER_QUEUE.get(timeout=1)
                    with lock:
                        cache_map[name] = 1
                except Empty:
                    pass
                try:
                    name = ResourceTracker.UNREGISTER_QUEUE.get(timeout=1)
                    with lock:
                        if name in cache_map:
                            cache_map.pop(name)
                except Empty:
                    pass
            time.sleep(10)

    def _clear_unregisters_at_exit(*args, **kwargs):
        while ResourceTracker.REGISTER_QUEUE.qsize() > 0:
            try:
                name = ResourceTracker.REGISTER_QUEUE.get(timeout=0.01)
                with lock:
                    cache_map[name] = 1
            except Empty:
                break

        unlinks = list(cache_map.keys())
        all_count = len(unlinks)
        if not all_count:
            return
        print(f"""
        ======================================================================
                Detect unlinked posix sharememory, size: {all_count}, 
                REGISTER_QUEUE: {ResourceTracker.REGISTER_QUEUE.qsize()}
                UNREGISTER_QUEUE: {ResourceTracker.UNREGISTER_QUEUE.qsize()}
        ======================================================================
        """)
        removes = []
        unlink_num = 0
        already_unlinked_num = 0
        i = 0
        while i < all_count:
            name = unlinks[i]
            try:
                _posixshmem.shm_unlink(name)
                print(f"unlinked {name}, id: {i + 1}, all: {all_count}")
                unlink_num += 1
                i += 1
                removes.append(name)
            except FileNotFoundError:
                print(f"already unlinked, pass: id: {i + 1}, all: {all_count}")
                already_unlinked_num += 1
                i += 1
                removes.append(name)
            except KeyboardInterrupt:
                pass

        for name in removes:
            cache_map.pop(name)

        print(f"""
        ======================================================================
                Finish unlink posix sharememory
                    detect size: {all_count}
                    unliked size: {unlink_num}
                    already unlinked size: {already_unlinked_num}
                    REGISTER_QUEUE: {ResourceTracker.REGISTER_QUEUE.qsize()}
                    UNREGISTER_QUEUE: {ResourceTracker.UNREGISTER_QUEUE.qsize()}
        ======================================================================
        """)
        exit(0)

    signal.signal(signal.SIGINT, _clear_unregisters_at_exit)
    signal.signal(signal.SIGTERM, _clear_unregisters_at_exit)

    try:
        Thread(target=_track_register, daemon=True).start()
        _track_unregister()
    except KeyboardInterrupt:
        _clear_unregisters_at_exit(0)
    finally:
        _clear_unregisters_at_exit(1)
        print("resource tracker exit !!!")


tracker = mp.Process(target=_keep_tracking)
tracker.start()


def _ensure_kill_tracker_at_exit():
    os.kill(tracker.pid, signal.SIGINT)
    os.waitpid(tracker.pid, 0)


atexit.register(_ensure_kill_tracker_at_exit)

if __name__ == "__main__":
    def test():
        time.sleep(100)


    mp.Process(target=test).start()

    print("start")
    time.sleep(5)
    print("end")
