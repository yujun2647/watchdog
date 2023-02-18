import inspect
from typing import *


def get_source_info(obj) -> Tuple[str, List, int]:
    """
    :param obj:
    :return: 返回该对象所属的 文件、源码定义，文件行数
    """
    src_file = inspect.getfile(obj)
    # noinspection PyBroadException
    try:
        src_lines, line_no = inspect.getsourcelines(obj)
    except Exception as exp:
        src_lines, line_no = "", ""
    return src_file, src_lines, line_no


def get_cls_names_from_src(source_code) -> Tuple[List, List]:
    """

    :param source_code:
    :return: (["classname"], [("classname", "base_class")])
    """
    code_lines: List[str] = source_code.split("\n")
    class_names = []
    class_name_with_base = []
    classes_heads = []
    class_heads = []
    for code_line in code_lines:
        class_head = code_line
        if not class_heads and class_head.startswith("class "):
            class_heads.append(class_head)
            continue

        if class_heads:
            if class_heads[-1].endswith(":"):
                classes_heads.append([code.replace("\\", "").strip()
                                      for code in class_heads])
                class_heads.clear()
                continue
            else:
                class_heads.append(class_head)
                continue

    for class_heads in classes_heads:
        class_head = "".join(class_heads)
        if class_head.startswith("class ") and class_head.endswith(":"):
            class_name = class_head[
                         class_head.index(" "): class_head.index("(")]
            base_class_name = class_head[
                              class_head.index("(") + 1: class_head.index(")")]
            class_name = class_name.strip()
            base_class_name = base_class_name.strip()
            class_name_with_base.append((class_name, base_class_name))
            class_names.append(class_name)

    return class_names, class_name_with_base


def get_cls_names_from_file(src_filepath: str) -> Tuple[List, List]:
    """

    :param src_filepath:
    :return: (["classname"], [("classname", "base_class")])
    """
    src_filepath = src_filepath.strip()
    if not src_filepath.endswith(".py"):
        raise Exception("Only support python script")
    with open(src_filepath, "rb") as fp:
        src_code = fp.read().decode()
        return get_cls_names_from_src(src_code)


class Test(object):
    pass


if __name__ == "__main__":
    t, t1 = get_cls_names_from_file(
        "/home/walkerjun/codes/Sports/Projects/HerculesModel/src/unit_tests/simulations/test_data_format_valid.py")
    print("debug")
