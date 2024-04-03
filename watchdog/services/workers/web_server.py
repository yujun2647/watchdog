from typing import *
from threading import Event as TEvent
from queue import Empty

from flask import Flask

from watchdog.utils.util_thread import new_daemon_thread
from watchdog.utils.util_router import load_routes_to_flask
from watchdog.utils.util_camera import FrameBox
from watchdog.configs.constants import PathConfig
from watchdog.models.worker_req import WorkerEndReq, WorkerStartReq
from watchdog.services.base.wd_base_worker import WDBaseWorker


class WebServer(WDBaseWorker):
    def __sub_init__(self, **kwargs):
        self.app: Optional[Flask] = None
        self._live_frame: Optional[FrameBox] = None
        self._live_frame_come = TEvent()

    @property
    def live_frame(self):
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

    def _sub_work_before_cleaned_up(self, work_req):
        pass

    def _sub_init_work(self, work_req):
        self.preloading_live_frame2()
        self.app = Flask(__name__,
                         root_path=PathConfig.PROJECT_PATH,
                         template_folder="templates",
                         static_folder="static")

        load_routes_to_flask(self.app)

    def _handle_start_req(self, work_req: WorkerStartReq) -> bool:
        port = work_req.req_msg.get("port", None)
        assert port, f"port must be set, now: {port}"
        self.app.run(host="0.0.0.0", port=port)

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
