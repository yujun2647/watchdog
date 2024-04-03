import time
from typing import *
from queue import Empty, Queue as TQueue
from threading import Event as TEvent

from watchdog.server.custom_server import EnhanceThreadedWSGIServer
from watchdog.configs.constants import CameraConfig

from watchdog.server.api_handlers.watch_handler import WatchCameraHandler
from watchdog.utils.util_camera import FrameBox
from watchdog.utils.util_thread import new_daemon_thread
from watchdog.services.workers.marker import Marker
from watchdog.services.workers.web_server import WebServer
from watchdog.services.workers.video_recorder import VidRecH264
from watchdog.services.wd_queue_console import WdQueueConsole
from watchdog.services.workers.monitor import Monitor
from watchdog.services.workers.frame_distributor import FrameDistributor
from watchdog.services.workers.detect.common_detector import CommonDetector


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
                 video_height=None, server_port=8000):
        self.q_console = WdQueueConsole.init_default(
            camera_address=camera_address,
            fps=CameraConfig.REST_FPS.value, detect_worker_num=1,
            video_width=video_width,
            video_height=video_height)

        self.frame_dst = FrameDistributor(q_console=self.q_console)

        self.marker = Marker(q_console=self.q_console)
        self.c_detector = CommonDetector(q_console=self.q_console)
        self.monitor = Monitor(q_console=self.q_console)
        self.vid_recorder = VidRecH264(
            q_console=self.q_console,
            work_req_queue=self.q_console.recorder_req_queue)
        self.web_server = WebServer(q_console=self.q_console)

        self.marker.send_start_work_req()
        self.c_detector.send_start_work_req()
        self.monitor.send_start_work_req()
        self.frame_dst.send_start_work_req()
        self.web_server.send_start_work_req(req_msg=dict(port=server_port))

        self._live_frame: Optional[FrameBox] = None
        self._live_frame_come = TEvent()

        self.monitor_camera_restart_sig()

        WatchCameraHandler.load_workshop(camera_address, self)
        self.marker.start_work_in_subprocess()
        self.monitor.start_work_in_subprocess()
        self.c_detector.start_work_in_subprocess()
        self.frame_dst.start_work_in_subprocess()
        self.vid_recorder.start_work_in_subprocess()
        self.web_server.start_work_in_subprocess(daemon=True)

    @new_daemon_thread
    def monitor_camera_restart_sig(self):
        while True:
            if self.q_console.camera_restart_sig.wait(timeout=5):
                EnhanceThreadedWSGIServer.add_service_action(
                    action_callback=self.q_console.camera.restart,
                    kwargs=dict(timeout=60),
                    timeout=60
                )
                self.q_console.camera_restart_sig.clear()

    @property
    def live_frame(self) -> FrameBox:
        if not self._live_frame_come.wait(timeout=5):
            raise Empty
        return self._live_frame

    @new_daemon_thread
    def preloading_live_frame2(self):
        render_frame_queue = self.q_console.render_frame_queue

        camera_active = False
        while True:
            if not camera_active and self.q_console.cam_viewing():
                self.q_console.active_camera(tag="view request")
                camera_active = True
            elif camera_active and not self.q_console.cam_viewing():
                self.q_console.rest_camera(tag="view request end")
                camera_active = False

            frame_box: FrameBox = render_frame_queue.get()
            frame_box.put_delay_text("final")
            frame_box.next_come = TEvent()
            if self._live_frame is None:
                self._live_frame = frame_box
                self._live_frame_come.set()
                continue
            self._live_frame.next = frame_box
            self._live_frame.next_come.set()
            self._live_frame = frame_box

    def test_monitor(self):
        from cv2 import cv2
        while True:
            frame_box: FrameBox = self.q_console.render_frame_queue.get()
            frame_box.put_delay_text("final")
            cv2.imshow("frame", frame_box.frame)
            cv2.waitKey(1)
