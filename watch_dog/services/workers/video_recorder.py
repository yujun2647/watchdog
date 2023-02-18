import logging
from typing import *

import numpy as np
from cv2 import cv2

from watch_dog.utils.util_camera import FrameBox
from watch_dog.utils.util_video import H264Writer
from watch_dog.models.worker_req import WorkerEndReq, VidRecStartReq
from watch_dog.services.base.wd_base_worker import WDBaseWorker


class VidRecorder(WDBaseWorker):
    """
        默认 mp4v 编码视频：mpeg4压缩标准视频，只有图像没有声音
    """

    RECORD_FILENAME = "src.mp4"

    def __sub_init__(self, **kwargs):
        self.video_writer: Optional[cv2.VideoWriter, H264Writer] = None
        self.frame_queue = self.q_console.frame4record_queue

        self.rec_req: Optional[VidRecStartReq] = None
        self.record_fps = 25

    def _sub_work_before_cleaned_up(self, work_req):
        pass

    def _sub_side_work(self):
        pass

    def _handle_worker_exception(self, exp):
        pass

    def _update_video_writer(self):
        self.video_writer = cv2.VideoWriter(
            self.rec_req.write_filepath,
            cv2.VideoWriter_fourcc(*"mp4v"),
            self.rec_req.rec_fps,
            (self.q_console.camera.video_width,
             self.q_console.camera.video_height),
            True,
        )

    def _update_vid_rec_req_info(self, rec_req: VidRecStartReq):

        if self.rec_req is None:
            self.rec_req = rec_req
            return

        if rec_req.c_time in (self.rec_req.c_time, self.rec_req.m_time):
            return

        now_rec_secs = self.working_handled_num / self.rec_req.rec_fps
        left_secs = self.rec_req.rec_secs - now_rec_secs

        plus_rec_secs = rec_req.rec_secs - left_secs
        if plus_rec_secs > 0:
            self.rec_req.rec_secs += plus_rec_secs
            logging.info(f"[{self.worker_name}] plus record time + "
                         f"{plus_rec_secs} secs")

        self.rec_req.m_time = rec_req.c_time

    def _sub_init_work(self, rec_req: VidRecStartReq):
        """
        :param rec_req:
        :return:
        """
        self.q_console.camera.adjust_camera_fps(rec_req.rec_fps)
        self._update_vid_rec_req_info(rec_req)
        self._update_video_writer()

    def _handle_start_req(self, rec_req: VidRecStartReq) -> bool:
        """
            开始获取视频帧队列，并写入
        :param rec_req:
        :return:
        """
        self._update_vid_rec_req_info(rec_req)
        return self._write_one()

    def _write_one(self) -> bool:
        """
        :return: 返回是否停止录制工作
        """

        frame_box: FrameBox = self.get_queue_item(
            self.frame_queue, queue_name="frame_queue")
        if frame_box is None:
            return False

        elif isinstance(frame_box.frame, np.ndarray):
            self.video_writer.write(frame_box.frame)
            self.working_handled_num += 1
        else:
            logging.warning(f"[{self.worker_name}] Wrong type frame, "
                            f"not ndarray but {type(frame_box.frame)}")

        target_frame_num = self.rec_req.rec_secs * self.rec_req.rec_fps
        return self.working_handled_num >= target_frame_num

    def _handle_end_req(self, work_req: WorkerEndReq) -> bool:
        """
        :param work_req:
        :return:
        """
        return self._write_one()

    def _sub_work_done_cleaned_up(self, work_req):
        if self.video_writer is not None and self.video_writer.isOpened():
            self.video_writer.release()

        if self.rec_req is not None:
            self.q_console.camera.adjust_camera_fps(self.rec_req.lazy_fps)
            self.rec_req: Optional[VidRecStartReq] = None

    def _sub_clear_all_output_queues(self):
        self._sub_work_done_cleaned_up(None)


class VidRecorderH264(VidRecorder):
    """
        H264编码视频：存储占用小，主流播放格式
    """

    def _update_video_writer(self):
        self.video_writer = H264Writer(self.rec_req.write_filepath,
                                       fps=self.rec_req.rec_fps)
