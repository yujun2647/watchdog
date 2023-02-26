import time
from typing import *

import multiprocessing as mp

from watch_dog.configs.constants import (CarMonitorState, PersonMonitorState,
                                         CameraConfig)
from watch_dog.models.detect_info import DetectInfo
from watch_dog.services.op_inst import (OpInst, CarWarningInst,
                                        VideoRecInst, SendMsg2ClientInst,
                                        PersonInst)
from watch_dog.models.worker_req import WorkerEndReq, WorkerStartReq
from watch_dog.services.sensors import CarSensor, PersonSensor
from watch_dog.services.base.wd_base_worker import WDBaseWorker


class Monitor(WDBaseWorker):
    def __sub_init__(self, **kwargs):
        self._car_sensor: Optional[CarSensor] = None
        self._person_sensor: Optional[PersonSensor] = None

        self._car_state = self.q_console.monitor_states.car_state
        self._person_state = self.q_console.monitor_states.person_state

        self._car_pos_time = mp.Value("d", 0)

    @property
    def car_state(self):
        return self._car_state.value

    @car_state.setter
    def car_state(self, state: int):
        self._car_state.value = state

    @property
    def car_pos_time(self):
        return self._car_pos_time.value

    @car_pos_time.setter
    def car_pos_time(self, p_time: float):
        self._car_pos_time.value = p_time

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

    def _check_car(self, has_car):
        ops = []
        if self.car_state == CarMonitorState.NEGATIVE:
            if has_car:
                tag = "车辆遮挡大门"
                self.car_state = CarMonitorState.POSITIVE
                self.car_pos_time = time.perf_counter()
                ops.append(CarWarningInst(warning=True))
                ops.append(VideoRecInst(start_record=True, tag=tag))
                ops.append(SendMsg2ClientInst(send=True, msg=tag))
        elif self.car_state == CarMonitorState.POSITIVE:
            if has_car:
                # 检查老赖
                now_time = time.perf_counter()
                car_alart_secs = CameraConfig.CAR_ALART_SECS.value
                if (self.car_pos_time and
                        (now_time - self.car_pos_time) > car_alart_secs):
                    tag = "车辆未离开"
                    ops.append(CarWarningInst(stop_warning=True))
                    ops.append(VideoRecInst(stop_record=True, tag=tag))
                    ops.append(SendMsg2ClientInst(send=True, msg=tag))
                    self.car_state = CarMonitorState.CAR_NOT_LEAVE
                    self.car_pos_time = 0
            else:
                tag = "车辆已离开"
                self.car_state = CarMonitorState.NEGATIVE
                self.car_pos_time = 0
                ops.append(CarWarningInst(stop_warning=True))
                ops.append(VideoRecInst(stop_record=True, tag=tag))
                ops.append(SendMsg2ClientInst(send=True, msg=tag))

        elif self.car_state == CarMonitorState.CAR_NOT_LEAVE:
            if not has_car:
                self.car_state = CarMonitorState.NEGATIVE
                tag = "车辆已离开"
                self.car_pos_time = 0
                ops.append(VideoRecInst(start_record=True, tag=tag))
                ops.append(SendMsg2ClientInst(send=True, msg=tag))

        return ops

    def _check_person(self, has_person):
        ops = []
        if self.person_state == PersonMonitorState.NEGATIVE:
            if has_person:
                ops.append(VideoRecInst(start_record=True, tag="有人出现"))
                ops.append(
                    SendMsg2ClientInst(
                        send=True,
                        msg=f"有人出现, sense_num: {self._person_sensor.sense_frame_num},"
                            f" not sense num: {self._person_sensor.not_sense_frame_num}"))
                ops.append(PersonInst(positive=True))
                self.person_state = PersonMonitorState.POSITIVE
        elif self.person_state == PersonMonitorState.POSITIVE:
            if not has_person:
                ops.append(VideoRecInst(stop_record=True, tag="有人出现"))
                ops.append(
                    SendMsg2ClientInst(
                        send=True,
                        msg=f"人已离开, sense_num: {self._person_sensor.sense_frame_num}"
                            f" not sense num: {self._person_sensor.not_sense_frame_num}"))
                self.person_state = PersonMonitorState.NEGATIVE

        return ops

    def _gen_op_inst(self, has_car: bool, has_person: bool):
        """
            如果之前没车，就是要找有车的状态，
            如果之前有车，就是要找没车的状态



        :param has_car:
        :param has_person:
        :return:
        """
        op_inst_list = []
        op_inst_list.extend(self._check_car(has_car))
        op_inst_list.extend(self._check_person(has_person))

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
        # print(f"""
        #
        # has_person: {has_person},
        # has_car: {has_car},
        # d_infos: {[d.__dict__ for d in d_infos]}
        #
        # """)

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
