from typing import *

import multiprocessing as mp

from watch_dog.configs.constants import CarMonitorState, PersonMonitorState
from watch_dog.models.detect_info import DetectInfo
from watch_dog.services.op_inst import (OpInst, FPSInst, CarWarningInst,
                                        VideoRecordInst, SendMsg2ClientInst)
from watch_dog.models.worker_req import WorkerEndReq, WorkerStartReq
from watch_dog.services.sensors import CarSensor, PersonSensor
from watch_dog.services.base.wd_base_worker import WDBaseWorker


class Monitor(WDBaseWorker):
    """
        1、默认状态为 “看守状态”
        2、“看守状态” 需要做的事
            2.1 fps 设置为 1 (为了省电)
            2.2 监测是否进入其他状态

        3、若前置状态为 “看守状态” 时，检测到车辆遮挡大门了，则进入 “车位占用警报状态”
        4、“车位占用警报状态” 需要做的事：
            3.1 拉高 fps 至最高
            3.2 报警，播放报警音频
            3.3 开始录制视频
            3.4 通知客户端报警信息
            3.5 警报状态最多维持 3 min
        5、若车辆在 3min 内离开，则退出 “车位占用警报状态”，回到 “看守状态”
            4.1 停止播放报警音频
            4.2 结束视频录制
            4.3 降低 fps 至 1
            4.4 通知客户端车辆已离开
        6、若车辆 3min 后仍然未离开，则进入 “老赖状态”
        7、“老赖状态” 需要做的事
           7.1 停止播放报警音频
           7.2 结束视频录制
           7.3 降低 fps 至 1
           7.3 通知客户端车辆赖着不走
           7.4 在 “老赖状态” 检测到车辆，不再进入 “车位占用警报状态”
           7.5 监测状态，在车辆离开时，则退出 “老赖状态” 进入 “看守状态”

    """

    def __sub_init__(self, **kwargs):
        self._car_sensor: Optional[CarSensor] = None
        self._person_sensor: Optional[PersonSensor] = None

        self._car_state = mp.Value("i", CarMonitorState.NEGATIVE)
        self._person_state = mp.Value("i", PersonMonitorState.NEGATIVE)

    @property
    def car_state(self):
        return self._car_state.value

    @car_state.setter
    def car_state(self, state: int):
        self._car_state.value = state

    @property
    def person_state(self):
        return self._person_state.value

    @person_state.setter
    def person_state(self, state: int):
        self._person_state.value = state

    def _sub_work_before_cleaned_up(self, work_req):
        pass

    def _sub_init_work(self, work_req):
        if self._car_sensor is None:
            self._car_sensor = CarSensor()
        if self._person_sensor is None:
            self._person_sensor = PersonSensor()

    def _gen_op_inst(self, has_car: bool, has_person: bool):
        """
            如果之前没车，就是要找有车的状态，
            如果之前有车，就是要找没车的状态



        :param has_car:
        :param has_person:
        :return:
        """

        def _check_car():
            car_ops = []
            if self.car_state == CarMonitorState.NEGATIVE:
                if has_car:
                    self.car_state = CarMonitorState.POSITIVE
                    car_ops.append(CarWarningInst(warning=True))
                    car_ops.append(FPSInst(pull_up=True))
                    car_ops.append(VideoRecordInst(start_record=True))
                    car_ops.append(
                        SendMsg2ClientInst(send=True, msg="车辆遮挡大门"))
            elif self.car_state == CarMonitorState.POSITIVE:
                if not has_car:
                    self.car_state = CarMonitorState.NEGATIVE
                    car_ops.append(CarWarningInst(stop_warning=True))
                    car_ops.append(FPSInst(reduce=True))
                    car_ops.append(VideoRecordInst(stop_record=True))
                    car_ops.append(
                        SendMsg2ClientInst(send=True, msg="车辆已离开"))
            elif self.car_state == CarMonitorState.CAR_NOT_LEAVE:
                if not has_car:
                    self.car_state = CarMonitorState.NEGATIVE

            return car_ops

        def _check_person():
            person_ops = []
            if self.person_state == PersonMonitorState.NEGATIVE:
                if has_person:
                    person_ops.append(FPSInst(pull_up=True))
                    person_ops.append(VideoRecordInst(start_record=True))
                    person_ops.append(
                        SendMsg2ClientInst(
                            send=True,
                            msg=f"有人出现, sense_num: {self._person_sensor.sense_frame_num},"
                                f" not sense num: {self._person_sensor.not_sense_frame_num}"))
                    self.person_state = PersonMonitorState.POSITIVE
            elif self.person_state == PersonMonitorState.POSITIVE:
                if not has_person:
                    person_ops.append(FPSInst(reduce=True))
                    person_ops.append(VideoRecordInst(stop_record=True))
                    person_ops.append(
                        SendMsg2ClientInst(send=True,
                                           msg=f"人已离开, sense_num: {self._person_sensor.sense_frame_num}"
                                               f" not sense num: {self._person_sensor.not_sense_frame_num}"))
                    self.person_state = PersonMonitorState.NEGATIVE

            return person_ops

        op_inst_list = []
        op_inst_list.extend(_check_car())
        op_inst_list.extend(_check_person())

        op_inst_group: Dict[ClassVar[OpInst], List[OpInst]] = {}
        for op_inst in op_inst_list:
            op_inst_group.setdefault(type(op_inst), [])
            op_inst_group[type(op_inst)].append(op_inst)
        final_op_inst_list: List[OpInst] = []
        for _class, op_list in op_inst_group.items():
            op_inst = _class.merge(op_list)
            final_op_inst_list.extend(op_inst)

        return final_op_inst_list

    def _handle_start_req(self, work_req: WorkerStartReq) -> bool:
        d_infos: List[DetectInfo] = self.get_queue_item(
            self.q_console.detect_infos_sense_queue, timeout=5,
            wait_item=True)

        if not d_infos:
            return False

        fps = d_infos[0].fps
        center_box = self.q_console.camera.center_box
        has_person = self._person_sensor.senses(d_infos, fps, center_box)
        has_car = self._car_sensor.senses(d_infos, fps, center_box)

        op_inst_list = self._gen_op_inst(has_car=has_car, has_person=has_person)
        if op_inst_list:
            print("------------------------------------------\n\n")
            for op_inst in op_inst_list:
                print(op_inst.__dict__)
                op_inst.handle(q_console=self.q_console)
            self.working_handled_num += 1
            print(f"""
        self.car_state: {CarMonitorState.get_name(self.car_state)}
        self.person_state: {PersonMonitorState.get_name(self.person_state)}
            """)

            print("------------------------------------------\n\n")
        return False

    def _handle_end_req(self, work_req: WorkerEndReq) -> bool:
        pass

    def _sub_work_done_cleaned_up(self, work_req):
        pass

    def _sub_side_work(self):
        pass

    def _sub_clear_all_output_queues(self):
        pass

    def _handle_worker_exception(self, exp):
        pass
