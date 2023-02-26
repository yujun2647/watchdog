import os
from typing import *
import json
import logging
import traceback
from queue import Empty
from threading import Event as TEvent

import cv2
import numpy as np
from werkzeug.exceptions import HTTPException
from flask import make_response, Response, render_template, send_file

from watch_dog.utils.util_router import Route
from watch_dog.utils.util_camera import FrameBox
from watch_dog.utils.util_log import time_cost_log
from watch_dog.configs.constants import PathConfig
from watch_dog.services.workshop import WorkShop
from watch_dog.server.api_handlers.base_handler import BaseHandler


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
    WORKSHOP_MAP: Dict[str, WorkShop] = {}

    @classmethod
    def load_workshop(cls, camera_address: [int, str], workshop: WorkShop):
        if not isinstance(camera_address, str):
            camera_address = str(camera_address)
        cls.WORKSHOP_MAP[camera_address] = workshop

    @classmethod
    def get_workshop(cls, camera_address=None) -> WorkShop:
        if camera_address is None:
            for _, value in cls.WORKSHOP_MAP.items():
                return value

        return cls.WORKSHOP_MAP.get(camera_address, None)

    def get(self):
        return "working"


@Route("/stream")
class WatchStream(WatchCameraHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.work_shop = self.get_workshop()
        self.q_console = self.work_shop.q_console
        self.fetched_frame_signal = TEvent()
        self.fetched_frame_signal.set()
        self.last: Optional[FrameBox] = None

    @classmethod
    def make_ok_response(cls, view_request_gen):
        return Response(
            view_request_gen,
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @classmethod
    def encode(cls, frame: np.ndarray):
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 20]
        result, jpeg = cv2.imencode('.jpg', frame, encode_param)
        return jpeg.tobytes()

    def get_byte_frame(self):
        frame_queue = self.q_console.render_frame_queue
        live_frame = self.q_console.live_frame
        try:
            if (self.last and self.q_console.live_frame
                    and live_frame.frame_ctime > self.last.frame_ctime):
                frame_box: FrameBox = self.q_console.live_frame
            else:
                frame_box: FrameBox = frame_queue.get(timeout=0.5)
                frame_box.put_delay_text(tag="final")
                self.q_console.live_frame = frame_box
            self.last = frame_box
            return self.encode(frame_box.frame)
        except Empty:
            if (self.last and self.q_console.live_frame
                    and live_frame.frame_ctime > self.last.frame_ctime):
                frame_box: FrameBox = self.q_console.live_frame
                self.last = frame_box
                return self.encode(frame_box.frame)
            return

    def handle_view_request(self):
        """
        :return:
        """
        byte_frame = None
        while True:
            try:
                self.work_shop.consuming_req_event.set()
                byte_frame = self.get_byte_frame()
            except Exception as exp:
                logging.error(f"{exp}, {traceback.format_exc()}")
            if byte_frame is not None:
                self.work_shop.consuming_req_event.clear()
                yield (
                        b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n"
                        + byte_frame + b"\r\n\r\n"
                )

    def get(self):
        self.work_shop.notify_consume_req()
        return self.handle_view_request()


@Route("/check_records")
class RecordHandler(WatchDogHandler):

    def get(self):
        try:
            _, _, videos = next(os.walk(PathConfig.CACHE_DATAS_PATH))
        except StopIteration:
            return []

        videos = [v for v in videos if v.endswith(".mp4")]
        videos.sort(key=lambda v: v[:v.rindex("-")], reverse=True)
        return videos


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
