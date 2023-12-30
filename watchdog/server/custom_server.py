import logging
import time
import traceback
from flask import Flask
from queue import Queue, Empty
from typing import Callable

from werkzeug import serving
from werkzeug.serving import (BaseWSGIServer,
                              ForkingWSGIServer, ThreadedWSGIServer)

from watchdog.utils.util_callable import get_callable_name


class CustomFlask(Flask):
    # 支持跨域
    def make_default_options_response(self):
        rsp = super().make_default_options_response()
        # 允许 ajax 跨域请求
        rsp.headers.update({
            "Access-Control-Allow-Origin": "*",  # 设置允许跨域
            "Access-Control-Allow-Methods": "GET, POST,OPTIONS",
            "Access-Control-Allow-Headers": "X-Requested-With, Content-Type"
        })
        return rsp


class ActionBox(object):
    def __init__(self, action_callback: Callable, args=None, kwargs=None):
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        self.action_callback = action_callback
        self.args = args
        self.kwargs = kwargs
        self.action_name = f"<{get_callable_name(action_callback)}>"
        self.done_rsp = Queue(1)

    def raise_if_not_callable(self):
        if not callable(self.action_callback):
            raise ValueError(f"[ActionBox]action_callback: "
                             f"{self.action_callback} is not callable !!!")

    def execute_callback(self):
        self.raise_if_not_callable()
        logging.info(f"[Service_action][executing] {self.action_name}")
        start = time.time()
        self.action_callback(*self.args, **self.kwargs)
        cost_time = round(time.time() - start, 2)
        logging.info(f"[Service_action][Execute done] "
                     f"{self.action_name}, cost_time: {cost_time} s")


class EnhanceThreadedWSGIServer(ThreadedWSGIServer):
    SERVICE_ACTION_QUEUE = Queue()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.num = 0

    @classmethod
    def add_service_action(cls, action_callback: Callable, args=None,
                           kwargs=None, timeout=3):
        if not callable(action_callback):
            logging.warning(f"[Service_action]{action_callback} "
                            f"is not callable !!!!")
            return
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        action_box = ActionBox(action_callback, args=args, kwargs=kwargs)
        logging.info(f"[Service_action][sending] {action_box.action_name}")
        cls.SERVICE_ACTION_QUEUE.put(action_box)
        try:
            start = time.perf_counter()
            action_box.done_rsp.get(timeout=timeout)
            logging.info(f"[Service_action][receive done] "
                         f"{action_box.action_name}, "
                         f"cost: {time.perf_counter() - start}")
        except Empty:
            logging.warning(f"[Service_action] {action_box.action_name} "
                            f"not end in {timeout} second, pass")

    def custom_service_actions(self):
        action_callback = None
        if self.SERVICE_ACTION_QUEUE.qsize() > 0:
            try:
                ab: ActionBox = self.SERVICE_ACTION_QUEUE.get(timeout=1)
                logging.info(f"[Service_action] handling action: "
                             f"{ab.action_name}")
                ab.raise_if_not_callable()
                action_callback = ab.action_callback
                ab.execute_callback()
                ab.done_rsp.put(1)
            except Empty:
                logging.warning(
                    f"[Service_actions] "
                    f"self._SERVICE_ACTION_QUEUE get empty, "
                    f"may be consumed by other threads? "
                    f"now qsize: {self.SERVICE_ACTION_QUEUE.qsize()}")
            except Exception as exp:
                raise type(exp)(f"[Service_action][{action_callback}] -{exp}")

    def service_actions(self) -> None:
        try:
            self.custom_service_actions()
        except Exception as exp:
            logging.error(f"[Service_actions][execute failed]: {exp}, "
                          f"{traceback.format_exc()}")


def make_server(
        host=None,
        port=None,
        app=None,
        threaded=False,
        processes=1,
        request_handler=None,
        passthrough_errors=False,
        ssl_context=None,
        fd=None,
):
    """Create a new server instance that is either threaded, or forks
    or just processes one request after another.
    """
    if threaded and processes > 1:
        raise ValueError(
            "cannot have a multithreaded and multi process server.")
    elif threaded:
        return EnhanceThreadedWSGIServer(
            host, port, app, request_handler, passthrough_errors, ssl_context,
            fd=fd
        )
    elif processes > 1:
        return ForkingWSGIServer(
            host,
            port,
            app,
            processes,
            request_handler,
            passthrough_errors,
            ssl_context,
            fd=fd,
        )
    else:
        return BaseWSGIServer(
            host, port, app, request_handler, passthrough_errors, ssl_context,
            fd=fd
        )


class MonkeyPatches(object):

    @classmethod
    def patch_all(cls, wsgi_server=True):
        if wsgi_server:
            serving.make_server = make_server
