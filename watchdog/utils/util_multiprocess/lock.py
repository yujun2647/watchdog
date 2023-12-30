import os
import time
import logging
import threading
import multiprocessing as mp

from watchdog.utils.util_stack import get_invoke_stacks_str

multi_lock_logger = logging.getLogger("multi_lock")
unit_test_logger = logging.getLogger("unit_test")


class BetterRLock(object):
    """
        在 原生 RLock 基础上,
            - 支持其他线程释放锁, 为了防止锁一直被卡死线程占用情况.
            - 支持 locked

    """

    def __init__(self, lock_name="default"):
        # 实际操作锁
        self._lock = mp.Lock()
        # 锁的别名
        self.lock_name = lock_name

        # 成功 acquire 的 操作id， 多进程共享变量
        self._acquired_id = mp.Value("d", 0)
        # 上一次成功 acquire 的操作id
        self._last_acquired_id = mp.Value("d", 0)

        # 成功 acquire 的进程 id
        self._acquire_pid = mp.Value("i", 0)

        # ------ 处理单线程中嵌套获取锁，造成的死锁问题，这里这种情况是因为，共享变量的获取，
        # ------ 在单线程里，一个锁操作中，很容易需要获取别的共享变量，比如日志记录状态信息，
        # ------ 这个状态信息可能就是需要获取锁的，如果不管很容易造成死锁，为此这里专门处理
        # ------ 这种情况，避免单线程中，重复获取锁导致的死锁问题

        # 当前线程尝试 acquire 的操作 id, 不一定 acquire 成功
        # 如果 acquire 成功，则赋值给 acquired_id
        self.__try_acquire_id = threading.local()
        self.__try_acquire_id.aid = 0

        # 当前线程是否已经上锁了
        self.__now_thread_locked = threading.local()
        self.__now_thread_locked.locked = False

        # 当前线程历史 _try_acquire_id
        self.__history_try_acquire_ids = threading.local()

    @property
    def _now_thread_locked(self):
        if not hasattr(self.__now_thread_locked, "locked"):
            self.__now_thread_locked.locked = False
        return self.__now_thread_locked.locked

    @_now_thread_locked.setter
    def _now_thread_locked(self, locked: bool):
        self.__now_thread_locked.locked = locked

    @property
    def _try_acquire_id(self):
        if not hasattr(self.__try_acquire_id, "aid"):
            self.__try_acquire_id.aid = 0
        return self.__try_acquire_id.aid

    @_try_acquire_id.setter
    def _try_acquire_id(self, aid: int):
        self.__try_acquire_id.aid = aid

    @property
    def _history_try_acquire_ids(self):
        if not hasattr(self.__history_try_acquire_ids, "ids"):
            self.__history_try_acquire_ids.ids = []
        return self.__history_try_acquire_ids.ids

    @property
    def acquired_id(self):
        return int(self._acquired_id.value)

    @property
    def last_acquired_id(self):
        return int(self._last_acquired_id.value)

    @acquired_id.setter
    def acquired_id(self, aid: int):
        self._acquired_id.value = aid

    @last_acquired_id.setter
    def last_acquired_id(self, aid: int):
        self._last_acquired_id.value = aid

    @property
    def acquire_pid(self):
        return self._acquire_pid.value

    @acquire_pid.setter
    def acquire_pid(self, pid: int):
        self._acquire_pid.value = pid

    def acquire(self, timeout=-1):
        # 当前线程已经尝试获取锁了，当前尝试再试获取锁，需要需要将操作id 入栈记录
        if self._try_acquire_id > 0:
            self._history_try_acquire_ids.insert(0, self._try_acquire_id)

        self._try_acquire_id = int(time.time() * 1000000)
        unit_test_logger.debug(f"pid: {os.getpid()} : try to acquire lock, "
                               f"_try_acquire_id: {self._try_acquire_id}")

        # 当前线程已经获取锁了，这里应禁止再次获取锁
        if self._now_thread_locked:
            # 告诉外部，获取锁失败，应禁止后续动作
            unit_test_logger.debug(
                f"pid: {os.getpid()} : now_thread_locked, try acquire failed "
                f"true_try_acquire_id: {self._history_try_acquire_ids[0]} "
                f"now_acquired_id: {self.acquired_id}, "
                f"last_acquired_id: {self.last_acquired_id}")
            return False

        # 获取锁，应该先获取锁，再更新包装后的各个状态变量，这样其他进行，就会阻塞在这里，
        # 不会再次更新状态变量
        acquire_result = self._lock.acquire(timeout=timeout)
        if not acquire_result:
            return acquire_result
        self.acquire_pid = os.getpid()
        self.acquired_id = self._try_acquire_id
        self._now_thread_locked = True

        multi_lock_logger.info(
            f"[Acquire lock] acquire_pid: {self.acquire_pid} "
            f"acquire_id: {self.acquired_id}, "
            f"last_acquire_id: {self.last_acquired_id}"
            f"invoker_stacks: {get_invoke_stacks_str()}")

        return acquire_result

    def release(self):
        try:
            self._lock.release()
        except ValueError:
            pass

    def __enter__(self):
        # 当前线程已经尝试获取锁了，当前尝试再试获取锁，需要需要将操作id 入栈记录
        if self._try_acquire_id > 0:
            self._history_try_acquire_ids.insert(0, self._try_acquire_id)

        self._try_acquire_id = int(time.time() * 1000000)
        unit_test_logger.debug(f"pid: {os.getpid()} : try to acquire lock, "
                               f"_try_acquire_id: {self._try_acquire_id}")

        # 当前线程已经获取锁了，这里应禁止再次获取锁
        if self._now_thread_locked:
            # 告诉外部，获取锁失败，应禁止后续动作
            unit_test_logger.debug(
                f"pid: {os.getpid()} : now_thread_locked, try acquire failed "
                f"true_try_acquire_id: {self._history_try_acquire_ids[0]} "
                f"now_acquired_id: {self.acquired_id}, "
                f"last_acquired_id: {self.last_acquired_id}")
            return False

        # 获取锁，应该先获取锁，再更新包装后的各个状态变量，这样其他进行，就会阻塞在这里，
        # 不会再次更新状态变量
        acquire_success = self._lock.__enter__()
        self.acquire_pid = os.getpid()
        self.acquired_id = self._try_acquire_id
        self._now_thread_locked = True

        multi_lock_logger.info(
            f"[Acquire lock] acquire_pid: {self.acquire_pid} "
            f"acquire_id: {self.acquired_id}, "
            f"last_acquire_id: {self.last_acquired_id}"
            f"invoker_stacks: {get_invoke_stacks_str()}")

        return acquire_success

    def __exit__(self, exc_type, exc_val, exc_tb):
        """当发生同一线程重复获取锁的情况， 如
            with lock as acquire_success1:
                print("do process")
                with lock as acquire_success2:
                    print("do_process")

            由于已经在 __enter__ 处理了，acquire_success2 会是 False,
            那么，在 acquire_success2 这个 with 语句中，应禁止调用 release, 即禁止调用 __exit__
            通过 self._try_acquire_id == self.acquired_id 来判断

        """
        # 当且仅当， 当前线程尝试获取的 acquire id 与 当前实际 acquired id 一致时
        # 说明当前锁，属于本线程，可以执行 __exit__ 释放锁， 否则说明，当前锁不属于本线程
        # 不能执行 __exit__ 释放锁
        if self._try_acquire_id == self.acquired_id:
            multi_lock_logger.info(
                f"[Release lock] try_acquire_pid: {self._try_acquire_id}, "
                f"acquire_id: {self.acquired_id}, "
                f"last_acquire_id: {self.last_acquired_id}")
            # logging.info(
            #         f"[Release lock] acquire_pid: {self.acquire_pid} "
            #         f"acquire_id: {self.acquire_id}")
            self.acquire_pid = 0
            self.last_acquired_id = self.acquired_id
            self.acquired_id = 0

            # 本次锁获取-释放 已结束，重置相关变量
            self._history_try_acquire_ids.clear()
            self._try_acquire_id = 0
            self._now_thread_locked = False
            unit_test_logger.debug(f"pid: {os.getpid()}: release lock success， "
                                   f"_try_acquire_id: {self._try_acquire_id}, "
                                   f"acquired_id: {self.acquired_id}, "
                                   f"last_acquire_id: {self.last_acquired_id}")
            # 释放锁，应该清理完各个包装状态变量，再释放，因为释放锁的时刻，别的进程可能里会立即获得锁
            # 需要保证这个时刻，各个状态变量已经重置
            try:
                self._lock.__exit__(exc_type, exc_val, exc_tb)
            except ValueError:
                pass

        else:  # 不一致，说明当前锁不属于本线程， 需要将 self._try_acquire_id 恢复成上一个
            if len(self._history_try_acquire_ids) > 0:
                unit_test_logger.debug(
                    f"pid: {os.getpid()} : release lock failed, "
                    f"lock not belong to this _try_acquire_id, "
                    f"_try_acquire_id: {self._try_acquire_id} "
                    f"acquired_id: {self.acquired_id} ,"
                    f"last_acquire_id: {self.last_acquired_id}"
                    f"resume to last _try_acquire_id: "
                    f"{self._history_try_acquire_ids[0]}")
                self._try_acquire_id = self._history_try_acquire_ids.pop(0)
            else:
                logging.warning(
                    f"pid: {os.getpid()}, can not find last "
                    f"_try_acquire_id !!!!, "
                    f"_try_acquire_id: {self._try_acquire_id}, "
                    f"acquire_id：{self.acquired_id}, "
                    f"last_acquire_id: {self.last_acquired_id}, "
                    f"_history_try_acquire_ids: "
                    f"{self._history_try_acquire_ids}")

    @property
    def __dict__(self):
        return dict(
            lock_name=self.lock_name,
            last_acquire_pid=self.last_acquired_id,
            acquire_pid=self.acquire_pid,
            acquire_id=self.acquired_id,
            inner_lock=str(self._lock)
        )
