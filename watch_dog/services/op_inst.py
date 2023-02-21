from typing import *
import cv2
from abc import abstractmethod

from watch_dog.models.audios import AudioPlayMod
from watch_dog.services.wd_queue_console import WdQueueConsole
from watch_dog.services.path_service import (get_alart_audio_file,
                                             get_person_detect_audio_file)


class OpInst(object):

    def __init__(self, positive=False):
        self.name = type(self).__name__
        self.positive = positive

    @classmethod
    @abstractmethod
    def merge(cls, op_inst_list):
        return [i for i in op_inst_list if i.positive][:1]

    @abstractmethod
    def handle(self, q_console: WdQueueConsole):
        pass

    @classmethod
    def choose_first_not_empty(cls, *arg_lists):
        for a_list in arg_lists:
            if a_list:
                return a_list
        return []


class PersonInst(OpInst):
    DETECT_AUDIO_FILE = get_person_detect_audio_file()

    @classmethod
    def merge(cls, op_inst_list: List["PersonInst"]):
        return OpInst.merge(op_inst_list)

    def handle(self, q_console: WdQueueConsole):
        if q_console.camera.audio_worker is None:
            return
        if self.positive:
            q_console.camera.audio_worker.play_audio(
                self.DETECT_AUDIO_FILE,
                play_mod=AudioPlayMod.FORCE)


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


class VideoRecInst(OpInst):
    WARNING_AUDIO_FILE = get_alart_audio_file()

    def __init__(self, start_record: bool = False, stop_record: bool = False,
                 tag="有人出现"):
        super().__init__()
        self.start_record: bool = start_record
        self.stop_record: bool = stop_record
        self.tag = tag

    @classmethod
    def merge(cls, op_inst_list: List["VideoRecInst"]) \
            -> List["VideoRecInst"]:
        return cls.choose_first_not_empty(
            [i for i in op_inst_list if i.start_record],
            [i for i in op_inst_list if i.stop_record])[:1]

    def handle(self, q_console: WdQueueConsole):
        if self.start_record:
            q_console.start_vid_record(tag=self.tag)
        if self.stop_record:
            q_console.stop_vid_record()


class SendMsg2ClientInst(OpInst):
    def __init__(self, send: bool = False, msg: str = ""):
        super().__init__()
        self.send: bool = send
        self.msg: str = msg

    @classmethod
    def merge(cls, op_inst_list: List["VideoRecInst"]) \
            -> List["VideoRecInst"]:
        return op_inst_list

    def handle(self, q_console: WdQueueConsole):
        pass


if __name__ == "__main__":
    OpInst()
