from typing import *
import json
import logging
import functools
import traceback
from watchdog.utils.util_printer import to_pretty_string


class ErrorHandler(object):

    def __init__(self, exp):
        self.exp = exp

    def handle_error(self):
        pass


def serialize_args(*args, **kwargs):
    def __to_json(_data):
        # noinspection PyBroadException
        try:
            _data = json.loads(_data)
            return _data
        except Exception:
            pass
        return _data

    serialized = {}
    if args:
        serialized.update(dict(args=__to_json(args)))
    if kwargs:
        serialized.update(dict(kwargs=__to_json(kwargs)))
    return to_pretty_string(serialized)


def unpack_exp(exp: Exception, error_type="error") -> Dict:
    """
    :param exp:
    :param error_type:
    :return:
        {
            "error_type" "error",
            "error_msg": "异常错误信息",
            "error_name": "异常错误信息",
            "error_file": "发生异常的文件"
        }
    """
    error_name = type(exp).__name__
    error_msg = str(exp)
    tb_stacks = traceback.format_tb(exp.__traceback__)
    error_file = tb_stacks[-1].strip().replace("\n", "") \
        .replace("File \"", "").replace("\"", "")
    return dict(errorType=error_type,
                errorName=error_name,
                errorMsg=error_msg,
                errorFile=error_file)


def ignore_error(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # noinspection PyBroadException
        try:
            result = func(*args, **kwargs)
            return result
        except Exception:
            func_name = func.__name__
            logging.error(f"error in {func_name}, {traceback.format_exc()}")

    return wrapper


def ignore_error_with_handler(error_processor_cls):
    def ignore_error_inner(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # noinspection PyBroadException
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as exp:
                func_name = func.__name__
                logging.error(f"error in {func_name}, {traceback.format_exc()}")
                error_processor_cls(exp).handle_error()

        return wrapper

    return ignore_error_inner


def ignore_assigned_error(assigned_error: Tuple):
    def out_wrapper(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # noinspection PyBroadException
            try:
                result = func(*args, **kwargs)
                return result
            except assigned_error:
                func_name = func.__name__
                logging.error(f"error in {func_name}, {traceback.format_exc()}")

        return wrapper

    return out_wrapper


@ignore_error
def ignore_error_test():
    logging.debug("ignore_error_test")
    a = 1 / 0


@ignore_assigned_error((ZeroDivisionError,))
def ignore_assigned_error_test1():
    logging.debug("ignore_assigned_error_test1")
    a = 1 / 0


@ignore_assigned_error((ZeroDivisionError, ValueError))
def ignore_assigned_error_test2():
    logging.debug("ignore_assigned_error_test1")
    raise ValueError("test")


class TestErrorHandler(ErrorHandler):
    def handle_error(self):
        print(f"process TestError: {self.exp}")


@ignore_error_with_handler(TestErrorHandler)
def ignore_error_with_processor_test():
    a = 1 / 0


if __name__ == '__main__':
    # warning_test(dict(a=2, b=3))
    # ignore_error(ignore_error_test)()
    ignore_error_with_processor_test()
    # ignore_assigned_error_test2()
    # print("test")
