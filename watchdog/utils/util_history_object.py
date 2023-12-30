from typing import *


class HistoryObject(object):
    """
        继承此类的对象，会自动记录历史对象，可记录的容量可通过 HISTORY_OBJECT_STORE_NUM 来配置
        需要注意，当一个任务结束时，需要主动调用 clear_histories 来清空历史记录，否则会影响下一次判断
    """

    # 存储历史对象的数量, 子类可继承更改
    HISTORY_OBJECT_STORE_NUM = 1
    # 存储历史对象的 map， 类的路径决定 key
    _STORE_OBJECT_MAP: Dict[str, List[object]] = dict()

    def __init__(self, *args, **kwargs):
        self._store_object()

    @classmethod
    def _get_store_key(cls):
        module_path = str(cls).replace("<class", "") \
            .replace(">", "").replace("'", "").replace(" ", "")
        return module_path

    @classmethod
    def _get_store_object_list(cls) -> List[object]:
        store_key = cls._get_store_key()
        if store_key not in cls._STORE_OBJECT_MAP:
            cls._STORE_OBJECT_MAP[store_key] = list()
        return cls._STORE_OBJECT_MAP[store_key]

    @classmethod
    def clear_all_store_object(cls):
        for key, values in cls._STORE_OBJECT_MAP.items():
            values.clear()
        cls._STORE_OBJECT_MAP.clear()

    def _store_object(self):
        """子类调用，存储当前对象"""
        store_object_list = self._get_store_object_list()
        if len(store_object_list) >= self.HISTORY_OBJECT_STORE_NUM:
            store_object_list.pop(0)
        store_object_list.append(self)

    @classmethod
    def get_stored_length(cls):
        store_object_list = cls._get_store_object_list()
        return len(store_object_list)

    @classmethod
    def get_history_object(cls, history_index: int):
        """
            返回上一个历史对象，-1: 上一个， -2, 上上个
            还没有存那么多时， 返回 None
        :param history_index:
        :return:
        """
        if history_index >= 0:
            raise ValueError("history_index should be negative")

        if abs(history_index) > cls.HISTORY_OBJECT_STORE_NUM:
            raise IndexError(
                f"history_index is out of range, (the store num "
                f"setting of {cls._get_store_key()} "
                f"is {cls.HISTORY_OBJECT_STORE_NUM})")
        store_object_list = cls._get_store_object_list()
        length = len(store_object_list)

        return (store_object_list[history_index] if abs(history_index) <= length
                else None)

    @classmethod
    def clear_histories(cls):
        store_object_list = cls._get_store_object_list()
        store_object_list.clear()

    @classmethod
    def reset(cls):
        cls.clear_histories()


class Test(HistoryObject):
    HISTORY_OBJECT_STORE_NUM = 5

    def __init__(self, a, b):
        super(Test, self).__init__(a, b)
        self.a = a
        self.b = b

    def __str__(self):
        return str(f"{self.a}, {self.b}")


class Test2(HistoryObject):
    HISTORY_OBJECT_STORE_NUM = 1

    def __init__(self, a, b):
        super(Test2, self).__init__(a, b)
        self.a = a
        self.b = b

    def __str__(self):
        return str(f"{self.a}, {self.b}")


if __name__ == "__main__":
    import logging
    from backend_utils.util_log import set_scripts_logging

    set_scripts_logging(__file__)
    Test(1, 2)
    Test(2, 3)
    Test(3, 4)
    HistoryObject.clear_all_store_object()

    logging.debug(Test.get_history_object(-3))
    logging.debug(Test2.get_history_object(-1))
