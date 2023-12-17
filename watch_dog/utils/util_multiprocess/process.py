import os
import sys
import time
import signal
import atexit
import logging
import threading
import multiprocessing as mp

import psutil
from psutil import NoSuchProcess

from watch_dog.utils.util_warning import ignore_assigned_error


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
    def kill_sub_processes(cls, pid=None, excludes=None, timeout=0):
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
                cls.waitpid(child.pid, timeout=timeout)
                print(f"\t[killed sub process] - {child.pid},"
                      f" signal: {signal.SIGINT}")
            except Exception as exp:
                print(f"[Kill process failed] error {exp}")

    @classmethod
    def waitpid(cls, pid, timeout=0, sent_signal="SIGINT"):
        start = time.time()
        if timeout <= 0:
            return os.waitpid(pid, 0)

        for i in range(int(timeout / 0.3)):
            result = os.waitpid(pid, os.WNOHANG)
            if result == (0, 0):
                time.sleep(0.3)
                continue
            logging.info(f"[ProcessController] process {pid} stop/kill success "
                         f"after sent signal {sent_signal}")

            return result
        if sent_signal == "SIGKILL":
            logging.error(f"[ProcessController] process still hang {pid}, "
                          f"after sent SIGKILL signal !!!")
            return

        logging.info(f"[ProcessController] process {pid} hang in {timeout} "
                     f"seconds after send {sent_signal} signal, force to kill, "
                     f"send SIGKILL signal")
        os.kill(pid, signal.SIGKILL)
        cls.waitpid(pid, timeout=int(max(timeout - (time.time() - start), 3)),
                    sent_signal="SIGKILL")

    @classmethod
    @ignore_assigned_error((FileNotFoundError, NoSuchProcess))
    def kill_process(cls, pid=None, timeout=0):
        start = time.time()
        logging.info(f"[ProcessController] killing process: {pid}")
        pid = pid if pid is not None else os.getpid()
        this_process = psutil.Process(pid)
        cls.kill_sub_processes(this_process.pid, timeout=timeout)
        time.sleep(0.1)
        os.kill(this_process.pid, signal.SIGINT)
        logging.info(f"[ProcessController] sent signal.SIGINT to {pid}")
        logging.info(f"[ProcessController] waiting {pid}")
        cls.waitpid(pid, timeout=int(max(timeout - (time.time() - start), 3)))

        logging.info(f"[ProcessController] wait end {pid}")
        logging.info(f"[ProcessController] killed process: {pid}")
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
