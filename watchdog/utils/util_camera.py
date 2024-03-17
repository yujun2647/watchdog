import os
import json
import time
import logging
import traceback
from typing import *
from queue import Empty
from threading import Event as TEvent
import multiprocessing as mp
from urllib.parse import urlparse

import cv2
import numpy as np
import setproctitle
from hikvisionapi import Client
from tqdm import tqdm

from watchdog.utils.util_time import Timer
from watchdog.utils.util_uuid import unique_time_id
from watchdog.utils.util_rtsp import RTSPCapture
from watchdog.utils.util_video import H264Writer
from watchdog.utils.util_log import time_cost_log
from watchdog.utils.util_os import run_sys_command
from watchdog.utils.util_thread import execute_by_thread
from watchdog.utils.util_v4l2 import get_videocap_devices
from watchdog.utils.util_multiprocess.process import (
    new_process, ProcessController)
from watchdog.utils.util_multiprocess.queue import (clear_queue, FastQueue,
                                                    clear_queue_cache)
from watchdog.utils.util_multiprocess.lock import BetterRLock
from watchdog.utils.util_net import is_connected, get_host_name
from watchdog.utils.util_hik_net_audio_controller import HIKNetAudioController
from watchdog.models.health_info import HealthRspInfo

__all__ = [
    "CameraParams", "FrameBox", "CameraAddressUtil", "MultiprocessCamera",
    "MultiprocessVideoCapture"
]

if TYPE_CHECKING:
    from threading import RLock


class _CameraRegisteredError(Exception):
    pass


class CameraParams(object):

    def __init__(self, video_fps, video_width, video_height):
        self.video_fps = video_fps
        self.video_width = video_width
        self.video_height = video_height

    def opencv_params(self):
        return {
            cv2.CAP_PROP_FPS: self.video_fps,
            cv2.CAP_PROP_FRAME_WIDTH: self.video_width,
            cv2.CAP_PROP_FRAME_HEIGHT: self.video_height
        }

    @classmethod
    def from_opencv_params(cls, opencv_params: dict) -> "CameraParams":
        return CameraParams(
            video_fps=opencv_params.get(cv2.CAP_PROP_FPS),
            video_width=opencv_params.get(cv2.CAP_PROP_FRAME_WIDTH),
            video_height=opencv_params.get(cv2.CAP_PROP_FRAME_HEIGHT)

        )

    def size_equal(self, camera_params: "CameraParams"):
        # 不考虑 fps
        return (self.video_width == camera_params.video_width
                and self.video_height == camera_params.video_height)


class FrameBox(object):

    def __init__(self, frame: Optional[np.ndarray] = None, is_marked=False,
                 fps=25):
        self.is_marked = is_marked
        self.fps = fps
        self._marked_frame: Optional[np.ndarray] = None
        self._raw_frame: Optional[np.ndarray] = None
        if self.is_marked:
            self._marked_frame = frame
        else:
            self._raw_frame = frame

        self.frame_ctime = time.perf_counter()
        self.frame_mtime = time.perf_counter()
        self.frame_id = unique_time_id()

        self._last_delay_y = 0
        self.last_xy = (0, 0)

        # 用于在多线程中赋值/获取 下一帧，不支持多进程共享
        self.next: Optional[FrameBox] = None
        # 用于在多线程中判断下一帧是否已存在
        self.next_come: Optional[TEvent] = None

    def update(self, frame: Optional[np.ndarray] = None, is_marked=False):
        self.is_marked = is_marked
        if self.is_marked:
            self._marked_frame = frame
        else:
            self._raw_frame = frame

        self.frame_mtime = time.perf_counter()

    @property
    def frame(self) -> np.ndarray:
        return self._marked_frame if self.is_marked else self._raw_frame

    @frame.setter
    def frame(self, frame: np.ndarray):
        if self.is_marked:
            self._marked_frame = frame
        else:
            self._raw_frame = frame

    def get_age_ms(self):
        return int(round((time.perf_counter() - self.frame_ctime) * 1000, 0))

    def get_age(self):
        return time.perf_counter() - self.frame_ctime

    def frame_size(self):
        return self.frame.shape[1], self.frame.shape[0]

    def put_delay_text(self, tag="_____"):
        frame = self.frame
        height = frame.shape[0]
        width = frame.shape[1]
        tag = tag.ljust(10)
        time_cost = f"{self.get_age_ms()} ms"
        time_cost = time_cost.rjust(6)
        # time_cost = f": {time_cost}"
        text = f"{tag}{time_cost}"
        text_size, baseline = cv2.getTextSize(
            text, cv2.FONT_HERSHEY_PLAIN, 2, 3)

        x = int(width - text_size[0] - width * 0.01)
        y = int(height * 0.05) + int(text_size[1] / 2)

        if self._last_delay_y:
            y = self._last_delay_y + int(text_size[1] * 1.5)

        if width - x < text_size[0]:
            x = width - text_size[0]
        if height - y < text_size[1]:
            y = height - text_size[1] * 2

        cv2.putText(self.frame,
                    text,
                    (x, y),
                    cv2.FONT_HERSHEY_PLAIN, 2, (255, 255, 0), 3)
        self._last_delay_y = y
        self.last_xy = text_size


class CameraAddressUtil(object):
    WEB_CAM_PROTOCOLS = ("rtsp", "http", "hls", "rtmp")

    @classmethod
    def is_web_cam_address(cls, address: [str, int]):
        if not isinstance(address, str):
            return False

        for protocol in cls.WEB_CAM_PROTOCOLS:
            if protocol in address:
                return True
        return False

    @classmethod
    def is_hik_web_cam_address(cls, address: [str, int]):
        if not cls.is_web_cam_address(address):
            return False
        parse_ret = urlparse(address)
        host_name = parse_ret.hostname

        def _ensure_connected():
            for i in range(50):
                if is_connected(host_name):
                    return True
                logging.warning(f"[Camera-Audio] address host_name: {host_name}"
                                f"is not connected, try again: {i + 1}")
                time.sleep(0.5)
            return False

        if not _ensure_connected():
            return False

        client = Client(f'http://{host_name}', parse_ret.username,
                        parse_ret.password,
                        timeout=30)
        # noinspection PyBroadException
        try:
            rsp_list = client.Event.notification.alertStream(
                method='get', type='stream')
            rsp_str = json.dumps(rsp_list)
            return "hikvision" in rsp_str

        except Exception:
            return False

    @classmethod
    def is_file_address(cls, address: [str, int]):
        if not isinstance(address, str):
            return False
        if (os.path.exists(address) and not cls.is_web_cam_address(address)
                and not cls.is_usb_camera(address)):
            return True
        return False

    @classmethod
    def is_usb_camera(cls, address: [str, int]):
        address = str(address).strip()
        if address.isdigit() and os.path.exists(f"/dev/video{address}"):
            return True
        elif "/dev/video" in address and os.path.exists(address):
            return True
        else:
            return False

    @classmethod
    def is_camera_address(cls, address):
        return (cls.is_web_cam_address(address)
                or cls.is_file_address(address)
                or cls.is_usb_camera(address))

    @classmethod
    def _failed_retry(cls, address, now_try_times):
        logging.warning(f"Connect camera `{address}` failed, "
                        f"try again {now_try_times - 1}....")
        time.sleep(0.5)
        return cls.camera_is_available(address, now_try_times - 1)

    @classmethod
    def is_address_available(cls, address):
        """
        【注意】这里不是相机是否可用的最终判断，最终判断通过 cv2.VideoCapture，
              但有可能会很耗时，所以先进行前置判断，节省判断时间

        相机地址是否可用的前置判断，如
            视频文件地址是否存在
            网络摄像头地址的域名/ip 是否可访问
            usb摄像头地址是否存在 对应的 /dev/video*
        :param address:
        :return:
        """
        if not cls.is_camera_address(address):
            return False

        # cls.is_camera_address(address) 中判断 视频文件 和 usb摄像头 已经会检查
        # 是否存在 视频地址， 所以这里只需要检查 网络摄像头 ip 是否可访问
        if cls.is_web_cam_address(address):
            host_name = get_host_name(address)
            return is_connected(host_name, time_out=0.5)

        return True

    @classmethod
    def force_release_usb_camera(cls, usb_camera_address: Optional[str] = None):
        """
        :param usb_camera_address: 若为None, 则释放所有相机， 否则只释放指定的相机
        :return:
        """

        if str(usb_camera_address).isdigit():
            usb_camera_address = f"/dev/video{usb_camera_address}"

        this_pid = os.getpid()
        if usb_camera_address is not None:
            run_sys_command(
                f"lsof {usb_camera_address} "
                "| grep '/dev/video' "
                "| awk '{print $2}' "
                f"| grep -v {this_pid} "
                "|xargs kill -9",
                raise_if_failed=False)
        else:
            run_sys_command(
                "lsof /dev/video* | grep '/dev/video' "
                "| awk '{print $2}' "
                f"| grep -v {this_pid} "
                "| xargs kill -9",
                raise_if_failed=False)

    @classmethod
    def camera_is_available(cls, address, try_times=1):
        if try_times < 0:
            logging.warning(f"Reach the max try time of `{address}`,"
                            f" give up")
            return False
        stream = None
        logging.info(f"checking camera `{address}` is available")
        # noinspection PyBroadException
        try:
            if cls.is_usb_camera(address):
                # 保险起见，释放所有相机
                cls.force_release_usb_camera(address)

            if not cls.is_camera_address(address):
                logging.warning(f"camera `{address}` is not valid camera "
                                f"address !!")
                return False

            if not cls.is_address_available(address):
                return cls._failed_retry(address, try_times)

            # 重启测试这里遇到过阻塞，因此这里放到子线程中处理
            logging.info(f"camera `{address}` init VideoCapture")
            stream = execute_by_thread(target=lambda: cv2.VideoCapture(address),
                                       wait_timeout=5)
            if stream is None:
                logging.warning(f"camera `{address}` init VideoCapture failed,"
                                f"try again")
                return cls._failed_retry(address, try_times)

            logging.info(f"camera `{address}` init VideoCapture Done")
            stream.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            stream.set(cv2.CAP_PROP_FPS, 30)
            logging.info(f"camera `{address}` checking isOpened")

            if not stream.isOpened():
                logging.info(f"camera `{address}` is not opened, "
                             f"release and try again")
                stream.release()
                return cls._failed_retry(address, try_times)
            logging.info(f"camera `{address}` isOpened, try to read ...")

            # 重启测试这里遇到过阻塞，因此这里放到子线程中处理
            read_result = execute_by_thread(target=lambda: stream.read(),
                                            wait_timeout=20)
            if read_result is None:
                logging.warning(f"camera `{address}` read timeout, try again")
                stream.release()
                return cls._failed_retry(address, try_times)

            grabbed, _frame = read_result
            if not grabbed:
                stream.release()
                logging.warning(f"camera `{address}` read failed: {grabbed}")
                return cls._failed_retry(address, try_times)
            logging.info(f"camera `{address}` is available")
            return grabbed
        except Exception:
            return cls._failed_retry(address, try_times)
        finally:
            if cls.is_usb_camera(address):
                # 最终杀死占用摄像头进程，防止出现相机没有成功释放的情况
                cls.force_release_usb_camera(address)
            if stream and stream.isOpened():
                stream.release()


class MultiprocessCamera(object):
    WEB_CAM_PROTOCOLS = ("rtsp", "http", "hls", "rtmp")

    VIDEO_PATH_TEST_FPS = 30
    # 读取帧失败的容忍值，超过这个值，则重连
    READ_FRAME_FAILED_TOLERATE = 5

    DEFAULT_SET_PARAMS = {
        cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*"MJPG"),
        # cv2.CAP_PROP_FRAME_WIDTH: 1280,
        # cv2.CAP_PROP_FRAME_HEIGHT: 720,
        cv2.CAP_PROP_FPS: 30,
        cv2.CAP_PROP_AUTO_EXPOSURE: 3,  # 曝光模式设置， 1：手动； 3: 自动
        cv2.CAP_PROP_EXPOSURE: 25,  # 曝光为手动模式时设置的曝光值， 若为自动，则这个值无效
    }

    def __init__(self, address, set_params: Optional[Dict] = None):
        if set_params is None:
            set_params = self.DEFAULT_SET_PARAMS

        address = str(address)
        if address.isdigit() and len(address) < 5:
            address = f"/dev/video{address}"

        self.project_name = os.environ.get("PROJECT_NAME", "")
        self.address = address
        self.set_params = set_params
        self.butcher_knife = BetterRLock()
        # self.store_queue: mp.Queue = mp.Queue(15)
        self.store_queue: FastQueue = FastQueue(
            15, name="camera_store_queue")

        # 切换摄像头信号，其中存放新的摄像机地址
        self._switch_camera_signal = mp.Queue(10)
        # 切换摄像头信号，rsp
        self._switch_camera_rsp = mp.Queue(10)

        # 调节摄像头参数信号
        self._camera_params_adjust_signal = mp.Queue(10)
        # 调节摄像头参数完毕 rsp
        self._camera_params_adjust_rsp = mp.Queue(10)
        # 调节摄像头参数的计时器，超过这个时间就放弃
        self._camera_params_adjust_timer = Timer(timeout=5, enable=False)

        self.connect_flag = mp.Value("d", 0)
        self._connect_confirm_timer_task = Timer(timeout=5, enable=False)
        self.view_worker: Optional[mp.Process] = None
        self.audio_worker: Optional[HIKNetAudioController] = None

        self.stream: Optional[cv2.VideoCapture] = None

        # 在子进程中赋值
        self._video_fps: mp.Value = mp.Value("d", 30)
        self._stream_video_fps: mp.Value = mp.Value("d", 30)
        self._video_width = mp.Value("d", 500)
        self._video_height = mp.Value("d", 800)

        self.health_check_req = mp.Queue(10)
        self.health_check_rsp = mp.Queue(10)

        self.read_failed_count = 0
        self._last_fake_start = 0

        self._frame_fsp_index = 0
        self._drop_frame_index_map = {}

    @property
    def video_width(self):
        return int(self._video_width.value)

    @property
    def video_height(self):
        return int(self._video_height.value)

    @property
    def video_fps(self):
        return int(self._video_fps.value)

    @property
    def stream_video_fps(self):
        return int(self._stream_video_fps.value)

    @video_width.setter
    def video_width(self, video_width: int):
        self._video_width.value = video_width

    @video_height.setter
    def video_height(self, video_height: int):
        self._video_height.value = video_height

    @video_fps.setter
    def video_fps(self, video_fps: int):
        self._video_fps.value = video_fps

    @stream_video_fps.setter
    def stream_video_fps(self, video_fps: int):
        self._stream_video_fps.value = video_fps

    @classmethod
    def _is_file_address(cls, address):
        if isinstance(address, str) and "/" in address \
                and "rtsp" not in address and "http" not in address:
            return True
        return False

    @classmethod
    def _get_frame_size(cls, _frame: np.ndarray) -> Tuple[int, int]:
        """
        :param _frame:
        :return: (video_width, video_height)
        """
        return int(_frame.shape[1]), int(_frame.shape[0])

    @property
    def center_box(self):
        cx = int(self.video_width * 0.25)
        cy = int(self.video_height * 0.20)
        cw = int(self.video_width * 0.65) - cx
        ch = int(self.video_height * 0.95) - cy
        return cx, cy, cw, ch

    def _fake_read_time(self):
        fake_read_time = 1 / self.video_fps
        if self._last_fake_start > 0:
            real_fake_read = time.time() - self._last_fake_start
            adjust_diff = real_fake_read - fake_read_time
            if 0.002 < adjust_diff < fake_read_time:
                fake_read_time -= adjust_diff
                fake_read_time -= 0.002

        self._last_fake_start = time.time()
        if fake_read_time > 0:
            time.sleep(fake_read_time)

    def read_frame(self, stream, address=None):
        if CameraAddressUtil.is_file_address(address):
            # 读文件时，将 fps 控制在 cls.VIDEO_PATH_TEST_FPS
            self._fake_read_time()
        # if address:
        #     logger.debug(f"read frame from {address}")
        with self.butcher_knife:
            return stream.read()

    def is_ip_camera(self):
        return not str(self.address).isdigit()

    def get_setting_camera_param(self) -> CameraParams:
        """
            获取设置的相机配置 【用户设置配置】
        :return: 
        """
        video_fps = self.set_params.get(cv2.CAP_PROP_FPS)
        video_width = self.set_params.get(cv2.CAP_PROP_FRAME_WIDTH)
        video_height = self.set_params.get(cv2.CAP_PROP_FRAME_HEIGHT)
        return CameraParams(
            video_fps=int(video_fps) if video_fps is not None else None,
            video_width=int(video_width) if video_width is not None else None,
            video_height=int(video_height) if video_height is not None else None
        )

    def get_camera_params(self) -> CameraParams:
        """
            获取相机配置 【真正的给使用方的配置】
        :return: 
        """
        # 确保已连接
        while self.connect_flag.value == 0:
            time.sleep(1)
        return CameraParams(
            video_fps=self.video_fps,
            video_width=self.video_width,
            video_height=self.video_height,
        )

    def _adjust_to_setting_fps(self, stream_fps):
        setting_camera_param = self.get_setting_camera_param()
        if setting_camera_param.video_fps is None:
            return stream_fps
        adjust_fps, self._drop_frame_index_map = self._calculate_adjust_fps(
            stream_fps, setting_camera_param.video_fps)

        return adjust_fps

    def health_check(self):
        self.health_check_req.put(1)
        try:
            info: HealthRspInfo = self.health_check_rsp.get(timeout=10)
            info.worker_status = "OK"
            return info
        except Empty:
            info = HealthRspInfo(worker_name="camera")
            info.worker_status = "No response"
            return info

    @classmethod
    def _calculate_adjust_fps(cls, origin_fps, adjust_fps):
        diff = origin_fps - adjust_fps
        if diff <= 0:
            return origin_fps, {}
        if adjust_fps == 1:
            return adjust_fps, {i + 1: 1 for i in range(1, origin_fps)}

        frame_drop_map = {}
        avg = origin_fps / diff
        drop_index = 1
        for i in range(1, origin_fps + 1):
            drop_suggest = avg * drop_index
            if i >= drop_suggest:
                # print(f"drop_suggest: {drop_suggest}, drop: {i}")
                frame_drop_map[i] = 1
                drop_index += 1

        return adjust_fps, frame_drop_map

    def _init_camera_params(self, stream: cv2.VideoCapture):
        if stream is None:
            return
        if not CameraAddressUtil.is_file_address(self.address):
            for key, value in self.set_params.items():
                stream.set(key, value)

        self.stream_video_fps = int(stream.get(cv2.CAP_PROP_FPS))
        self.video_fps = self._adjust_to_setting_fps(self.stream_video_fps)
        setting_param = self.get_setting_camera_param()
        stream_width = int(stream.get(cv2.CAP_PROP_FRAME_WIDTH))
        stream_height = int(stream.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if (setting_param.video_width is None
                and setting_param.video_height is None):
            self.video_width = stream_width
            self.video_height = stream_height
        elif ((setting_param.video_width, setting_param.video_width)
              != (stream_width, stream_height)):
            self.video_width = setting_param.video_width
            self.video_height = setting_param.video_height
        else:
            self.video_width = stream_width
            self.video_height = stream_height

    @time_cost_log
    def _init_stream(self) -> cv2.VideoCapture:
        # logging.info(f"[camera-inside] getting butcher_knife")
        with self.butcher_knife:
            # logging.info(f"[camera-inside] got butcher_knife")
            logging.info(f"init stream for {self.address}")
            if CameraAddressUtil.is_usb_camera(self.address):
                CameraAddressUtil.force_release_usb_camera(self.address)

            if CameraAddressUtil.is_web_cam_address(self.address):
                stream = RTSPCapture(self.address)
            else:
                stream = cv2.VideoCapture(self.address)

            self._init_camera_params(stream)

            if stream.isOpened():
                # 连接上了，但是不一定读取到视频帧了，还不能设置为已连接，
                # 当真正读取到视频帧后，才能设置为已连接
                self._connect_confirm_timer_task.reset_timer()
                logging.info("[camera] set _connect_confirm_timer_task")
                logging.info("[camera] stream connected, but not real "
                             "connected")
                logging.info(f""" [camera] stream camera params
                video_height: {int(stream.get(cv2.CAP_PROP_FRAME_HEIGHT))}
                video_width: {int(stream.get(cv2.CAP_PROP_FRAME_WIDTH))}
                video_fps: {stream.get(cv2.CAP_PROP_FPS)}
                """)
                MultiprocessCamera.VIDEO_PATH_TEST_FPS = self.video_fps
            self._reset()
            return stream

    def is_connected(self):
        return self.connect_flag.value > 0

    def switch_camera(self, new_address):
        old_connect_flag = self.connect_flag.value
        self._switch_camera_signal.put(new_address)
        for _ in range(30):
            if self.connect_flag.value > old_connect_flag:
                return True
            logging.info(f"[camera] waiting camera switch to {new_address}")
            time.sleep(0.1)
        return False

    def adjust_camera_params(self, new_params: dict):
        clear_queue(self._camera_params_adjust_rsp,
                    queue_msg="self._camera_params_adjust_rsp")
        self._camera_params_adjust_signal.put(new_params)
        try:
            self._camera_params_adjust_rsp.get(timeout=10)
            return True
        except Empty:
            logging.error(f"[camera] no adjust success sig found \n "
                          f"{traceback.format_exc()}")
            return False
        finally:
            camera_param = self.get_camera_params()
            logging.info(f"[camera] now camera_param: "
                         f"{json.dumps(camera_param.__dict__, indent=4)}")

    def adjust_camera_fps(self, fps):
        if fps > self.stream_video_fps:
            fps = self.stream_video_fps
        if self.video_fps == fps:
            return
        self.adjust_camera_params({cv2.CAP_PROP_FPS: fps})

    def _ensure_stream_opened(self) -> cv2.VideoCapture:
        while self.stream is None or not self.stream.isOpened():
            logging.warning(f"[camera] stream closed !!!!, reconnecting....."
                            f": {self.address}")
            time.sleep(0.3)
            self.stream = self._init_stream()
            self._check_switch_camera_signal()
        return self.stream

    def _reset(self):
        self.read_failed_count = 0

    def _check_switch_camera_signal(self):
        if self._switch_camera_signal.qsize() > 0:
            try:
                self.address = self._switch_camera_signal.get(timeout=1)
                self.stream.release()
                if CameraAddressUtil.is_usb_camera(self.address):
                    CameraAddressUtil.force_release_usb_camera(self.address)
                self.stream = None
                self.clear_buffer()
            except Empty:
                logging.error(
                    f"[camera] obtain switch_camera_signal failed !!!!")

    def _check_camera_params_adjust_signal(self):
        if self._camera_params_adjust_signal.qsize() > 0:
            try:
                new_params = self._camera_params_adjust_signal.get(timeout=1)
                now_params = self.get_camera_params().opencv_params()
                if new_params != now_params:
                    logging.info(f"[camera] camera_params_adjust_signal:"
                                 f" {new_params}, new_params != now_params:"
                                 f" {new_params != now_params}")
                    self._camera_params_adjust_timer.reset_timer()
                    self.set_params.update(new_params)
                    self._init_camera_params(self.stream)
                    self.clear_buffer()
            except Empty:
                logging.error(f"[camera] camera_params_adjust_signal"
                              f" is missing !!!!")

    def _check_camera_params_adjust_result(self, resized_frame: np.ndarray):
        if self._camera_params_adjust_timer.is_timeout():
            return
        params = self.get_camera_params()
        video_width, video_height = self._get_frame_size(resized_frame)
        params.video_width, params.video_height = video_width, video_height
        # 通过最终 frame 的 params 判断是否
        setting_params = CameraParams.from_opencv_params(self.set_params)
        if params.size_equal(setting_params):
            logging.info("[camera] new params is detected, send adjust"
                         f" success sig, self.set_params: {self.set_params}, \n"
                         f"self.video_fps: {self.video_fps}\n"
                         f"self.video_width: {self.video_width}\n"
                         f"self.video_height: {self.video_height}")
            self._camera_params_adjust_rsp.put(1)
            self._camera_params_adjust_timer.disable()

    def _health_check(self):
        if self.health_check_req.qsize() > 0:
            try:
                self.health_check_req.get(timeout=0.1)
                self.health_check_rsp.put(HealthRspInfo())
            except Empty:
                pass
            finally:
                clear_queue(self.health_check_req, time_out=0.01)

    def _frame_resize_filter(self, _frame: np.ndarray):
        """

        :param _frame:
        :return:
        """
        setting_param = self.get_setting_camera_param()
        # 如果没有指定尺寸，则不 resize
        if (setting_param.video_width is None
                and setting_param.video_height is None):
            return _frame
        frame_width, frame_height = self._get_frame_size(_frame)

        setting_size = (setting_param.video_width, setting_param.video_height)
        if (frame_width, frame_height) != setting_size:
            _frame = cv2.resize(_frame, setting_size)

        frame_width, frame_height = self._get_frame_size(_frame)
        if (self.video_width, self.video_height) != (frame_width, frame_height):
            self.video_width = frame_width
            self.video_height = frame_height
            logging.info(f"""[camera] update camera_params:
                self.video_width = {frame_width}
                self.video_height = {frame_height}
            """)

        return _frame

    def _confirm_connected(self):
        if self._connect_confirm_timer_task.is_timeout():
            return
        self.connect_flag.value += 1
        self._connect_confirm_timer_task.disable()
        logging.info(f"""[camera] camera real connected with frames !!!
            real camera params:
             {json.dumps(self.get_camera_params().__dict__, indent=4)}
            address: {self.address}
        """)

    @new_process()
    def show(self, frame_num=0):
        if frame_num == 0:
            frame_num = 99999999999
        for _ in range(frame_num):
            try:
                frame_box: FrameBox = self.store_queue.get(timeout=10)
            except Empty:
                break
            cv2.imshow(self.address, frame_box.frame)
            cv2.waitKey(1)

    def _plus_frame_fps_index(self):
        self._frame_fsp_index += 1
        if self._frame_fsp_index > self.stream_video_fps:
            self._frame_fsp_index = 1

    def reading_frames(self):
        try:
            logging.info(f"[camera-inside] starting view worker: {self.address}"
                         f" pid: {os.getpid()}")
            self.stream: cv2.VideoCapture = self._init_stream()
            setproctitle.setproctitle(f"{self.project_name}-Camera")

            last_frame = None
            while True:
                with self.butcher_knife:
                    pass
                self._health_check()
                self._check_camera_params_adjust_signal()
                self._check_switch_camera_signal()
                self._ensure_stream_opened()
                grabbed, _frame = self.read_frame(self.stream, self.address)
                if grabbed:
                    self._plus_frame_fps_index()
                    if self._drop_frame_index_map.get(self._frame_fsp_index):
                        # print(f"drop: {self._frame_fsp_index}")
                        continue
                    frame_box = FrameBox(_frame, fps=self.video_fps)

                    # 无条件转为 设置的 分辨率
                    resized_frame = self._frame_resize_filter(frame_box.frame)
                    # 成功读取到视频帧，才视作已连接
                    self._confirm_connected()
                    self._check_camera_params_adjust_result(resized_frame)

                    frame_box.frame = resized_frame
                    last_frame = frame_box
                    if self.store_queue.full():
                        # 保持读取摄像头最新的数据
                        self.store_queue.abandon_one()
                    with self.butcher_knife:
                        self.store_queue.put(frame_box)
                elif (CameraAddressUtil.is_file_address(self.address)
                      and last_frame is not None):
                    if self.store_queue.full():
                        self.store_queue.abandon_one()
                    last_frame.frame_id = unique_time_id()
                    last_frame.frame_ctime = time.perf_counter()
                    with self.butcher_knife:
                        self.store_queue.put(last_frame)
                elif self.read_failed_count > self.READ_FRAME_FAILED_TOLERATE:
                    logging.warning(
                        f"[camera]: read frame failed, "
                        f"self.self.read_failed_count: {self.read_failed_count}"
                        f"stream status: {self.stream.isOpened()},"
                        f"address: {self.address}"
                    )
                    self.release()
                    self.stream = None
                    time.sleep(0.5)
                    self.stream = self._init_stream()
                else:
                    self.read_failed_count += 1
        except KeyboardInterrupt:
            self.release()
        finally:
            print(f"""
            -------------------------------------------------------------
            
                    Camera worker exit: {self.address}
            
            -------------------------------------------------------------
            """)
            self.release()

    def clear_buffer(self):
        buffer_size = self.store_queue.qsize()
        if not buffer_size:
            return
        logging.debug(f"Detect camera buffer, buffer size: {buffer_size},"
                      f" clearing ....")
        clear_count = 0
        for _ in range(buffer_size):
            try:
                self.store_queue.get(timeout=0.01)
                clear_count += 1
                logging.debug(f"Cleared-{clear_count} camera buffer, "
                              f"buffer remain {self.store_queue.qsize()}")
            except Empty:
                continue

        logging.debug(f"Camera buffer clear complete")

    def _init_audio_worker(self, hc=None):
        if not CameraAddressUtil.is_hik_web_cam_address(address=self.address):
            return
        if not self.wait_connected(timeout=10):
            return

        if hc is None:
            hc = HIKNetAudioController()
            hc.start_work_in_subprocess()

        parse_ret = urlparse(self.address)
        hc.send_start_work_req(host=parse_ret.hostname,
                               username=parse_ret.username,
                               password=parse_ret.password)

        def _wait_connected():
            for _ in range(50):
                if hc.is_working():
                    logging.info("""
                    ===================================================
                                Audio worker is working !!!!!
                    ==================================================
                    """)
                    break

                if hc.is_error_exit():
                    print(hc.worker_working_state)
                    hc.send_start_work_req(host=parse_ret.hostname,
                                           username=parse_ret.username,
                                           password=parse_ret.password)

                time.sleep(0.5)

        _wait_connected()

        return hc

    def wait_connected(self, timeout=10) -> bool:
        for _ in range(timeout * 10):
            if self.is_connected():
                logging.info(f"[camera] wait_connected, confirmed connection")
                return True
            time.sleep(0.1)
        logging.info("[camera] wait_connected, camera is still not connected")
        return False

    def play_audio(self, audio_file):
        if self.audio_worker is not None:
            self.audio_worker.play_audio(audio_file)

    def start_view_worker(self):
        self.connect_flag.value = 0
        self.view_worker = mp.Process(target=self.reading_frames)
        self.view_worker.daemon = False
        self.view_worker.start()

    def start(self):
        if self.view_worker is None:
            self.start_view_worker()

        if self.audio_worker is None:
            self.audio_worker = self._init_audio_worker()

    def restart(self, timeout=60):
        start = time.time()
        logging.info(f"[camera] killing view_worker: "
                     f"{self.view_worker.pid}")
        # force to release it
        # camera butcher_knife not release by other process, probably was view
        # worker, blocking at read frame or something else using pyav,
        # which is all handled within self.butcher_knife, so force release it
        try:
            if not self.butcher_knife.acquire(timeout=timeout):
                self.butcher_knife.release()
                logging.warning("[camera] camera butcher_knife not release by "
                                "other process, so force release it")
        finally:
            self.butcher_knife.release()

        with self.butcher_knife:
            logging.info(f"[camera] killing view_worker: "
                         f"{self.view_worker.pid} [butcher_knife gained]")
            clear_queue_cache(self.store_queue, "camera_store_queue")
            remain_timeout = int(max(timeout - (time.time() - start), 3))
            ProcessController.kill_process(self.view_worker.pid,
                                           timeout=remain_timeout)
            # 关闭进程的 pipe 文件
            self.view_worker._popen.close()
            logging.info(f"[camera] killed view_worker: {self.view_worker.pid}")

        self.start_view_worker()

        if self.audio_worker is not None:
            self.audio_worker.restart_worker()
            self._init_audio_worker(self.audio_worker)

        self.wait_connected(timeout)

    def release(self):
        # noinspection PyBroadException
        try:
            if self.stream:
                self.stream.release()
            if CameraAddressUtil.is_usb_camera(self.address):
                CameraAddressUtil.force_release_usb_camera(self.address)
        except Exception:
            pass

    def close(self):
        if self.view_worker:
            if self.view_worker.is_alive():
                self.view_worker.terminate()
                os.waitpid(self.view_worker.pid, 0)
        self.release()

    def __del__(self):
        # noinspection PyBroadException
        try:
            self.close()
        except Exception as exp:
            pass


class MultiprocessVideoCapture(object):

    def __init__(self):
        self.cam_map: Dict[str, MultiprocessCamera] = dict()
        self.view_processes: List[mp.Process] = []

    def register_camera(self, cam_address, set_params: Optional[Dict] = None):

        logging.info(f"""[camera] register camera: {cam_address}
            set_params:　{json.dumps(set_params, indent=4)}
        """)
        camera = MultiprocessCamera(address=cam_address, set_params=set_params)

        self.cam_map.setdefault(cam_address, camera)
        self.cam_map[cam_address].start()

    def switch_camera(self, old_cam_address, new_cam_address):
        self._raise_if_not_registered(old_cam_address)
        # 已注册过 new_cam_address，不处理更换地址请求
        if (old_cam_address != new_cam_address
                and new_cam_address in self.cam_map):
            raise _CameraRegisteredError(new_cam_address)

        logging.debug(f"[camera] switching camera, old {old_cam_address},"
                      f"new_cam_address: {new_cam_address}")
        camera = self.cam_map[old_cam_address]
        if not camera.switch_camera(new_cam_address):
            # 切换失败切换回去
            logging.info("[camera] switch failed, switch back")
            camera.switch_camera(old_cam_address)
            return False
        self.cam_map[new_cam_address] = self.cam_map.pop(old_cam_address)
        return True

    def adjust_params(self, cam_address, new_params: dict):
        self._raise_if_not_registered(cam_address)
        camera = self.cam_map[cam_address]
        now_params = camera.get_camera_params()
        if now_params != new_params:
            if camera.adjust_camera_params(new_params):
                camera.set_params = new_params
                logging.info(f"[camera] adjusting params success: "
                             f"{json.dumps(new_params, indent=4)}")
            else:
                params = camera.get_camera_params()
                logging.info(f"[camera] adjust params failed, now params "
                             f"{json.dumps(params.__dict__, indent=4)}")
        else:
            now_camera_params = camera.get_camera_params().__dict__
            logging.info(f"""[camera] camera_params no change, pass:
                new_params:　{json.dumps(new_params, indent=4)}
                
                camera.now_camera_params: 
                {json.dumps(now_camera_params, indent=4)}
                
            """)

    def _raise_if_not_registered(self, cam_address):
        if cam_address not in self.cam_map:
            raise AttributeError(f"[camera] Please register camera "
                                 f"first: {cam_address}")

    def clear_camera_buffer(self, cam_address):
        self._raise_if_not_registered(cam_address)
        camera = self.cam_map[cam_address]
        camera.clear_buffer()

    def read_camera_frame(self, cam_address) -> FrameBox:
        self._raise_if_not_registered(cam_address)
        camera = self.cam_map[cam_address]
        return camera.store_queue.get()

    def show_camera(self, cam_address, frame_num=0, window_name=None):
        self.clear_camera_buffer(cam_address)
        frame_num = frame_num if frame_num else 10000000
        window_name = str(cam_address) if window_name is None else window_name
        for _ in range(frame_num):
            frame_box = self.read_camera_frame(cam_address)
            frame_box.put_delay_text(tag="result")
            self._show_frame(frame_box.frame, window_name=window_name)

    def get_camera(self, cam_address) -> MultiprocessCamera:
        self._raise_if_not_registered(cam_address)
        return self.cam_map[cam_address]

    def get_camera_params(self, cam_address):
        camera = self.get_camera(cam_address)
        return camera.get_camera_params()

    def close_camera(self, cam_address):
        self._raise_if_not_registered(cam_address)
        camera = self.cam_map[cam_address]
        camera.close()

    def close_all_cameras(self):
        for camera in self.cam_map.values():
            camera.close()

    def autoload_usb_cameras(self):
        usb_cameras = get_videocap_devices()
        for usb_camera in usb_cameras:
            self.register_camera(usb_camera)

        logging.info(f"""
        -----------------------------------------------------------------------
        【Autoload usb cameras】 NUM: {len(usb_cameras)}
            {json.dumps(usb_cameras, indent=4, ensure_ascii=False)}
        -----------------------------------------------------------------------
        """)
        for m in range(10):
            for s in range(60):
                logging.info(f"run time: {m}:{s}")
                time.sleep(1)

    @classmethod
    def _show_frame(cls, frame, window_name=None):
        if window_name is None:
            window_name = "frame"
        # frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)  #顺时针旋转图片
        cv2.imshow(window_name, frame)
        cv2.waitKey(1)

    @classmethod
    def show_queue_frames(cls, cam_address, store_queue: mp.Queue, frame_num,
                          window_name=None):
        logging.debug(f"{cam_address}, {mp.current_process().pid}")
        for _ in range(frame_num):
            frame: FrameBox = store_queue.get()
            cls._show_frame(frame.frame, window_name)

    def show_camera_async(self, cam_address, frame_num=0, window_name=None):
        self.clear_camera_buffer(cam_address)
        frame_num = frame_num if frame_num else 10000000
        self._raise_if_not_registered(cam_address)
        window_name = str(cam_address) if window_name is None else window_name
        camera = self.cam_map[cam_address]
        worker = mp.Process(target=self.show_queue_frames,
                            args=(cam_address, camera.store_queue, frame_num,
                                  window_name))
        worker.daemon = False
        worker.start()
        self.view_processes.append(worker)

    def stop_all_view_processes(self):
        for pro in self.view_processes:
            pro.terminate()
            os.waitpid(pro.pid, 0)

    def save_video(self, cam_address, frame_num=0, save_path="./test.mp4"):
        frame_num = frame_num if frame_num else 10000000
        camera_params = self.get_camera_params(cam_address)
        frames = []
        for _ in range(frame_num):
            frame_box = self.read_camera_frame(cam_address)
            self._show_frame(frame_box.frame)
            frames.append(frame_box.frame)

        @time_cost_log
        def _video_write():
            video_writer = H264Writer(save_path, fps=camera_params.video_fps,
                                      bit_rate=1000000)
            # video_writer = cv2.VideoWriter(
            #     save_path,
            #     cv2.VideoWriter_fourcc(*"mp4v"),
            #     camera_params.video_fps,
            #     (camera_params.video_width,
            #      camera_params.video_height),
            #     True,
            # )
            for _frame in frames:
                video_writer.write(_frame)
            # video_writer.release()
            # to_h264_video(save_path, f"{os.path.dirname(__file__)}/test-h264.mp4")

        _video_write()
        return os.path.abspath(save_path)

    def save_frames(self, cam_address, frame_num=0, save_dirpath="./test/"):
        frame_num = frame_num if frame_num else 10000000
        camera_params = self.get_camera_params(cam_address)
        frames = []
        for _ in range(frame_num):
            frame_box = self.read_camera_frame(cam_address)
            self._show_frame(frame_box.frame)
            frames.append(frame_box.frame)

        for frame in tqdm(frames, desc="saving frames"):
            image_filepath = os.path.join(
                save_dirpath, f"IMG-{time.perf_counter_ns()}.jpg")
            print(f"IMG-{time.perf_counter_ns()}.jpg")
            cv2.imwrite(image_filepath, frame)

        return os.path.abspath(save_dirpath)

    def __del__(self):
        # noinspection PyBroadException
        try:
            self.stop_all_view_processes()
        except Exception:
            pass


if __name__ == "__main__":
    from watchdog.utils.util_log import set_scripts_logging

    set_scripts_logging(__file__)
    print(f"main pid: {os.getpid()}")
    mvc = MultiprocessVideoCapture()
    # 2592 * 1944
    # 1920 * 1080
    # 1600 * 1200
    # 1280 * 720
    # 1024 * 768
    # 800 * 600
    # 640 * 480
    SET_PARAMS = {
        cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*"MJPG"),
        cv2.CAP_PROP_FRAME_WIDTH: 1280,
        cv2.CAP_PROP_FRAME_HEIGHT: 720,
        cv2.CAP_PROP_FPS: 60,
        cv2.CAP_PROP_AUTO_EXPOSURE: 3,  # 曝光模式设置， 1：手动； 3: 自动
        cv2.CAP_PROP_EXPOSURE: 25,  # 曝光为手动模式时设置的曝光值， 若为自动，则这个值无效
    }

    # SET_PARAMS2 = {
    #     cv2.CAP_PROP_FPS: 5,
    #     cv2.CAP_PROP_AUTO_EXPOSURE: 3,  # 曝光模式设置， 1：手动； 3: 自动
    #     cv2.CAP_PROP_EXPOSURE: 25,  # 曝光为手动模式时设置的曝光值， 若为自动，则这个值无效
    # }

    ADDRESS4 = "0"
    # ADDRESS4 = 0

    mvc.register_camera(ADDRESS4, SET_PARAMS)
    # mvc.get_camera(ADDRESS4).play_audio("/home/walkerjun/下载/chuanqi.m4a")

    mvc.show_camera_async(ADDRESS4)
    while True:
        time.sleep(5)
        mvc.get_camera(ADDRESS4).restart()
    #
    # mvc.save_video(ADDRESS4, frame_num=250, save_path="./test_continue.mp4")
    # mvc.adjust_params(ADDRESS4, SET_PARAMS2)
    # mvc.save_video(ADDRESS4, frame_num=50, save_path="./test_continue.mp4")
    # mvc.adjust_params(ADDRESS4, SET_PARAMS)
    # mvc.save_video(ADDRESS4, frame_num=250, save_path="./test_continue.mp4")
    # mvc.show_camera_async(ADDRESS4)
