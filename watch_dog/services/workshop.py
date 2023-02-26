import time
from typing import *
import logging
from queue import Empty, Queue as TQueue
from threading import Event as TEvent, Lock as TLock

from watch_dog.configs.constants import CameraConfig

from watch_dog.utils.util_camera import FrameBox
from watch_dog.utils.util_thread import new_thread
from watch_dog.services.workers.marker import Marker
from watch_dog.services.workers.video_recorder import VidRecH264
from watch_dog.services.wd_queue_console import WdQueueConsole
from watch_dog.services.workers.monitor import Monitor
from watch_dog.services.workers.frame_distributor import FrameDistributor
from watch_dog.services.workers.detect.common_detector import CommonDetector


class TimeTQueue(TQueue):

    def __init__(self, maxsize=0):
        super().__init__(maxsize=maxsize)
        self.ctime = time.perf_counter()
        self.mtime = time.perf_counter()

    def get(self, block=True, timeout=None):
        t = super().get(block=block, timeout=timeout)
        self.mtime = time.perf_counter()
        return t

    @property
    def break_time(self):
        return time.perf_counter() - self.mtime


class WorkShop(object):

    def __init__(self, camera_address, video_width=None,
                 video_height=None):
        self.q_console = WdQueueConsole.init_default(
            camera_address=camera_address,
            fps=CameraConfig.REST_FPS.value, detect_worker_num=1,
            video_width=video_width,
            video_height=video_height)

        self._stop_load_event = TEvent()
        self.consume_req_event = TEvent()
        self.consuming_req_event = TEvent()

        self._live_frame_queues: List[TimeTQueue] = []
        self._live_queues_lock = TLock()

        self.frame_dst = FrameDistributor(q_console=self.q_console)

        self.marker = Marker(q_console=self.q_console)
        self.c_detector = CommonDetector(q_console=self.q_console)
        self.monitor = Monitor(q_console=self.q_console)
        self.vid_recorder = VidRecH264(
            q_console=self.q_console,
            work_req_queue=self.q_console.recorder_req_queue)

        self.marker.send_start_work_req()
        self.c_detector.send_start_work_req()
        self.monitor.send_start_work_req()
        self.frame_dst.send_start_work_req()

        self.marker.start_work_in_subprocess()
        self.monitor.start_work_in_subprocess()
        self.c_detector.start_work_in_subprocess()
        self.frame_dst.start_work_in_subprocess()
        self.vid_recorder.start_work_in_subprocess()

        self.preloading_live_frame()

    def register_view_request(self) -> TimeTQueue:
        with self._live_queues_lock:
            ttq = TimeTQueue()
            self._live_frame_queues.append(ttq)
            return ttq

    def notify_consume_req(self):
        self.consume_req_event.set()

    @new_thread
    def preloading_live_frame(self):
        render_frame_queue = self.q_console.render_frame_queue

        while True:
            if self._stop_load_event.is_set():
                return
            if not self.consume_req_event.is_set():
                # print("no consume req...")
                time.sleep(0.5)
                continue

            if not self.consuming_req_event.wait(timeout=5):
                logging.info("No consuming req event, exit preload")
                self.consume_req_event.clear()
                self._live_frame_queues.clear()
                continue
            try:
                frame_box: FrameBox = render_frame_queue.get(timeout=5)
                frame_box.put_delay_text(tag="final")
                with self._live_queues_lock:
                    expires = []
                    for queue in self._live_frame_queues:
                        if queue.break_time > 30:
                            expires.append(queue)
                            continue
                        queue.put(frame_box)
                    for queue in expires:
                        self._live_frame_queues.remove(queue)
                        logging.info(f"queue: {queue.break_time} expired, "
                                     f"removed")

                self.q_console.live_frame = frame_box
            except Empty:
                continue
