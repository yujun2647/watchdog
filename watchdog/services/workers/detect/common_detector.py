from typing import *

from watchdog.utils.util_camera import FrameBox
from watchdog.ai.yolo_detector import YoloDetector
from watchdog.models.detect_info import DetectInfo
from watchdog.models.worker_req import WorkerEndReq, WorkerStartReq
from watchdog.services.base.wd_base_worker import WDBaseWorker


class CommonDetector(WDBaseWorker):
    def __sub_init__(self, **kwargs):
        self.detector: Optional[YoloDetector] = None
        self.frame_box_queue = self.q_console.frame4common_detect_queue

    def _sub_work_before_cleaned_up(self, work_req):
        pass

    def _sub_init_work(self, work_req):
        if self.detector is None:
            self.detector = YoloDetector()

    def _handle_start_req(self, work_req: WorkerStartReq) -> bool:
        frame_box: FrameBox = self.get_queue_item(self.frame_box_queue,
                                                  timeout=5, wait_item=True)
        if frame_box is None:
            return False

        d_infos = self.detector.detect(frame_box)

        if not d_infos:
            d_infos.append(DetectInfo(frame_box.frame_id, fps=frame_box.fps,
                                      is_detected=False))

        self.put_queue_item(self.q_console.detect_infos_queue, d_infos,
                            force_put=True)
        self.put_queue_item(self.q_console.detect_infos_sense_queue,
                            d_infos, force_put=True)

        self.plus_working_handled_num()
        return False

    def _handle_end_req(self, work_req: WorkerEndReq) -> bool:
        pass

    def _sub_work_done_cleaned_up(self, work_req):
        pass

    def _sub_side_work(self):
        pass

    def _sub_clear_all_output_queues(self):
        pass

    def _handle_worker_exception(self, exp):
        pass
