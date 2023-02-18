import json
import time

from watch_dog.services.path_service import get_cache_filepath
from watch_dog.utils.util_time import get_bj_time_str


class WorkerReq(object):

    def __init__(self, *args, **kwargs):
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

    def __init__(self, tag="", rec_secs=10 * 3, rec_fps=15, lazy_fps=1):
        super().__init__()
        self.tag = f"{get_bj_time_str()}-{tag}"
        self.rec_filename = f"{self.tag}.mp4"
        self.rec_secs = rec_secs
        self.rec_fps = rec_fps
        self.lazy_fps = lazy_fps
        self.c_time = time.perf_counter()
        self.m_time = time.perf_counter()
        self.write_filepath = get_cache_filepath(self.rec_filename)

