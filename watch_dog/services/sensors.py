import traceback
from abc import abstractmethod
from typing import List
import logging

from watch_dog.configs.constants import DetectLabels
from watch_dog.models.detect_info import DetectInfo


class SenseState(object):
    NOT_SENSED = 0
    SENSED = 1


class _Sensor(object):
    """感应器,
        感应目标，并传达建议指令

        检测是否在目标区域有检测到目标, 返回 True/False
    """

    # 目标检测区域，仅在此区域内检测
    # x, y, w, h : 其中 x:左上点横坐标， y: 左上点横坐标; w: 长度， h: 高度
    # 如果为 (0, 0, 0, 0) 表示全区域
    TARGET_AREA = (0, 0, 0, 0)

    SENSE_SECOND_TH = 0.1
    NOT_SENSE_SECOND_TH = 0.5

    SENSE_LABELS = []

    def __init__(self):
        self.sense_frame_num = 0
        self.not_sense_frame_num = 0

        self.now_sense_state = SenseState.NOT_SENSED

    def _select_d_infos(self, d_infos: List[DetectInfo]):
        return [d_info for d_info in d_infos
                if d_info.label in self.SENSE_LABELS]

    def senses(self, d_infos: List[DetectInfo], fps: int,
               target_area=None) -> bool:
        if target_area is None:
            target_area = self.TARGET_AREA
        frame_sense_result = False
        for d_info in d_infos:
            # noinspection PyBroadException
            if d_info is None or d_info.label not in self.SENSE_LABELS:
                continue
            try:
                if self._sense(d_info, target_area=target_area):
                    frame_sense_result = True
                    break
            except Exception as exp:
                logging.warning(f"[{type(self)}] sense failed, error: {exp}, "
                                f"{traceback.format_exc()}")
                continue

        if frame_sense_result:
            self.sense_frame_num += 1
            if self.sense_frame_num >= fps * self.SENSE_SECOND_TH:
                self.now_sense_state = SenseState.SENSED
                self.not_sense_frame_num = 0
        elif self.now_sense_state == SenseState.SENSED:
            self.not_sense_frame_num += 1
            if self.not_sense_frame_num >= fps * self.NOT_SENSE_SECOND_TH:
                self.now_sense_state = SenseState.NOT_SENSED
                self.sense_frame_num = 0

        # if isinstance(self, PersonSensor):
        #     print(f"""
        #         frame_sense_result: {frame_sense_result}
        #         self.now_sense_state: {self.now_sense_state}
        #         self.sense_frame_num: {self.sense_frame_num}
        #         self.not_sense_frame_num: {self.not_sense_frame_num}
        #
        #     """)

        return self.now_sense_state == SenseState.SENSED

    def _sense(self, d_info: DetectInfo, target_area) -> bool:
        if d_info.label not in self.SENSE_LABELS:
            return False

        whole_area = d_info.width * d_info.height
        if (d_info.area < whole_area * 0.003
                or d_info.area > whole_area * 0.75):
            return False

        cx, cy = d_info.center_point
        tx, ty, tw, th = target_area

        if (target_area == (0, 0, 0, 0) or
                (tx < cx < tx + tw and ty < cy < ty + th)):
            return True

        return False

    def reset(self):
        pass


class PersonSensor(_Sensor):
    """行人感应器"""

    SENSE_LABELS = [DetectLabels.PERSON, ]
    NOT_SENSE_SECOND_TH = 1.5


class CarSensor(_Sensor):
    """车辆感应器

    检测到，发送警报

    """
    SENSE_LABELS = [DetectLabels.CAR, DetectLabels.TRUCK, DetectLabels.BUS]
