from typing import *
import time
import logging
import multiprocessing as mp
from multiprocessing import RLock as MRLock
from multiprocessing.managers import SyncManager, BaseProxy, BaseManager
from datetime import datetime, timedelta, timezone

from watchdog.utils.util_stack import get_invoke_stacks_str


def exclude_proxy(func):
    """
        使用本装饰器的函数，将会直接执行该函数在代理对象中对应的函数，
        而不会发送请求至代理 manager 执行
    :param func:
    :return:
    """

    def inner(*args, **kwargs):
        return func(*args, **kwargs)

    return inner


def _is_exclude_proxy(func):
    return exclude_proxy.__name__ in func.__qualname__.split(".")


class NamespaceProxy(BaseProxy):
    SHA_TZ = timezone(timedelta(hours=8), name='Asia/Shanghai')
    CREATE_TIME = "create_time"
    CREATE_TIMESTAMP = "create_timestamp"

    UPDATE_TIME = "update_time"
    UPDATE_TIMESTAMP = "update_timestamp"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = MRLock()
        with self._lock:
            self._update_time_attr(creat=True)
        self._value = self._callmethod_with_lock("self_value")

    def __getattr__(self, key):
        if key[0] == "_":
            return object.__getattribute__(self, key)
        with self._lock:
            return self._callmethod_with_lock("__getattribute__", (key,))

    def __setattr__(self, key, value):
        if key[0] == "_":
            return object.__setattr__(self, key, value)
        with self._lock:
            return self._callmethod_with_lock("__setattr__", (key, value),
                                              update_time_stamp=True)

    def __delattr__(self, key):
        if key[0] == "_":
            return object.__delattr__(self, key)
        with self._lock:
            return self._callmethod_with_lock("__delattr__", (key,))

    def _callmethod_with_lock(self, method_name, args=(), kwargs=None,
                              update_time_stamp=False):
        if kwargs is None:
            kwargs = {}
        with self._lock:
            result = self._callmethod(method_name, args=args, kwds=kwargs)
            if update_time_stamp:
                self._update_time_attr()
            return result

    def _update_time_attr(self, creat=False):
        now_time = self._get_beijing_now_time()
        now_timestamp = time.time()
        if creat:
            self._callmethod("__setattr__", (self.CREATE_TIME, now_time))
            self._callmethod("__setattr__",
                             (self.CREATE_TIMESTAMP, now_timestamp))
        self._callmethod("__setattr__", (self.UPDATE_TIME, now_time))
        self._callmethod("__setattr__", (self.UPDATE_TIMESTAMP, now_timestamp))

    @classmethod
    def _get_beijing_now_time(cls, fmt="%Y-%m-%d %H:%M:%S.%f") -> str:
        utc_time = datetime.utcnow().replace(tzinfo=timezone.utc)
        beijing_time = utc_time.astimezone(cls.SHA_TZ)
        return beijing_time.strftime(fmt)

    def _delay_handle(self, delay_update: float = 0.0):
        update_timestamp = self.get_attr(self.UPDATE_TIMESTAMP)
        delay_update /= 1000.0
        stay_time = time.time() - update_timestamp
        if stay_time < delay_update:
            time.sleep(delay_update - stay_time)

    def update_attr(self, attr, value, delay_ms: float = 0.0):
        """

        :param attr: 需要更新的属性名
        :param value: 需要更新的属性值
        :param delay_ms: 延迟多少毫秒更新 (相对于上次更新时间)， 单位：毫秒
                        相较于上次更新时间，必须超过 delay_ms 才能更新，
                        用于防止依赖上次更新状态的业务逻辑还没执行完，就被设置成了新的状态

                    如：协同结束：
                        - 1 号收到结束信号，判断当前状态为未结束，则更新状态为 结束，并广播协同结束信号
                        - 协作者 2 号收到协同结束信号，判断当前状态为未结束，则更新状态为 结束，并广播协同结束信号
                        - 此时 1 号的状态被设置成了 非结束状态，在这之后，再次收到了 2号 的广播结束信号，
                                         判断当前状态为未结束，再次更新状态为 结束，并再次广播协同结束信号

                        由此造成，重复结束， 1 号状态，在收到别的协同结束信号后，状态应该不变，这样才能不重复结束

        :return:
        """
        self._delay_handle(delay_ms)
        setattr(self, attr, value)
        logging.info(f"[UPDATE ATTR]: updated `{attr}` to `{value}`")

    def waiting_attr(self, attr, wait_value, time_out=0.1, wait_round=50,
                     reverse_judge=False, update2wait_value=False) -> bool:
        """

        :param attr:
        :param wait_value:
        :param time_out: second
        :param wait_round: second
        :param reverse_judge: bool
        :param update2wait_value: bool 若未等待到 wait_value, 是否主动设置为 wait_value
        :return:
        """
        if not hasattr(self, attr):
            raise AttributeError(f"No such attr `{attr}` in object: {self}")

        def _log_success(_value):
            logging.info(f"Waiting attr '{attr}' is {wait_value} success,"
                         f" now {_value}")

        for _ in range(wait_round):
            value = getattr(self, attr)
            if wait_value is None:
                if reverse_judge:
                    if value is not None:
                        _log_success(value)
                        return True
                else:
                    if value is None:
                        _log_success(value)
                        return True
            else:
                if reverse_judge:
                    if value != wait_value:
                        _log_success(value)
                        return True
                else:
                    if value == wait_value:
                        _log_success(value)
                        return True
            log_not = "not" if reverse_judge else ""
            logging.info(f"Waiting attr '{attr}' {log_not}"
                         f" {wait_value} , now {value}.........")
            time.sleep(time_out)
        if update2wait_value:
            setattr(self, attr, wait_value)

        logging.warning(f"Waiting attr '{attr}' is {wait_value} failed, "
                        f"now {getattr(self, attr)}, time_out={time_out}, "
                        f"wait_round={wait_round}, "
                        f"invoker_stacks: {get_invoke_stacks_str()}")
        return False

    @property
    def value(self):
        self._value = self._callmethod_with_lock("self_value")
        return self._value

    def get_lock(self):
        return self._lock

    def get_attr(self, attr: str):
        return getattr(self, attr)

    def get(self):
        return self.value


class MultiShareObject(object):
    """注意
        类似 t.a += 1 这样的操作不是进程安全的
        需要这样使用
        with t.get_lock:
            t.a += 1
    """

    def __init__(self):
        self.create_time = None
        self.create_timestamp = None
        self.update_time = None
        self.update_timestamp = None

    def self_value(self):
        return self

    def reset(self):
        ...

    @exclude_proxy
    @property
    def value(self):
        return

    @exclude_proxy
    def shape(self):
        # ide debug 访问
        ...

    @exclude_proxy
    def get_lock(self) -> MRLock:
        ...

    @exclude_proxy
    def get_attr(self, attr: str):
        ...

    @exclude_proxy
    def get(self):
        ...

    @exclude_proxy
    def waiting_attr(self, attr, wait_value, time_out=0.1, wait_round=50,
                     reverse_judge=False, update2wait_value=False) -> bool:
        ...

    @classmethod
    @exclude_proxy
    def create_proxy_class(cls) -> Callable:
        class_attrs = dir(cls)
        _exposed_ = ("__getattribute__", "__setattr__", "__delattr__")

        def _call_method_wrapper(method_name):
            def _call_method(self, *args, **kwargs):
                return self._callmethod_with_lock(method_name=method_name,
                                                  args=args, kwargs=kwargs)

            return _call_method

        methods_funcs_attrs_dict = {
            attr: _call_method_wrapper(attr)
            for attr in class_attrs
            if not attr.startswith("__") and not attr.startswith("_")
               and callable(getattr(cls, attr))
               and not _is_exclude_proxy(getattr(cls, attr))
        }

        _exposed_ += tuple(methods_funcs_attrs_dict.keys())
        attrs_dict = dict(
            _exposed_=_exposed_
        )
        init_dict = {}
        init_dict.update(attrs_dict)
        init_dict.update(methods_funcs_attrs_dict)
        proxy_class = type(f"Proxy{cls.__name__}_{int(time.process_time_ns())}",
                           (NamespaceProxy,),
                           init_dict
                           )
        return proxy_class

    @classmethod
    @exclude_proxy
    def register(cls, manager=SyncManager):
        # ensure register, due to execute this method before the start of the manager
        if cls.__name__ not in manager._registry:
            manager.register(cls.__name__, cls, cls.create_proxy_class())

    @classmethod
    @exclude_proxy
    def create_proxy(cls, manager: BaseManager, args=(), kwargs=None):
        if kwargs is None:
            kwargs = {}
        return getattr(manager, cls.__name__)(*args, **kwargs)


if __name__ == "__main__":
    import json
    from watchdog.utils.util_log import set_scripts_logging
    import multiprocessing as mp

    set_scripts_logging(__file__)


    class MultiTest(MultiShareObject):

        def __init__(self, a, b):
            super().__init__()
            self.a = a
            self.b = b

        def cal(self):
            return self.a + self.b

        def cal2(self):
            return self.cal() + 2

        def cal3(self, plus_a):
            self.a += plus_a
            return self.a


    MultiTest.register(SyncManager)
    _manager = mp.Manager()
    multi_test_proxy: MultiTest = _manager.MultiTest(1, 2)


    def test1():
        for _ in range(1000):
            multi_test_proxy.cal3(2)
            multi_test_proxy.a += 4
            time.sleep(1)


    mp.Process(target=test1).start()

    for _ in range(1000):
        print(json.dumps(multi_test_proxy.value.__dict__, indent=4))
        time.sleep(0.5)


class MultiObject(object):
    _MANAGER: SyncManager = mp.Manager()

    def __init__(self, value: object = None):
        self._inner_obj = self._MANAGER.Value(object, value)

    @property
    def value(self):
        return self._inner_obj.value

    @value.setter
    def value(self, v):
        self._inner_obj.value = v
