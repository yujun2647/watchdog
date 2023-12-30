import json
from copy import deepcopy

from watchdog.utils.util_multiprocess.multi_object import MultiShareObject


class TaskInfo(MultiShareObject):
    # 属性名，用于获取 属性名
    TASK_NAME = "task_name"
    TASK_ID = "task_id"

    def __init__(self, task_id="", task_name="simple-task"):
        super().__init__()
        self.task_id = task_id
        self.task_name = task_name

    def self_desc_text(self):
        return json.dumps(self.__dict__, indent=4, ensure_ascii=False)

    def self_desc_datas(self):
        datas = deepcopy(self.__dict__)
        return datas

    def reset(self):
        """
            每次重新创建任务都需要调用这个方法
        """
        self.task_id = "reset"


TaskInfo.register()
