import os
import logging
from typing import *
from datetime import datetime, timedelta

import numpy as np
import cv2

from watchdog.utils.util_camera import FrameBox
from watchdog.utils.util_video import H264Writer
from watchdog.configs.constants import PathConfig, CameraConfig
from watchdog.services.path_service import get_cache_videos
from watchdog.models.worker_req import WorkerEndReq, VidRecStartReq
from watchdog.services.base.wd_base_worker import WDBaseWorker


class VidRec(WDBaseWorker):
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
            self.q_console.camera.video_fps,
            (self.q_console.camera.video_width,
             self.q_console.camera.video_height),
            True,
        )

    def _update_vid_rec_req_info(self, work_req: VidRecStartReq):
        if self.rec_req is None:
            self.rec_req = work_req
            return

        if not work_req.is_new:
            return

        now_rec_secs = self.working_handled_num / self.rec_req.active_fps
        left_secs = self.rec_req.rec_secs - now_rec_secs

        plus_rec_secs = work_req.rec_secs - left_secs
        if plus_rec_secs > 0:
            self.rec_req.rec_secs += plus_rec_secs
            logging.info(f"[{self.worker_name}] plus record time + "
                         f"{plus_rec_secs} secs [{work_req.raw_tag}]")

        self.rec_req.m_time = work_req.c_time
        self._work_req = self.rec_req

    def _sub_init_work(self, work_req: VidRecStartReq):
        """
        :param work_req:
        :return:
        """
        self._clean_expired_videos()
        self.q_console.active_camera(tag="start record video")
        self._update_vid_rec_req_info(work_req)
        self._update_video_writer()

    def _handle_start_req(self, work_req: VidRecStartReq) -> bool:
        """
            开始获取视频帧队列，并写入
        :param work_req:
        :return:
        """
        self._update_vid_rec_req_info(work_req)
        return self._write_one()

    def _write_one(self) -> bool:
        """
        :return: 返回是否停止录制工作
        """

        frame_box: FrameBox = self.get_queue_item(
            self.frame_queue, queue_name="frame_queue",
            timeout=0.2)

        if frame_box is None:
            return False
        elif isinstance(frame_box.frame, np.ndarray):
            self.video_writer.write(frame_box.frame)
            self.plus_working_handled_num()
        else:
            logging.warning(f"[{self.worker_name}] Wrong type frame, "
                            f"not ndarray but {type(frame_box.frame)}")

        target_frame_num = self.rec_req.rec_secs * self.rec_req.active_fps
        if (self.working_handled_num >= target_frame_num
                and self.q_console.monitor_states.is_now_active()):
            work_req = VidRecStartReq(tag="still active")
            work_req.is_new = True
            self._update_vid_rec_req_info(work_req)

        target_frame_num = self.rec_req.rec_secs * self.rec_req.active_fps
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
            self.video_writer = None
            logging.info(f"[{self.worker_name}] End of recording："
                         f"{self.rec_req.write_filepath}, "
                         f"remain: {self.frame_queue.qsize()}")

        if self.rec_req is not None:
            self.q_console.rest_camera(tag="video record end")
            self.rec_req: Optional[VidRecStartReq] = None

    def _sub_clear_all_output_queues(self):
        self._sub_work_done_cleaned_up(None)

    def _clean_expired_videos(self):
        videos = get_cache_videos()
        tt = datetime.now() - timedelta(
            days=CameraConfig.CACHE_DAYS.value)
        tt_str = tt.strftime("%Y-%m-%d-%H-%M-%S-%f")
        removes = []
        for t in videos:
            _t = t[:t.rindex("-")]
            if _t < tt_str:
                removes.append(t)

        for r in removes:
            filepath = os.path.join(PathConfig.CACHE_DATAS_PATH, r)
            if os.path.exists(filepath):
                os.remove(filepath)
                logging.info(f"[{self.worker_name}] remove expired video: "
                             f"{filepath}")


class VidRecH264(VidRec):
    """
        H264编码视频：存储占用小，主流播放格式
    """

    def _update_video_writer(self):
        self.video_writer = H264Writer(self.rec_req.write_filepath,
                                       fps=self.q_console.camera.video_fps,
                                       bit_rate=1024 * 500)
