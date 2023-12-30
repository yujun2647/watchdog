from typing import *


def get_callable_name(method_or_function: Callable):
    name = method_or_function.__str__()
    return name.split("of <")[0].split("at")[0].replace(
        "<", "").strip()
