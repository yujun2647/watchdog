from typing import *
from abc import abstractmethod

from watch_dog.services.wd_queue_console import WdQueueConsole
from watch_dog.models.worker_req import WorkerEndReq, WorkerStartReq
from watch_dog.utils.util_multiprocess.base_worker import BaseWorker


class WDBaseWorker(BaseWorker):

    def __init__(self, q_console: Optional[WdQueueConsole] = None, **kwargs):
        self.q_console = q_console
        if self.q_console is None:
            self.q_console = WdQueueConsole.init_default(console_id="simple")
        super().__init__(q_console=self.q_console, **kwargs)
        self.__sub_init__(**kwargs)

    @abstractmethod
    def __sub_init__(self, **kwargs):
        pass

    @abstractmethod
    def _sub_work_before_cleaned_up(self, work_req):
        pass

    @abstractmethod
    def _sub_init_work(self, work_req):
        pass

    @abstractmethod
    def _handle_start_req(self, work_req: WorkerStartReq) -> bool:
        pass

    @abstractmethod
    def _handle_end_req(self, work_req: WorkerEndReq) -> bool:
        pass

    @abstractmethod
    def _sub_work_done_cleaned_up(self, work_req):
        pass

    @abstractmethod
    def _sub_side_work(self):
        pass

    @abstractmethod
    def _sub_clear_all_output_queues(self):
        pass

    @abstractmethod
    def _handle_worker_exception(self, exp):
        pass


if __name__ == "__main__":
    import time
    import multiprocessing as mp


    class TestWorker(WDBaseWorker):
        def __sub_init__(self):
            self.test_value = mp.Value("i", 111)

        def _sub_work_before_cleaned_up(self, work_req):
            print("do work_before_cleaned_up")

        def _sub_init_work(self, work_req):
            print("do init_work")

        def _handle_start_req(self, work_req: WorkerStartReq) -> bool:
            time.sleep(1)
            self.plus_working_handled_num()
            print(f"handled start req, working_handled_num: "
                  f"{self.working_handled_num}, {self.test_value.value}")
            # 可提前结束
            if self.working_handled_num == 100:
                return True

            return False

        def _handle_end_req(self, work_req: WorkerEndReq) -> bool:
            time.sleep(1)
            self.plus_working_handled_num()
            print(f"handled end req: self.working_handled_num: "
                  f"{self.working_handled_num}")
            return True

        def _sub_work_done_cleaned_up(self, work_req):
            print("do work_done_cleaned_up")

        def _sub_side_work(self):
            pass

        def _sub_clear_all_output_queues(self):
            pass

        def _handle_worker_exception(self, exp):
            pass


    t = TestWorker()
    t.start_work_in_subprocess()
    last_heat_beat = 0
    t.send_start_work_req()
    while True:
        now_heart_beat = t.heart_beat
        if now_heart_beat != last_heat_beat:
            print(f"now heart beat: {now_heart_beat}")
            last_heat_beat = now_heart_beat

        if t.working_handled_num == 10:
            t.send_end_work_req()
            break
