import time
import logging
import hashlib


def is_num(string):
    # noinspection PyBroadException
    try:
        float(string)
        return True
    except Exception as exp:
        return False


def extract_num_from_string(string):
    def _to_num(_string):
        return float(_string) if "." in string else int(_string)

    if is_num(string):
        return _to_num(string)
    else:
        chars = [c for c in string if is_num(c)]
        if not chars:
            raise TypeError(f"string : {string} doesn't contain number")
        return _to_num("".join(chars))


def random_str():
    return hashlib.md5(str(time.time()).encode(encoding='utf-8')).hexdigest()


def plus_str_tail_idx(string: str, tail_symbol="$"):
    string = str(string)
    if tail_symbol in string:
        index = string.rindex(tail_symbol)
        prefix, tail_index = string[:index], string[index:]
        tail_index = extract_num_from_string(tail_index)
        return f"{prefix}{tail_symbol}{tail_index + 1}"
    else:
        return f"{string}{tail_symbol}1"


def line2hump(text):
    """下划线命名转驼峰命名"""
    items = text.split("_")
    for index, item in enumerate(items):
        if index == 0:
            continue
        item = f"{item[0].upper()}{item[1:]}"
        items[index] = item
    new_text = "".join(items)
    return new_text


def hump2line(text):
    """驼峰命名转下划线命名"""
    lst = []
    for index, char in enumerate(text):
        if char.isupper() and index != 0:
            lst.append("_")
        lst.append(char)

    return "".join(lst).lower()


if __name__ == "__main__":
    t = line2hump("basketball_around")
    logging.debug(extract_num_from_string("ssss23245"))
