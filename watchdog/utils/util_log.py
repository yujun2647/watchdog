import os
import sys
import json
import time
import logging
import functools
import threading
from watchdog.utils.util_src import get_source_info
from watchdog.utils.util_printer import to_pretty_string
from watchdog.utils.util_path import get_log_path

LOG_LEVEL_METHOD_MAP = {
    logging.INFO: logging.info,
    logging.DEBUG: logging.debug,
    logging.WARNING: logging.warning,
    logging.ERROR: logging.ERROR
}


def get_log_cost_msg(cost_second):
    msg = "{cost_num} {unit}"
    if cost_second < 1:
        cost_num = cost_second * 1000
        unit = "ms"
    elif cost_second < 60:
        cost_num = cost_second
        unit = "second"
    elif cost_second < 3600:
        cost_num = cost_second / 60
        unit = "min"
    else:
        cost_num = cost_second / 3600
        unit = "hours"
    return msg.format(cost_num=round(cost_num, 2), unit=unit)


def log_func_cost(start, func_obj, desc=None, insert_extra=True,
                  extra_key="time_cost", log_method=logging.debug, min_cost=1):
    cost = time.time() - start
    if cost * 1000 < min_cost:
        return

    desc = f"[{desc}]" if desc else ""
    # 日志统计使用 毫秒
    extra = {extra_key: cost * 1000} if insert_extra else {}
    # src_filepath, src_lines, line_no = get_source_info(func_obj)
    # line_no += 1
    # src_filename = os.path.basename(src_filepath)
    func_name = func_obj.__name__
    log_msg = (f"【FUNC TIME COST】: {desc} "
               f"{func_name}(**) cost {get_log_cost_msg(cost)}")
    if log_method in (logging.info, logging.debug, logging.error,
                      logging.warning):
        log_method(log_msg, extra=extra)
    else:
        log_method(log_msg)


def time_cost_log(func):
    # 打印各个函数执行时间，用于优化代码
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            log_func_cost(start, func, insert_extra=True)
        except Exception as exp:
            log_func_cost(start, func)
            raise exp
        return result

    return wrapper


def time_cost_log_with_desc(desc="", insert_extra=True, extra_key="time_cost",
                            log_method=logging.debug, min_cost=1):
    """
    :param: desc
    :param: insert_extra 是否注入进 extra, 默认开启，会往 record 中注入耗时信息
    :param: extra_key
    """

    def outer_wrapper(func):
        # 打印各个函数执行时间，用于优化代码
        @functools.wraps(func)
        def inner_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                log_func_cost(start, func, desc=desc,
                              insert_extra=insert_extra, extra_key=extra_key,
                              log_method=log_method, min_cost=min_cost)
            except Exception as exp:
                log_func_cost(start, func, desc=desc)
                raise exp
            return result

        return inner_wrapper

    return outer_wrapper


def set_scripts_logging(_file_, level=logging.DEBUG):
    """
        为了是脚本log安装正确，请把此函数的调用放在脚本的最上面， 例：
            from commons import set_scripts_logging
            set_scripts_logging(__file__)

            import logging
            import ..others..

    @_file_:
    @level:
    @return:
    """
    log_filename = get_log_path(_file_)
    root_logger = logging.getLogger()
    # 解除第三方 logger 广播日志
    for logger_name, logger in root_logger.manager.loggerDict.items():
        if (isinstance(logger, logging.Logger)
                and logger_name != root_logger.name
                and logger.parent.name == root_logger.name):
            logger.propagate = False
    if root_logger.handlers:  # 防止有多个 handler
        root_logger.handlers.clear()

    logging.basicConfig(level=level,
                        format=("%(asctime)s %(filename)s "
                                "[line:%(lineno)d] %(levelname)s %(message)s"),
                        datefmt="%a, %d %b %Y %H:%M:%S",
                        filename=log_filename)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [line:%(lineno)d] %(levelname)s "
                          "%(message)s"))
    console_handler.setLevel(level=level)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(level=level)
    logging.info("\nLog_filename: {}".format(log_filename))
    return log_filename


@time_cost_log_with_desc(desc="test")
def cost_test():
    time.sleep(1.2)


def log_thread_msg(func):
    # 打印各个函数执行时间，用于优化代码
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            thread_id = threading.get_ident()
            thread_name = threading.current_thread().name
            logging.debug(f"[thread log] def {func.__name__} "
                          f"thread_id: {thread_id} "
                          f"thread_name: {thread_name}")
            result = func(*args, **kwargs)
        except Exception as exp:
            raise exp
        return result

    return wrapper


def log_return(desc="", level=logging.INFO, front="", end="", pretty_data=True):
    def out_wrapper(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            log_method = LOG_LEVEL_METHOD_MAP.get(level, logging.INFO)
            if pretty_data:
                result = to_pretty_string(result)

            log_method(f"[Return log] def {func.__name__}: {front}{desc} \n"
                       f"{result}{end}")
            return result

        return wrapper

    return out_wrapper


if __name__ == "__main__":
    set_scripts_logging(__file__)
