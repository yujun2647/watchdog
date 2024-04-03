import os
from typing import *
import json
import logging
import traceback
from queue import Empty

import cv2
import numpy as np
from werkzeug.exceptions import HTTPException
from flask import make_response, Response, render_template, send_file

from watchdog.utils.util_router import Route
from watchdog.utils.util_camera import FrameBox
from watchdog.configs.constants import PathConfig
from watchdog.services.path_service import get_cache_videos
from watchdog.server.api_handlers.base_handler import BaseHandler

if TYPE_CHECKING:
    from watchdog.services.workshop import WorkShop


@Route("/")
class WatchDogIndex(BaseHandler):
    @classmethod
    def make_ok_response(cls, result):
        return result

    def get(self, *args, **kwargs):
        return render_template("index.html")


class WatchDogHandler(WatchDogIndex):
    LOG_RESPONSE = True

    def prepare(self):
        """
        Called at the beginning of a request before  `get`/`post`/etc.
        """
        request_data = json.dumps(self.request_data, ensure_ascii=False,
                                  indent=4)
        logging.info(f"[API] -- {self.request.path} -- "
                     f"request_datas: {request_data}")

    def handle_exception(self, exp):
        if isinstance(exp, HTTPException):
            return exp
        logging.error(traceback.format_exc())
        error_name = type(exp).__name__
        error_msg = str(exp)
        tb_stacks = traceback.format_tb(exp.__traceback__)
        error_file = tb_stacks[-1].strip().replace("\n", "") \
            .replace("File \"", "").replace("\"", "")
        rsp = make_response(dict(code=500,
                                 status="Error",
                                 errorName=error_name,
                                 errorMsg=error_msg,
                                 errorFile=error_file,
                                 data=None), 500)
        rsp.headers['Content-Type'] = 'application/json'
        rsp.headers['Access-Control-Allow-Origin'] = "*"  # 设置允许跨域
        return rsp

    def handle_upload(self, upload_name, save_dir, save_filename=None):
        return super().handle_upload(
            upload_name=upload_name,
            save_dir=save_dir,
            save_filename=save_filename)

    @classmethod
    def process_event_id(cls, event_id):
        return event_id.replace('"', "")

    @classmethod
    def to_int(cls, data):
        return int(data)

    @classmethod
    def get_response(cls, code=0, status='success', data=None):
        response = dict(code=code, status=status)
        if data is not None and isinstance(data, dict):
            response.update(data)
        else:
            response["data"] = data
        # noinspection PyBroadException
        try:
            response_str = json.dumps(response, ensure_ascii=False, indent=4)
        except Exception as exp:
            logging.error(f"[Waning] response data in is not JSON serializable:"
                          f"{response}")
            raise exp
        if cls.LOG_RESPONSE:
            logging.info(f"[Response]: {response_str}")
        return make_response(response)


@Route("/echo")
class WatchCameraHandler(BaseHandler):
    WORKSHOP_MAP: Dict[str, "WorkShop"] = {}

    @classmethod
    def load_workshop(cls, camera_address: [int, str], workshop: "WorkShop"):
        if not isinstance(camera_address, str):
            camera_address = str(camera_address)
        cls.WORKSHOP_MAP[camera_address] = workshop

    @classmethod
    def get_workshop(cls, camera_address=None) -> "WorkShop":
        if camera_address is None:
            for _, value in cls.WORKSHOP_MAP.items():
                return value

        return cls.WORKSHOP_MAP.get(camera_address, None)

    def get(self):
        return dict(server="watchdog",
                    version=os.environ.get("VERSION"))


@Route("/stream")
class WatchStream(WatchCameraHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.work_shop = self.get_workshop()
        self.q_console = self.work_shop.q_console
        self.last: Optional[FrameBox] = None

    @classmethod
    def make_ok_response(cls, view_request_gen):
        return Response(
            view_request_gen,
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @classmethod
    def encode(cls, frame: np.ndarray):
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 17]
        result, jpeg = cv2.imencode('.jpg', frame, encode_param)
        return jpeg.tobytes()

    def get_byte_frame2(self):
        try:
            if self.last is None:
                frame_box = self.work_shop.web_server.live_frame
            else:
                if not self.last.next_come.wait(timeout=5):
                    raise Empty
                frame_box = self.last.next
            self.last = frame_box
            return self.encode(frame_box.frame)
        except Empty:
            return

    def handle_view_request(self):
        """
        :return:
        """
        byte_frame = None
        while True:
            try:
                self.q_console.latest_view_time.update()
                byte_frame = self.get_byte_frame2()
            except Exception as exp:
                logging.error(f"{exp}, {traceback.format_exc()}")
            if byte_frame is not None:
                yield (
                        b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n"
                        + byte_frame + b"\r\n\r\n"
                )

    def get(self):
        return self.handle_view_request()


@Route("/check_records")
class RecordHandler(WatchDogHandler):

    def get(self):
        return get_cache_videos()


@Route("/check_video/<video_name>")
class CheckVideo(WatchDogHandler):

    @classmethod
    def make_ok_response(cls, result):
        return result

    def get(self, video_name):
        video_filepath = os.path.join(PathConfig.CACHE_DATAS_PATH, video_name)
        if not os.path.exists(video_filepath):
            raise FileNotFoundError(f"file {video_filepath} not exist")
        return send_file(video_filepath)
