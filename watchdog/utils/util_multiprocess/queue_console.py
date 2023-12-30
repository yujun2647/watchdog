import time
import logging
import multiprocessing as mp
from abc import abstractmethod
from contextvars import ContextVar
from multiprocessing.queues import Queue

from watchdog.utils.util_multiprocess.multi_object import MultiShareObject
from watchdog.models.multi_objects.task_info import TaskInfo


class QueueBox(object):
    pass


class QueueConsole(object):
    TASK_INFO_CONTEXT = ContextVar("task_info")

    def __init__(self, global_worker_task: MultiShareObject,
                 console_id: str = ""):
        self.global_worker_task = global_worker_task
        self.console_id = console_id

    @classmethod
    @abstractmethod
    def init_default(cls, console_id="console_id") -> "QueueConsole":
        """
            初始化一个默认的管理对象，用作缺省值，当工作节点不需要使用 全局管理器时 使用
        :param console_id:
        :return:
        """
        return QueueConsole(
            global_worker_task=mp.Manager().TaskInfo(task_name=console_id),
            console_id=console_id
        )

    @classmethod
    def set_context_task_info(cls, task_info: TaskInfo):
        cls.TASK_INFO_CONTEXT.set(task_info)

    @classmethod
    def get_context_task_info(cls) -> [TaskInfo, None]:
        return cls.TASK_INFO_CONTEXT.get(None)

    def get_task_info(self) -> TaskInfo:
        return self.global_worker_task.get()

    def set_task_info_context(self):
        task_info: TaskInfo = self.get_task_info()
        self.set_context_task_info(task_info)

    def queue_size_check(self, loop_check=False):
        """检查所有队列容量"""
        attrs_dict = self.__dict__

        def _check_once(_attrs_dict):
            queue_size_check_str = """[queue_size_check]:"""
            queue_sizes = dict()
            queue_size_check_str = f"\n{self.console_id}-{queue_size_check_str}"
            queue_boxes = []
            for attr, attr_value in _attrs_dict.items():
                # queue 的类型检查得这样...
                if isinstance(attr_value, Queue):
                    size = attr_value.qsize()
                    queue_size_check_str += f"\n     {attr}: {size}"
                    queue_sizes[attr] = size
                elif isinstance(attr_value, QueueBox):
                    if "z_sub_queue_boxes" not in queue_sizes:
                        queue_sizes["z_sub_queue_boxes"] = {}
                    queue_box_size = _check_once(attr_value.__dict__)
                    queue_sizes["z_sub_queue_boxes"][attr] = queue_box_size
                    queue_boxes.append((attr, attr_value))

            logging.debug(queue_size_check_str)
            return queue_sizes

        def _size_check():
            while True:
                _check_once(attrs_dict)
                time.sleep(4)

        if loop_check:
            mp.Process(target=_size_check).start()
        return _check_once(attrs_dict)
