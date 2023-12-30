"""
    负责标注所有检测结果
"""
import time
from typing import *
from threading import Thread

import numpy as np
import cv2

from watchdog.utils.util_log import time_cost_log
from watchdog.utils.util_camera import FrameBox
from watchdog.models.detect_info import DetectInfo
from watchdog.models.worker_req import WorkerEndReq, WorkerStartReq
from watchdog.services.base.wd_base_worker import WDBaseWorker


class Marker(WDBaseWorker):
    # 检测到的物体 bbox 面积小于次时， 则不会显示出来
    MIN_AREA = 0.02

    def __sub_init__(self):
        self.frame_box_queue = self.q_console.frame4mark_queue
        self.d_infos_map: Dict[str, List[DetectInfo]] = {}
        self.d_infos_list = []

    def _sub_work_before_cleaned_up(self, work_req):
        pass

    def _sub_init_work(self, work_req):
        pass

    @classmethod
    def _draw_spot_area(cls, frame, x, y, w, h, line_width=50,
                        color=(255, 255, 255), thickness=5):

        cv2.line(frame, (x, y), (x + line_width, y), color, thickness)
        cv2.line(frame, (x + w, y), (x + w - line_width, y),
                 color, thickness)

        cv2.line(frame, (x, y), (x, y + line_width), color, thickness)
        cv2.line(frame, (x + w, y), (x + w, y + line_width),
                 color, thickness)

        cv2.line(frame, (x, y + h), (x + line_width, y + h),
                 color, thickness)
        cv2.line(frame, (x + w, y + h), (x + w - line_width, y + h),
                 color, thickness)

        cv2.line(frame, (x, y + h), (x, y - line_width + h),
                 color, thickness)
        cv2.line(frame, (x + w, y + h), (x + w, y - line_width + h),
                 color, thickness)

    def _landmarks(self, frame: np.ndarray, detect_infos: List[DetectInfo]):
        cx, cy, cw, ch = self.q_console.camera.center_box

        self._draw_spot_area(frame, cx, cy, cw, ch)

        if not detect_infos:
            return frame

        for detect_info in detect_infos:
            class_color = detect_info.suggest_color
            display_text = (f"{detect_info.label}: "
                            f"{round(detect_info.confidence, 4)}")
            x, y, w, h = detect_info.bbox

            whole_area = detect_info.width * detect_info.height
            if detect_info.area < whole_area * self.MIN_AREA:
                continue

            # 标记中心点
            cv2.circle(frame, detect_info.center_point, 1, class_color,
                       thickness=2)

            text_font = int(w * 0.005)
            text_font = max(1, text_font)
            cv2.rectangle(frame, (x, y), (x + w, y + h), class_color, 1)
            cv2.putText(frame, display_text, (x + 5, y + text_font * 15),
                        cv2.FONT_HERSHEY_PLAIN, text_font,
                        class_color, text_font + 1)

            line_width = int(w * 0.15)

            self._draw_spot_area(frame, x, y, w, h, color=class_color,
                                 thickness=8, line_width=line_width)

        return frame

    # @time_cost_log
    def _select_d_infos(self, frame_id):
        if frame_id not in self.d_infos_map:
            self.d_infos_map.clear()

        select_num = 0
        while True:
            d_infos: List[DetectInfo] = self.get_queue_item(
                self.q_console.detect_infos_queue, timeout=5, wait_item=True)
            if not d_infos:
                continue

            d_frame_id = d_infos[0].frame_id
            self.d_infos_map.setdefault(d_frame_id, [])
            self.d_infos_map[d_frame_id].extend(d_infos)
            if d_frame_id != frame_id:
                break
            select_num += 1
            if select_num >= self.q_console.detect_worker_num.value:
                break

        return [d_info for d_info in
                self.d_infos_map.get(frame_id, [])
                if d_info.is_detected]

    def _handle_start_req(self, work_req: WorkerStartReq) -> bool:
        frame_box: FrameBox = self.get_queue_item(
            self.q_console.frame4mark_queue, timeout=5, wait_item=True)
        if frame_box is None:
            return False

        frame_box.put_delay_text(tag="markB")
        d_infos: List[DetectInfo] = self._select_d_infos(frame_box.frame_id)

        marked_frame = self._landmarks(frame_box.frame, d_infos)
        frame_box.update(marked_frame, is_marked=True)

        if frame_box.frame_id in self.d_infos_map:
            self.d_infos_map.pop(frame_box.frame_id)

        frame_box.put_delay_text(tag="markA")
        # print(f"{len(self.d_infos_map)}")
        self.put_queue_item(self.q_console.render_frame_queue, frame_box,
                            force_put=True)
        self.put_queue_item(self.q_console.frame4record_queue,
                            frame_box, force_put=True)

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


if __name__ == "__main__":
    marker = Marker()
    marker.simple_test()
