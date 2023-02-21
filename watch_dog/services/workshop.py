from watch_dog.configs.constants import CameraConfig

from watch_dog.services.workers.marker import Marker
from watch_dog.services.workers.video_recorder import VidRecH264
from watch_dog.services.wd_queue_console import WdQueueConsole
from watch_dog.services.workers.monitor import Monitor
from watch_dog.services.workers.frame_distributor import FrameDistributor
from watch_dog.services.workers.detect.common_detector import CommonDetector


class WorkShop(object):

    def __init__(self, camera_address, video_width=None,
                 video_height=None):
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

        self.marker.send_start_work_req()
        self.c_detector.send_start_work_req()
        self.monitor.send_start_work_req()
        self.frame_dst.send_start_work_req()

        self.marker.start_work_in_subprocess()
        self.monitor.start_work_in_subprocess()
        self.c_detector.start_work_in_subprocess()
        self.frame_dst.start_work_in_subprocess()
        self.vid_recorder.start_work_in_subprocess()
