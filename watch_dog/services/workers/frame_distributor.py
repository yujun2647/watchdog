from watch_dog.utils.util_camera import FrameBox
from watch_dog.models.worker_req import WorkerEndReq, WorkerStartReq
from watch_dog.services.base.wd_base_worker import WDBaseWorker


class FrameDistributor(WDBaseWorker):
    MAX_CAM_FETCH_FAILED = 3

    def __sub_init__(self, **kwargs):
        self.camera_frame_queue = self.q_console.camera.store_queue

        # 相机图像帧获取失败次数, 连续失败 {MAX_CAM_FETCH_FAILED} 次, 则重启相机
        self.cam_fetch_failed_count = 0

    def _sub_work_before_cleaned_up(self, work_req):
        pass

    def _sub_init_work(self, work_req):
        pass

    def _handle_start_req(self, work_req: WorkerStartReq) -> bool:
        frame_box: FrameBox = self.get_queue_item(self.camera_frame_queue,
                                                  timeout=5, wait_item=True)
        if frame_box is not None:
            self.cam_fetch_failed_count = 0
            frame_box.put_delay_text(tag="import")
            self.put_queue_item(self.q_console.frame4mark_queue, frame_box,
                                force_put=True)
            self.put_queue_item(self.q_console.frame4common_detect_queue,
                                frame_box, force_put=True)

            self.plus_working_handled_num()
        else:
            self.cam_fetch_failed_count += 1

        if self.cam_fetch_failed_count >= self.MAX_CAM_FETCH_FAILED:
            # 重启相机
            self.q_console.restart_camera(proxy=True)

        return False

    def _handle_end_req(self, work_req: WorkerEndReq) -> bool:
        return False

    def _sub_work_done_cleaned_up(self, work_req):
        pass

    def _sub_side_work(self):
        pass

    def _sub_clear_all_output_queues(self):
        pass

    def _handle_worker_exception(self, exp):
        pass


if __name__ == "__main__":
    from watch_dog.utils.util_log import set_scripts_logging

    set_scripts_logging(__file__)
    import time
    import json

    t = FrameDistributor()
    t.start_work_in_subprocess()
    t.send_start_work_req()
    for _ in range(100):
        health_info = t.health_check()
        print(json.dumps(health_info.__dict__, indent=4))
        # health_info = t.q_console.camera.health_check()
        # print(json.dumps(health_info.__dict__, indent=4))
        time.sleep(1)
