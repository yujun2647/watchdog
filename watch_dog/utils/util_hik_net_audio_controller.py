"""
1、能放音频
2、能接收音频

两者是绝对冲突的，
    放完了，才能接收音频
        但是也可以，发送信号停止播放。

    但是接收音频是可以被打断的

"""
import os
import time
import logging
from typing import *
from ctypes import *
import multiprocessing as mp
from threading import Thread, Event as TEvent

from tqdm import tqdm

from watch_dog.utils.util_hik_sdk import HCHetSdk
from watch_dog.utils.util_thread import new_daemon_thread
from watch_dog.utils.util_multiprocess.queue import clear_queue_cache
from watch_dog.utils.util_multiprocess.base_worker import BaseWorker
from watch_dog.models.worker_req import WorkerStartReq, WorkerEndReq
from watch_dog.models.audios import AudioPlayReq, AudioPlayMod

__all__ = ["HIKNetAudioController"]


class HIKNetAudioController(BaseWorker):
    """
        这个是程序启动后就开启工作的常驻节点，理论上不会停止，因此，不用实现结束 “结束任务” 刘O记
    """

    PROCESS_SELF_MAP = dict()

    HC_SDK_HEARTBEAT_FILE = os.path.join(HCHetSdk.SDK_LIB_DIR,
                                         "heartbeat.pcm")

    def _sub_work_before_cleaned_up(self, work_req):
        pass

    def _handle_end_req(self, work_req: WorkerEndReq) -> bool:
        pass

    def _sub_work_done_cleaned_up(self, work_req):
        pass

    def _sub_side_work(self):
        pass

    def _handle_worker_exception(self, exp):
        pass

    def __init__(self):
        super().__init__()
        self._hc_sdk: Optional[HCHetSdk] = None

        self._play_switch = mp.Value("d", 0)
        self._record_switch = mp.Value("d", 1)

        self._audio_play_queue_req_force = mp.Queue()  # 优先队列
        self._audio_play_queue_req = mp.Queue()

        self._playing_lock = mp.Lock()
        self._playing_signal = mp.Event()
        self._play_done_signal = mp.Event()
        self._stop_play_signal = mp.Event()
        self._stopped_play_signal = mp.Event()

        # 监听状态是 暂停/继续
        self._pause_listening_signal_queue = mp.Queue()
        self._resume_listening_signal_queue = mp.Queue()

        self._history_heartbeat_thread_stop_signal: Optional[List[TEvent]] = []
        self._keep_heartbeat_thread: Optional[Thread] = None
        self._play_done_signal_for_heartbeat = mp.Event()

    @property
    def is_play_switch_on(self):
        return self._play_switch.value == 1

    @property
    def is_record_switch_on(self):
        return self._record_switch.value == 1

    @new_daemon_thread
    def _keep_send_heartbeats_async(self, stop_event: TEvent):
        while True:
            for _ in tqdm(range(50000), desc="Heartbeat"):
                if stop_event.is_set():
                    return

                if self._play_done_signal_for_heartbeat.wait(timeout=2):
                    self._play_done_signal_for_heartbeat.clear()
                    time.sleep(2)

                if self._playing_signal.is_set():
                    print(f"正在播放，self._playing_status.is_set(): "
                          f"{self._playing_signal.is_set()}")

                if not self._playing_signal.is_set():
                    self._play_audio_by_slices(
                        AudioPlayReq(audio_file=self.HC_SDK_HEARTBEAT_FILE,
                                     is_heartbeat=True))

    def _stop_history_heartbeat_thread(self):
        for event in self._history_heartbeat_thread_stop_signal:
            event.set()

    def _play_switch_on(self):
        """ 开启播放时，关闭录制"""
        self._play_switch.value = 1
        self._record_switch.value = 0

    def _play_switch_off(self):
        """关闭播放时，开启录制"""
        self._play_switch.value = 0
        self._record_switch.value = 1

    def _sub_init_work(self, work_req: WorkerStartReq):
        """ 初始化 hc_sdk"""
        if self._hc_sdk is None:
            self._hc_sdk = HCHetSdk(host=work_req.req_msg["host"],
                                    username=work_req.req_msg["username"],
                                    password=work_req.req_msg["password"])

            HIKNetAudioController.PROCESS_SELF_MAP[os.getpid()] = self
            self._hc_sdk.init_voice_handler(self.record_voice)

            self._stop_history_heartbeat_thread()
            stop_event = TEvent()
            self._keep_heartbeat_thread = Thread(
                target=self._keep_send_heartbeats_async,
                args=(stop_event,))
            self._keep_heartbeat_thread.start()

    def send_start_work_req(self, host="", username="", password=""):
        req_msg = dict(host=host, username=username, password=password)
        super().send_start_work_req(req_msg=req_msg)

    @CFUNCTYPE(c_bool, c_void_p, c_int, POINTER(c_char * 160), c_int, c_byte,
               c_void_p)
    def record_voice(self, lVoiceComHandle, pRecvDataBuffer, dwBufSize,
                     byAudioFlag, pUser):
        self: HIKNetAudioController = \
            HIKNetAudioController.PROCESS_SELF_MAP[os.getpid()]
        # print(self.worker_name)

    def _play_audio_by_slices(self, audio_play_req: AudioPlayReq):
        """
            调用解码， 播放
        :param audio_play_req:
        :return:
        """
        log_method = (logging.info if not audio_play_req.is_heartbeat
                      else lambda *args, **kwargs: None)
        with self._playing_lock:
            self._playing_signal.set()
            self._play_done_signal.clear()
            try:
                log_method(f"""
                -----------------------------------------------------------------
                            Playing {audio_play_req.audio_pcm_file}
                -----------------------------------------------------------------
                """)
                with open(audio_play_req.audio_pcm_file, "rb") as fp:
                    raw_audio_datas = fp.read()

                byte_length = len(raw_audio_datas)

                audio_datas = (c_byte * byte_length)(*raw_audio_datas)
                for vi in range(0, byte_length, 640):
                    end = vi + 640
                    if end > byte_length:
                        end = byte_length
                    play_gen = self._hc_sdk.play_audio_data(
                        audio_datas[vi: end])

                    for _ in play_gen:
                        if not self.is_play_switch_on:
                            return
                        if self._stop_play_signal.is_set():
                            self._stop_play_signal.clear()
                            self._stopped_play_signal.set()

                            return
            finally:
                self._playing_signal.clear()
                self._play_done_signal.set()
                self._play_done_signal_for_heartbeat.set()

                log_method(
                    f"""
                -----------------------------------------------------------------
                            End of playing {audio_play_req.audio_pcm_file}
                -----------------------------------------------------------------
                """)

    def listening_play_audio_req(self):
        while True:
            audio_play_queue_req_force: Optional[
                AudioPlayReq] = self.get_queue_item(
                queue=self._audio_play_queue_req_force,
                queue_name="_audio_play_queue_req_force")

            if audio_play_queue_req_force is not None:
                if self.is_play_switch_on:
                    self._play_audio_by_slices(audio_play_queue_req_force)
                    self.working_handled_num += 1
                continue

            audio_play_req: Optional[AudioPlayReq] = self.get_queue_item(
                queue=self._audio_play_queue_req,
                queue_name="_audio_play_queue_req")
            if audio_play_req is None:
                time.sleep(self.IDLE_TIME)
                continue

            if self.is_play_switch_on:
                self._play_audio_by_slices(audio_play_req)
                self.working_handled_num += 1
                time.sleep(20 / 1000.0)

    def _handle_start_req(self, work_req: WorkerStartReq) -> bool:
        print("_handling start req")
        # 阻塞，在这里监听，播放
        self.listening_play_audio_req()

        return True

    def stop_playing(self):
        if self._playing_signal.is_set():
            self._stop_play_signal.set()
            if self._stopped_play_signal.wait(timeout=1):
                pass
            self._stopped_play_signal.clear()

    def clear_queue_stop_playing(self):
        clear_queue_cache(self._audio_play_queue_req_force,
                          queue_msg="_audio_play_queue_req_force")
        clear_queue_cache(self._audio_play_queue_req,
                          queue_msg="_audio_play_queue_req")
        self.stop_playing()

    def play_audio(self, audio_file: str,
                   play_mod=AudioPlayMod.CLEAR_QUEUE_FORCE,
                   block=False, timeout=None):
        audio_play_req = AudioPlayReq(audio_file, play_mod=play_mod)
        self._play_switch_on()
        self._play_done_signal.clear()

        if play_mod in (AudioPlayMod.CLEAR_QUEUE_FORCE, AudioPlayMod.FORCE):
            self.stop_playing()
            clear_queue_cache(self._audio_play_queue_req_force,
                              queue_msg="_audio_play_queue_req_force")
            logging.info(f"[AudioPlay] cleared _audio_play_queue_req_force")
            self.put_queue_item(self._audio_play_queue_req_force,
                                audio_play_req,
                                queue_name="_audio_play_queue_req_force")

            if play_mod == AudioPlayMod.CLEAR_QUEUE_FORCE:
                clear_queue_cache(self._audio_play_queue_req,
                                  queue_msg="_audio_play_queue_req")
                logging.info(f"[AudioPlay] cleared _audio_play_queue_req")

        else:
            self.put_queue_item(self._audio_play_queue_req, audio_play_req,
                                queue_name="_audio_play_queue_req")
        logging.info(f"[AudioPlay][PUT QUEUE]: {audio_play_req.audio_file}")
        if block:
            if self._play_done_signal.wait(timeout=timeout):
                return True
            return False
        return True

    def _sub_clear_all_output_queues(self):
        if self._hc_sdk is not None:
            self._hc_sdk.release()


if __name__ == "__main__":
    from watch_dog.utils.util_log import set_scripts_logging

    set_scripts_logging(__file__, level=logging.INFO)
    hc = HIKNetAudioController()
    hc.start_work_in_subprocess()
