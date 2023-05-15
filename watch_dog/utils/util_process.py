import os
import signal
import time
import sys
import json
import atexit
import logging
import psutil
from typing import *
import threading
import multiprocessing as mp

from psutil import NoSuchProcess

from watch_dog.utils.util_stack import get_invoke_stacks_str
from watch_dog.utils.util_warning import ignore_assigned_error
from datetime import datetime, timedelta, timezone

multi_lock_logger = logging.getLogger("multi_lock")
unit_test_logger = logging.getLogger("unit_test")


def new_process(pro_cls=mp.Process, daemon=None, join=False):
    def outer_wrapper(func):
        def inner_wrapper(*args, **kwargs):
            worker = pro_cls(target=func, args=args, kwargs=kwargs,
                             daemon=daemon)
            worker.start()
            if join:
                worker.join()

        return inner_wrapper

    return outer_wrapper


class FakeLock(object):
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class ProcessController(object):
    """控制进程：可以暂停、恢复、杀死、重启"""

    @classmethod
    def pause_process(cls, pid: int):
        os.system(f"kill -STOP {pid}")
        logging.info(f"paused process: {pid}")

    @classmethod
    def resume_process_from_pause(cls, pid: int):
        os.system(f"kill -CONT {pid}")
        logging.info(f"resumed process from pause: {pid}")

    @classmethod
    @ignore_assigned_error((FileNotFoundError, NoSuchProcess))
    def kill_sub_processes(cls, pid=None, excludes=None):
        def _wait(_pid):
            os.waitpid(_pid, 0)

        if excludes is None:
            excludes = []
        pid = pid if pid is not None else os.getpid()
        if pid in excludes:
            return
        this_process = psutil.Process(pid)
        print(f"kill sub processes: {this_process.children()}")
        for child in this_process.children():
            # noinspection PyBroadException
            if child.pid in excludes:
                continue
            if child.children():
                cls.kill_sub_processes(child.pid, excludes=excludes)
            try:
                # 手动方案
                os.kill(child.pid, signal.SIGINT)
                t = threading.Thread(target=_wait, args=(child.pid,))
                try:
                    t.start()
                    t.join(timeout=1)
                finally:
                    if t.is_alive():
                        os.kill(child.pid, signal.SIGKILL)
                # 代理方案
                # child.terminate()
                # child.wait(timeout=1)
                print(f"\t[killed sub process] - {child.pid},"
                      f" signal: {signal.SIGINT}")
            except Exception as exp:
                print(f"[Kill process failed] error {exp}")

    @classmethod
    @ignore_assigned_error((FileNotFoundError, NoSuchProcess))
    def kill_process(cls, pid=None):
        pid = pid if pid is not None else os.getpid()
        this_process = psutil.Process(pid)
        cls.kill_sub_processes(this_process.pid)
        time.sleep(0.1)
        os.kill(this_process.pid, signal.SIGINT)
        os.waitpid(this_process.pid, 0)
        # this_process.terminate()
        # this_process.wait(timeout=1)

    @classmethod
    def register_kill_all_subprocess_at_exit(cls):
        # kill all sub process at exit
        atexit.register(cls.kill_sub_processes, pid=os.getpid())


@ignore_assigned_error((FileNotFoundError, NoSuchProcess))
def restart_whole_process():
    print(f"Restarting process - PID: {os.getpid()}")
    print_sub_processes(pid=os.getpid())
    ProcessController.kill_sub_processes()
    python = sys.executable
    os.execl(python, python, *sys.argv)


@ignore_assigned_error((FileNotFoundError, NoSuchProcess))
def print_sub_processes(pid=None, depth=1):
    pid = pid if pid is not None else os.getpid()
    this_process = psutil.Process(pid)
    tab = "\t\t" * (depth - 1)
    print(f"{tab}- {pid}, status: {this_process.status()}")
    for child in this_process.children():
        print_sub_processes(child.pid, depth=depth + 1)


class MultiShardObject(object):
    """接收 object, 有一个 queue 管理， 拿取， 更新"""
    SHA_TZ = timezone(timedelta(hours=8), name='Asia/Shanghai')
    CREATE_TIME = "create_time"
    CREATE_TIMESTAMP = "create_timestamp"

    UPDATE_TIME = "update_time"
    UPDATE_TIMESTAMP = "update_timestamp"

    def __init__(self, obj: object):
        self.queue = mp.Queue(1)
        self._update_time_attr(obj, creat=True)
        self.queue.put(obj)

    def _update_time_attr(self, obj, creat=False):
        now_time = self._get_beijing_now_time()
        now_timestamp = time.time()
        if creat:
            setattr(obj, self.CREATE_TIME, now_time)
            setattr(obj, self.CREATE_TIMESTAMP, now_timestamp)
        setattr(obj, self.UPDATE_TIME, now_time)
        setattr(obj, self.UPDATE_TIMESTAMP, now_timestamp)

    @classmethod
    def _get_beijing_now_time(cls, fmt="%Y-%m-%d %H:%M:%S.%f") -> str:
        utc_time = datetime.utcnow().replace(tzinfo=timezone.utc)
        beijing_time = utc_time.astimezone(cls.SHA_TZ)
        return beijing_time.strftime(fmt)

    def get_attr(self, attr: str):
        obj = self.queue.get()
        self.queue.put(obj)
        return getattr(obj, attr)

    def get(self):
        obj = self.queue.get()
        self.queue.put(obj)
        return obj

    def _delay_handle(self, delay_update: float = 0.0):
        update_timestamp = self.get_attr(self.UPDATE_TIMESTAMP)
        delay_update /= 1000.0
        stay_time = time.time() - update_timestamp
        if stay_time < delay_update:
            time.sleep(delay_update - stay_time)

    def update_attr(self, attr, value, delay_ms: float = 0.0):
        """

        :param attr: 需要更新的属性名
        :param value: 需要更新的属性值
        :param delay_ms: 延迟多少毫秒更新 (相对于上次更新时间)， 单位：毫秒
                        相较于上次更新时间，必须超过 delay_ms 才能更新，
                        用于防止依赖上次更新状态的业务逻辑还没执行完，就被设置成了新的状态

                    如：协同结束：
                        - 1 号收到结束信号，判断当前状态为未结束，则更新状态为 结束，并广播协同结束信号
                        - 协作者 2 号收到协同结束信号，判断当前状态为未结束，则更新状态为 结束，并广播协同结束信号
                        - 此时 1 号的状态被设置成了 非结束状态，在这之后，再次收到了 2号 的广播结束信号，
                                         判断当前状态为未结束，再次更新状态为 结束，并再次广播协同结束信号

                        由此造成，重复结束， 1 号状态，在收到别的协同结束信号后，状态应该不变，这样才能不重复结束

        :return:
        """
        self._delay_handle(delay_ms)
        queue_obj = self.queue.get()
        self._update_time_attr(queue_obj)
        setattr(queue_obj, attr, value)
        self.queue.put(queue_obj)
        tag = (f"[{queue_obj.req_tag}]"
               if hasattr(queue_obj, "tag") and queue_obj.req_tag else "")
        logging.info(f"[UPDATE ATTR]{tag}: updated `{type(queue_obj)}.{attr}`"
                     f" to `{value}`")

    def reset_update(self):
        """
            会调用 维护对象的 reset 方法，如果 reset 方法不存在，则不会起任何作用
        :return:
        """
        queue_obj = self.queue.get()
        try:
            method = getattr(queue_obj, "reset")
            if callable(method):
                method()
                self._update_time_attr(queue_obj)
        except AttributeError:
            pass
        self.queue.put(queue_obj)

    def waiting_attr(self, attr, wait_value, time_out=0.1, wait_round=50,
                     reverse_judge=False, update2wait_value=False):
        """

        :param attr:
        :param wait_value:
        :param time_out: second
        :param wait_round: second
        :param reverse_judge: bool
        :param update2wait_value: bool 若未等待到 wait_value, 是否主动设置为 wait_value
        :return:
        """

        def _log_success(_value):
            logging.info(f"Waiting attr '{attr}' is {wait_value} success,"
                         f" now {_value}")

        for _ in range(wait_round):
            value = self.get_attr(attr)
            if wait_value is None:
                if reverse_judge:
                    if value is not None:
                        _log_success(value)
                        return True
                else:
                    if value is None:
                        _log_success(value)
                        return True
            else:
                if reverse_judge:
                    if value != wait_value:
                        _log_success(value)
                        return True
                else:
                    if value == wait_value:
                        _log_success(value)
                        return True
            log_not = "not" if reverse_judge else ""
            logging.info(f"Waiting attr '{attr}' {log_not}"
                         f" {wait_value} , now {value}.........")
            time.sleep(time_out)
        if update2wait_value:
            self.update_attr(attr, wait_value)

        logging.warning(f"Waiting attr '{attr}' is {wait_value} failed, "
                        f"now {self.get_attr(attr)}, time_out={time_out}, "
                        f"wait_round={wait_round}, "
                        f"invoker_stacks: {get_invoke_stacks_str()}")
        return False


@new_process()
def test(a, b, _queue: mp.Queue):
    logging.debug(f"sum: {a + b}")
    while True:
        data = _queue.get()
        logging.debug(f"子进程{mp.current_process().name} 获取数据:　{data}")


class MultiStr(object):

    def __init__(self, value):
        self.value = value


class WrapperMultiLock(object):
    """
        支持自动识别同一线程，嵌套获取锁操作，避免此情况造成的死锁问题， 如：
        with lock as acquire_success1:
            print("do process")
            with lock as acquire_success2:
                print("do_process")
                with lock as acquire_success3:
                    print("do_process")
        这种情况下， 除了 acquire_success1 为 True, acquire_success2 与 acquire_success3
        都会为 False, 应根据 `acquire_success` 判断选择合适的操作，如果获取失败，应主动避免
        会搞乱数据的操作

        with lock:
            pass
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
            self._lock.__exit__(exc_type, exc_val, exc_tb)

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


class TestObject(object):

    def __init__(self):
        self.a = 2

    def reset(self):
        self.a = 0


if __name__ == "__main__":
    def test1():
        time.sleep(100)


    def test2():
        mp.Process(target=test1).start()
        time.sleep(100)


    p = mp.Process(target=test2)
    p.start()

    time.sleep(5)
    ProcessController.kill_process(p.pid)

    print(f"llklsdlfjksdlkfj: {os.getpid()}")
    time.sleep(100)
