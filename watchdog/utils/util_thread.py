from typing import Callable
import time
import logging
import functools
from threading import Thread


def new_thread(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        Thread(target=func, args=args, kwargs=kwargs).start()

    return wrapper


def new_daemon_thread(func):
    """"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        Thread(target=func, args=args, kwargs=kwargs, daemon=True).start()

    return wrapper


@new_thread
def test_func(a, b=None):
    logging.debug("do something")
    time.sleep(4)
    logging.debug(a, b)
    logging.debug("work done")


class ResultThread(Thread):

    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None, *, daemon=None):
        super().__init__(group=group, target=target, name=name,
                         args=args, kwargs=kwargs, daemon=daemon)
        self.result = None

    def get_result(self):
        return self.result

    def run(self):
        try:
            if self._target:
                self.result = self._target(*self._args, **self._kwargs)
        finally:
            # Avoid a refcycle if the thread is running a function with
            # an argument that has a member that points to the thread.
            del self._target, self._args, self._kwargs


def execute_by_thread(target: Callable, args=(), kwargs=None,
                      join: bool = True, wait_timeout=None) -> False:
    """

    :param target:
    :param args:
    :param kwargs:
    :param join: 是否 join 等待线程结束
    :param wait_timeout: 等待线程结束最大时间，仅当 join = True 有效
    :return: 是否已结束
    """

    def _wait_thread(thread: ResultThread, timeout: [float, int]) -> object:
        """
        :param thread:
        :param timeout:
        :return: 返回线程结果
        """
        thread.join(timeout=timeout)
        return thread.result

    th = ResultThread(target=target, args=args, kwargs=kwargs)
    th.start()
    if join:
        return _wait_thread(th, wait_timeout)
    return th.result


if __name__ == "__main__":
    from watchdog.utils.util_log import set_scripts_logging
    set_scripts_logging(__file__)
    test_func(1, 3)
    print("test end ")
