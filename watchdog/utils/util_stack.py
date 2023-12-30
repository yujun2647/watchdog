import os
import io
import sys
import logging
import traceback
from typing import *

if hasattr(sys, '_getframe'):
    currentframe = lambda: sys._getframe(3)
else:  # pragma: no cover
    def currentframe():
        """Return the frame object for the caller's stack frame."""
        try:
            raise Exception
        except Exception:
            return sys.exc_info()[2].tb_frame.f_back


def addLevelName(level, levelName):
    """
    Associate 'levelName' with 'level'.

    This is used when converting levels to text during message formatting.
    """
    pass


_srcfile = os.path.normcase(addLevelName.__code__.co_filename)
f = __file__


def get_invoker_msg(invoke_frame, src_codes={}):
    invoke_f_code = invoke_frame.f_code
    invoke_filename = invoke_f_code.co_filename
    invoke_func_name = invoke_f_code.co_name

    if invoke_filename in src_codes:
        lines = src_codes[invoke_filename]
    else:
        with open(invoke_filename, "r") as fp:
            lines = fp.readlines()
        src_codes[invoke_filename] = lines

    # invoke_code_line = invoke_f_code.co_firstlineno
    invoke_code_line = invoke_frame.f_lineno
    invoke_code_name = lines[invoke_code_line - 1].replace("\n", "").strip()

    _invoker_msg = f"""File "{invoke_filename}", line {invoke_code_line}, in {invoke_func_name}
    {invoke_code_name} """
    if len(src_codes) > 10:
        src_codes.clear()
    return _invoker_msg


def get_invoke_stacks(invoke_frame=None, stack_num=15):
    if invoke_frame is None:
        invoke_frame = sys._getframe().f_back.f_back
    invoke_stacks = []
    for _ in range(stack_num):
        if invoke_frame is None:
            break
        invoker_msg = get_invoker_msg(invoke_frame)
        if "/python3" not in invoker_msg:
            invoke_stacks.append(invoker_msg)
        if not hasattr(invoke_frame, "f_back"):
            break
        invoke_frame = invoke_frame.f_back

    invoke_stacks.reverse()
    return invoke_stacks


def get_invoke_stacks_str(invoke_frame=None, stack_num=15):
    if invoke_frame is None:
        invoke_frame = sys._getframe().f_back.f_back
    invoke_stacks = get_invoke_stacks(invoke_frame=invoke_frame,
                                      stack_num=stack_num)
    invoker_stacks_str = "\n".join(invoke_stacks)
    return invoker_stacks_str


def find_caller(stack_info=False, stack_level=1) -> Tuple:
    """

    :param stack_info:
    :param stack_level:
    :return: 返回调用调用方的信息： (文件路径, 行号)
    """
    # noinspection PyBroadException
    try:  # 兼容 cython currentframe 无效
        f = currentframe()
    except Exception:
        return "(unknown file)", 0
    # On some versions of IronPython, currentframe() returns None if
    # IronPython isn't run with -X:Frames.
    if f is not None and f.f_back is not None:
        f = f.f_back
    orig_f = f
    while f and stack_level > 1:
        f = f.f_back
        stack_level -= 1
    if not f:
        f = orig_f
    rv = "(unknown file)", 0
    while hasattr(f, "f_code"):
        co = f.f_code
        filename = os.path.normcase(co.co_filename)
        if filename == _srcfile and f.f_back is not None:
            f = f.f_back
            continue
        sinfo = None
        if stack_info:
            sio = io.StringIO()
            sio.write('Stack (most recent call last):\n')
            traceback.print_stack(f, file=sio)
            sinfo = sio.getvalue()
            if sinfo[-1] == '\n':
                sinfo = sinfo[:-1]
            sio.close()
        rv = (co.co_filename, f.f_lineno)
        break
    return rv


def test():
    # logging.info("test")
    print(find_caller())


if __name__ == "__main__":
    from backend_utils.util_log import set_scripts_logging

    # set_scripts_logging(__file__)
    test()
