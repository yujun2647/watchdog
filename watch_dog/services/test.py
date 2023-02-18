import time
import json
import atexit
from threading import Thread
from watch_dog.utils.util_process import ProcessController

atexit.register(ProcessController.kill_sub_processes)

from watch_dog.services.workers.marker import Marker
from watch_dog.services.workers.video_recorder import VidRecorderH264, VidRecorder
from watch_dog.services.wd_queue_console import WdQueueConsole
from watch_dog.services.workers.monitor import Monitor
from watch_dog.services.workers.frame_distributor import FrameDistributor
from watch_dog.services.workers.detect.common_detector import CommonDetector

if __name__ == "__main__":
    from cv2 import cv2
    from watch_dog.utils.util_camera import FrameBox
    from watch_dog.utils.util_log import set_scripts_logging

    set_scripts_logging(__file__)

    camera_address = 0
    camera_address = "rtsp://admin:huang7758258@192.168.3.230:554/h265/ch1/main/av_stream"
    q_console = WdQueueConsole.init_default(camera_address=camera_address,
                                            fps=1, detect_worker_num=1)

    frame_dst = FrameDistributor(q_console=q_console)

    marker = Marker(q_console=q_console)
    c_detector = CommonDetector(q_console=q_console)
    monitor = Monitor(q_console=q_console)
    vid_recorder = VidRecorderH264(q_console=q_console,
                                   work_req_queue=q_console.recorder_req_queue)

    marker.send_start_work_req()
    c_detector.send_start_work_req()
    monitor.send_start_work_req()
    frame_dst.send_start_work_req()

    marker.start_work_in_subprocess()
    monitor.start_work_in_subprocess()
    c_detector.start_work_in_subprocess()
    frame_dst.start_work_in_subprocess()
    vid_recorder.start_work_in_subprocess()

    while True:
        frame_box: FrameBox = q_console.render_frame_queue.get()
        frame_box.put_delay_text(tag="final")

        cv2.imshow(f"frame", frame_box.frame)
        cv2.waitKey(1)
