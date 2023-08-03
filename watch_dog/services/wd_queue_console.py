from typing import *
import multiprocessing as mp
from multiprocessing.synchronize import Event as MEvent

import cv2

from watch_dog.configs.constants import CarMonitorState, PersonMonitorState

from watch_dog.utils.util_multiprocess.queue import FastQueue
from watch_dog.utils.util_camera import MultiprocessCamera, FrameBox
from watch_dog.utils.util_multiprocess.queue_console import QueueConsole
from watch_dog.models.worker_req import WorkerEndReq, VidRecStartReq

if TYPE_CHECKING:
    from watch_dog.utils.util_multiprocess.multi_object import MultiShareObject


class QueueBox(object):
    pass


class ShareStates(object):
    pass


class MonitorStates(ShareStates):

    def __init__(self):
        self.car_state = mp.Value("i", CarMonitorState.NEGATIVE)
        self.person_state = mp.Value("i", PersonMonitorState.NEGATIVE)

    def is_now_active(self):
        return (self.car_state.value == CarMonitorState.POSITIVE
                or self.person_state.value == PersonMonitorState.POSITIVE)


class WdQueueConsole(QueueConsole):

    def __init__(self, camera: "MultiprocessCamera",
                 global_worker_task: Optional["MultiShareObject"] = None,
                 console_id: str = "", detect_worker_num=1):
        if global_worker_task is None:
            global_worker_task = mp.Manager().TaskInfo(task_name="")
        super().__init__(global_worker_task=global_worker_task,
                         console_id=console_id)

        self.detect_worker_num = mp.Value("i", int(detect_worker_num))

        # 相机对象
        self.camera = camera

        # 相机重启信号
        self.camera_restart_sig: MEvent = mp.Event()

        self.live_frame: Optional[FrameBox] = None

        # 用于存放已标注/渲染后的帧
        self.render_frame_queue = FastQueue(10, name="render_frame_queue")

        # 存放检测数据，用于 landmark
        self.detect_infos_queue = FastQueue(360, name="detect_infos_queue")

        # 同样存放检测数据，用于监控器分析
        self.detect_infos_sense_queue = FastQueue(
            360, name="detect_infos_sense_queue")

        # 用于标注的帧
        self.frame4mark_queue = FastQueue(360, name="frame4mark_queue")

        # 用于常规检测的帧传输
        self.frame4common_detect_queue = FastQueue(
            360, name="frame4common_detect_queue")

        # 用于视频录制
        self.frame4record_queue = FastQueue(8 * 3, name="record_frame_queue")

        self.recorder_req_queue = FastQueue(name="record_frame_queue")

        self.monitor_states = MonitorStates()

    def restart_camera(self, proxy=True):
        if not proxy:
            self.camera.restart()
            return
        self.camera_restart_sig.set()

    def start_vid_record(self, tag):
        print("start recording")
        self.recorder_req_queue.put(VidRecStartReq(tag=tag))

    def stop_vid_record(self):
        print("end record")
        self.recorder_req_queue.put(WorkerEndReq())

    @classmethod
    def init_default(cls, console_id="console_id", camera_address=None,
                     fps=None, video_width=None,
                     video_height=None,
                     detect_worker_num=1) -> "WdQueueConsole":
        if camera_address is None:
            camera_address = 0

        set_params = {
            cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*"MJPG"),
            cv2.CAP_PROP_AUTO_EXPOSURE: 3,  # 曝光模式设置， 1：手动； 3: 自动
            cv2.CAP_PROP_EXPOSURE: 25,  # 曝光为手动模式时设置的曝光值， 若为自动，则这个值无效
        }
        if fps is not None:
            set_params[cv2.CAP_PROP_FPS] = fps
        if video_width is not None:
            set_params[cv2.CAP_PROP_FRAME_WIDTH] = video_width
        if video_height is not None:
            set_params[cv2.CAP_PROP_FRAME_HEIGHT] = video_height

        test_camera = MultiprocessCamera(camera_address, set_params=set_params)
        test_camera.start()
        print(f"inited default q_console")
        return WdQueueConsole(camera=test_camera,
                              detect_worker_num=detect_worker_num)


if __name__ == "__main__":
    _global_worker_task = mp.Manager().TaskInfo(task_name="")
    q_console = WdQueueConsole(None, global_worker_task=_global_worker_task)
    print("debug")
