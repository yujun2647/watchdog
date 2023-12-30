import json
import time
import multiprocessing as mp

from watchdog.configs.constants import CameraConfig
from watchdog.utils.util_time import get_bj_time_str
from watchdog.services.path_service import get_cache_filepath


class WorkerReq(object):

    def __init__(self, *args, **kwargs):
        self.is_new = False
        self.req_sig = None
        self.req_type = None
        self.req_msg = None

    def desc_dict_text(self):
        return json.dumps(self.__dict__, indent=4, ensure_ascii=False)


class WorkerStartReq(WorkerReq):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.req_sig = "start"
        self.req_msg = kwargs.get("req_msg", None)


class WorkerEndReq(WorkerReq):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.req_sig = "end"
        self.req_msg = kwargs.get("req_msg", None)


class VidRecStartReq(WorkerStartReq):

    def __init__(self, tag=""):
        super().__init__()
        self.raw_tag = tag
        self.req_tag = f"{get_bj_time_str()}-{tag}"
        self.rec_filename = f"{self.req_tag}.mp4"
        self.write_filepath = get_cache_filepath(self.rec_filename)
        self.rec_secs = CameraConfig.REC_SECS.value
        self.active_fps = CameraConfig.ACTIVE_FPS.value
        self.rest_fps = CameraConfig.REST_FPS.value
        self.c_time = time.perf_counter()
        self.m_time = time.perf_counter()
