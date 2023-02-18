from typing import *
from cv2 import cv2
from abc import abstractmethod

from watch_dog.models.audios import AudioPlayMod
from watch_dog.services.wd_queue_console import WdQueueConsole
from watch_dog.services.path_service import get_alart_audio_file


class OpInst(object):

    def __init__(self):
        self.name = type(self).__name__

    @classmethod
    @abstractmethod
    def merge(cls, op_inst_list):
        pass

    @abstractmethod
    def handle(self, q_console: WdQueueConsole):
        pass

    @classmethod
    def choose_first_not_empty(cls, *arg_lists):
        for a_list in arg_lists:
            if a_list:
                return a_list
        return []


class FPSInst(OpInst):

    def __init__(self, pull_up: bool = False, reduce: bool = False):
        super().__init__()
        self.pull_up: bool = pull_up
        self.reduce: bool = reduce

    @classmethod
    def merge(cls, op_inst_list: List["FPSInst"]) -> List["FPSInst"]:
        return cls.choose_first_not_empty(
            [i for i in op_inst_list if i.pull_up],
            [i for i in op_inst_list if i.reduce])[:1]

    def handle(self, q_console: WdQueueConsole):
        if self.pull_up:
            q_console.camera.adjust_camera_fps(15)
        # if self.reduce:
        #     q_console.camera.adjust_camera_fps(1)


class CarWarningInst(OpInst):
    WARNING_AUDIO_FILE = get_alart_audio_file()

    def __init__(self, warning: bool = False, stop_warning: bool = False):
        super().__init__()
        self.start_warning: bool = warning
        self.stop_warning: bool = stop_warning

    @classmethod
    def merge(cls, op_inst_list: List["CarWarningInst"]) \
            -> List["CarWarningInst"]:
        return cls.choose_first_not_empty(
            [i for i in op_inst_list if i.start_warning],
            [i for i in op_inst_list if i.stop_warning])[:1]

    def handle(self, q_console: WdQueueConsole):
        if q_console.camera.audio_worker is None:
            return
        if self.start_warning:
            q_console.camera.audio_worker.clear_queue_stop_playing()
            for _ in range(30):
                q_console.camera.audio_worker.play_audio(
                    self.WARNING_AUDIO_FILE,
                    play_mod=AudioPlayMod.QUEUE_PLAY)

        if self.stop_warning:
            q_console.camera.audio_worker.clear_queue_stop_playing()


class VideoRecordInst(OpInst):
    WARNING_AUDIO_FILE = get_alart_audio_file()

    def __init__(self, start_record: bool = False, stop_record: bool = False):
        super().__init__()
        self.start_record: bool = start_record
        self.stop_record: bool = stop_record

    @classmethod
    def merge(cls, op_inst_list: List["VideoRecordInst"]) \
            -> List["VideoRecordInst"]:
        return cls.choose_first_not_empty(
            [i for i in op_inst_list if i.start_record],
            [i for i in op_inst_list if i.stop_record])[:1]

    def handle(self, q_console: WdQueueConsole):
        if self.start_record:
            q_console.start_vid_record(tag="有人出现")
        if self.stop_record:
            q_console.stop_vid_record()


class SendMsg2ClientInst(OpInst):
    def __init__(self, send: bool = False, msg: str = ""):
        super().__init__()
        self.send: bool = send
        self.msg: str = msg

    @classmethod
    def merge(cls, op_inst_list: List["VideoRecordInst"]) \
            -> List["VideoRecordInst"]:
        return op_inst_list

    def handle(self, q_console: WdQueueConsole):
        pass


if __name__ == "__main__":
    OpInst()
