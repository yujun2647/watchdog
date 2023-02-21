import os
import time
import json
import logging
import traceback
from typing import *
import threading
from abc import ABC, abstractmethod
from queue import Empty, Full
import multiprocessing as mp

import setproctitle

from watch_dog.configs.constants import (WorkerEnableState,
                                         WorkerState, WorkerWorkingState)
from watch_dog.models.worker_req import WorkerReq, WorkerStartReq, WorkerEndReq

from watch_dog.utils.util_history_object import HistoryObject
from watch_dog.utils.util_queue import clear_queue_cache

from watch_dog.models.multi_objects.strs import MultiTaskId, MultiWorkerName
from watch_dog.models.multi_objects.task_info import TaskInfo
from watch_dog.models.health_info import HealthRspInfo
from watch_dog.utils.util_queue_console import QueueConsole
from watch_dog.utils.util_process import (ProcessController, MultiShardObject,
                                          WrapperMultiLock)


class BaseWorker(ABC):
    IDLE_TIME = 0.3
    # 队列获取超时时间
    Q_GET_TIMEOUT = 0.5
    # 队列入队超时时间
    Q_PUT_TIMEOUT = 0.5

    # 工作进程更新心跳的频率，单位秒
    HEART_BEAT_INTERVAL = 1

    # 等待 state 的超时时间
    WAIT_TIMEOUT = 15

    def __init__(self, q_console: Optional[QueueConsole] = None,
                 work_req_queue: Optional[mp.Queue] = None,
                 work_rsp_queue: Optional[mp.Queue] = None,
                 health_req_queue: Optional[mp.Queue] = None,
                 health_rsp_queue: Optional[mp.Queue] = None, **kwargs):
        if q_console is None:
            self.q_console = QueueConsole.init_default(console_id="simple")

        if work_req_queue is None:
            work_req_queue = mp.Queue()

        if health_req_queue is None:
            health_req_queue = mp.Queue()

        if health_rsp_queue is None:
            health_rsp_queue = mp.Queue()

        self._heart_beat = mp.Value("i", int(time.time()))

        self.project_name = os.environ.get("PROJECT_NAME", "")
        self._worker_enable_state = mp.Value("i", WorkerEnableState.ENABLE)
        self._worker_state = mp.Value("i", WorkerState.READY)
        self._worker_working_state = mp.Value("i", WorkerWorkingState.NOT_START)
        self._last_worker_pid = mp.Value("i", 0)
        self._worker_pid = mp.Value("i", 0)

        self._work_req_queue: Optional[mp.Queue] = work_req_queue
        self._work_rsp_queue: Optional[mp.Queue] = work_rsp_queue

        self._health_req_queue: Optional[mp.Queue] = health_req_queue
        self._health_rsp_queue: Optional[mp.Queue] = health_rsp_queue
        # 仅进程内部使用
        self.__worker_name = MultiWorkerName(type(self).__name__)
        # 用于共享至别的进程
        self._worker_name = MultiShardObject(self.__worker_name)

        # 工作进程要进行队列数据交互(get/put)或操作管道时，需先获取，
        # 同时外部要杀死工作进程时，也要先获取，
        # 防止在工作进程还在进行数据交互时杀死工作进程，导致数据损坏，从而导致队列/管道数据不可用
        # https://docs.python.org/zh-cn/3.9/library/multiprocessing.html?highlight=multiprocess#multiprocessing.Process.terminate
        self.butcher_knife = WrapperMultiLock(type(self).__name__)

        # 记录失效工作进程 pid
        self.dead_worker_pids = []
        self._worker: Optional[mp.Process] = None

        # 工作进程使用
        self._sub_heart_beat = time.time()
        self._task_info: TaskInfo = self.q_console.get_task_info()
        self._work_req: Optional[WorkerReq] = None

        # 工作记录变量
        # 已处理数量， 如已分析数量、已写入视频帧数量
        # 实际调用 self.working_handled_num
        self._working_handled_num = mp.Value("i", 0)
        # 用于进程内部使用
        self.__last_working_task_id = MultiTaskId("")
        # 用于共享至别的进程
        self._last_working_task_id = MultiShardObject(
            self.__last_working_task_id)
        # 用于进程内部使用
        self.__working_task_id = MultiTaskId("")
        # 用于共享至别的进程
        self._working_task_id = MultiShardObject(self.__working_task_id)

    def start_work_in_subprocess(self) -> mp.Process:
        self._worker = mp.Process(
            target=self.start_work_loop
        )
        self._worker.start()
        return self._worker

    def start_work_loop(self):
        """
            此方法应在子进程中运行
        :return:
        """
        self.last_worker_pid = self.worker_pid
        self.worker_pid = os.getpid()
        self.worker_name = (f"{type(self).__name__}-"
                            f"{self.q_console.console_id}-{self.worker_pid}")
        mp.current_process().name += f"-{self.worker_name}"
        setproctitle.setproctitle(f"{self.project_name}-{self.worker_name}")
        try:
            while True:
                with self.butcher_knife:
                    # 确保在杀死进程时，工作进程没有在进行任何工作
                    pass

                self._heart_pacemaker()
                # noinspection PyBroadException
                try:
                    self._handle_health_check()
                    self._handle_side_work()
                    # 如果 worker 处于未启动状态，则接收任何任务
                    if self.worker_enable_state != WorkerEnableState.ENABLE:
                        self.worker_state = WorkerState.READY
                        time.sleep(self.IDLE_TIME)
                        continue

                    if self._work_req_queue is None:
                        logging.error(
                            f"[{self.worker_name}]self.work_req_queue "
                            f"is None, exit")
                        exit()

                    # 每次都要检查新请求，如果没有请求，则复用旧请求
                    # 请求分为 开始请求、结束请求等；
                    # 只有当前工作已完成（工作状态为 is_idle），才能进行新工作
                    # 也可以由外部调用 self.force_work_done 来强制结束工作
                    self._work_req, is_new_req = self._get_new_work_req()

                    if self._work_req is not None:
                        self._work_req.is_new = is_new_req

                    if is_new_req:
                        # 只要是新请求，则直接传递给下方，至于如何处理，由实际工作者 self._do_work 来决定
                        self._handle_work(self._work_req)
                    elif not WorkerWorkingState.is_idle(
                            self.worker_working_state):
                        # 工作未完成，继续工作
                        self._handle_work(self._work_req)
                    else:  # 工作已完成，且没有新请求， 等待下次工作
                        time.sleep(self.IDLE_TIME)
                        self.worker_state = WorkerState.READY
                        continue
                except Exception as exp:
                    # 1、打印错误日志
                    # 2、处理错误，common 与 子类的 处理逻辑
                    # 3、执行清理逻辑，保证 worker 初始数据正常
                    # 4、设置工作状态为： 异常退出
                    # 5、设置工人状态为： 空闲中
                    logging.error(f"""
                    [Error][{self.worker_name}]: {exp},
    
                    worker_states: {json.dumps(self.get_states_dict(), indent=4)} 
    
                    {traceback.format_exc()}
                    """)
                    # noinspection PyBroadException
                    try:
                        self._handle_worker_exception(exp)
                    except Exception as exp:
                        logging.error(f"""
                            [ERROR][{self.worker_name}]: {exp}, exception happen
    
                            while handling exception
    
                            {traceback.format_exc()}
                            """)

                    self._do_work_done_cleaned_up(self._work_req)
                    self.worker_working_state = WorkerWorkingState.ERROR_EXIT
                    self.worker_state = WorkerState.READY
                    time.sleep(self.IDLE_TIME)
                    continue

        except KeyboardInterrupt:
            self._clear_all_output_queues()
        finally:
            self._clear_all_output_queues()

    def send_start_work_req(self, req_msg=None):
        """发送工作开始请求"""
        self.put_queue_item(self._work_req_queue,
                            WorkerStartReq(req_msg=req_msg))

    def send_end_work_req(self, req_msg=None):
        """发送工作结束请求"""
        self.put_queue_item(self._work_req_queue,
                            WorkerEndReq(req_msg=req_msg))

    def get_states_dict(self):
        logging.debug(
            f"pid:{os.getpid()}, thread：{threading.current_thread()}, "
            f"getting states dict,"
            f" lock status: {self.butcher_knife.__dict__}")
        states_dict = dict(
            last_worker_pid=self.last_worker_pid,
            worker_pid=self.worker_pid,
            worker_enable_state=WorkerEnableState.get_name(
                self.worker_enable_state),
            worker_state=WorkerState.get_name(self.worker_state),
            worker_working_state=WorkerWorkingState.get_name(
                self.worker_working_state),
            working_handled_num=self.working_handled_num,
            last_heart_beat=self.last_heart_beat,
            last_working_task_id=self.last_working_task_id,
            working_task_id=self.working_task_id
        )
        logging.debug(
            f"pid:{os.getpid()}, thread：{threading.current_thread()}, "
            f"get states dict done")
        return states_dict

    def is_ready(self):

        return self.worker_state == WorkerState.READY

    def is_working(self):
        return self.worker_working_state == WorkerWorkingState.DOING

    def is_error_exit(self):
        return self.worker_working_state == WorkerWorkingState.ERROR_EXIT

    def wait_ready_state(self, timeout=WAIT_TIMEOUT, force_stop=False):
        logging.info(f"[{self.worker_name}] waiting wait_ready_state")

        wait_round = int(timeout / 0.1)
        for i in range(wait_round):
            logging.info(f"[{self.worker_name}] waiting wait_ready_state,"
                         f" round {i}")
            logging.info(f"[{self.worker_name}] checking is ready")
            if self.is_ready():
                logging.info(f"[{self.worker_name}] is ready")
                self._notify_wait_done(waiting_msg="ready_state")
                logging.info(f"[{self.worker_name}] is ready !!")
                logging.info(f"[{self.worker_name}] waiting wait_ready_state "
                             f"done, success")
                return True

            logging.info(f"[{self.worker_name}] is not ready")
            now_state_name = WorkerState.get_name(self.worker_state)
            logging.info(f"[{self.worker_name}] got now state_name: "
                         f"{now_state_name}")
            logging.info(f"[{self.worker_name}] is not ready, "
                         f"now state: {now_state_name}")
            logging.info(f"[{self.worker_name}] notifying waiting")
            self._notify_waiting(waiting_msg="ready_state")
            logging.info(f"[{self.worker_name}] notify waiting down")
            time.sleep(0.1)
        self._notify_wait_timeout(waiting_msg="ready_state", timeout=timeout)
        logging.info(f"[{self.worker_name}] waiting wait_ready_state done,"
                     f" failed")
        if force_stop:
            logging.info(f"[{self.worker_name}] forcing stop ...")
            self.force_work_done()
            return self.wait_ready_state(timeout=2)
        return False

    def health_check(self) -> HealthRspInfo:
        self._health_req_queue.put(1)
        try:
            info: HealthRspInfo = self._health_rsp_queue.get(timeout=10)
            info.worker_status = "OK"
            return info
        except Empty:
            info = HealthRspInfo(
                states=self.get_states_dict(),
                worker_name=self.worker_name
            )
            info.worker_status = "No response"
            return info
        finally:
            clear_queue_cache(self._health_req_queue, queue_msg="heal_req_q")
            clear_queue_cache(self._health_rsp_queue, queue_msg="heal_rsp_q")

    def force_work_done(self):
        """
            强制结束工作状态
        :return:
        """
        self._set_working_state_done()

    def restart_worker(self) -> mp.Process:
        """重启 worker
            1、等待工作结束,
                如果没有结束，则调用 self.force_work_done, 然后再等待结束，
                如果依然等待超时，则主动重启 worker
            2、如果工作已结束，则直接重启
            3、重置工作状态

        :return:
        """
        _force_work_done = False
        if not self.wait_ready_state(timeout=1):
            logging.warning(f"[{self.worker_name}] worker is not ready before "
                            f"new task, forcing stop...  ")
            self.force_work_done()
            _force_work_done = True
        if not self.wait_ready_state(timeout=1):
            logging.error(f"[{self.worker_name}] worker is not ready, "
                          f"force restarting")
        if self._worker is not None:
            # 工作进程要进行队列数据交互(get/put)或操作管道时，需先获取 self.butcher_knife
            # 同时外部要杀死工作进程时，也要先获取，
            # 防止在工作进程还在进行数据交互时杀死工作进程，导致数据损坏，从而导致队列/管道数据不可用
            # https://docs.python.org/zh-cn/3.9/library/multiprocessing.html?highlight=multiprocess#multiprocessing.Process.terminate
            with self.butcher_knife:
                # 杀死进程前，必须清空所有本进程输出数据的队列，如果在队列有数据情况下杀死进程，
                # 会导致该队列变得不可用：
                #  杀死后，第一次get该队列，即使设置了 timeout， 仍然会造成阻塞，
                #  之后的get 则都会报 Empty 异常，即使 qsize() > 0 的，此时队列已经损坏不可用了
                self._clear_all_output_queues()
                ProcessController.kill_process(self._worker.pid)
            logging.info(f"[{self.worker_name}][Killed worker]: "
                         f"{self._worker.pid}")
        worker_pid_before_restart = self.worker_pid
        self._do_work_done_cleaned_up(self._work_req)
        self.start_work_in_subprocess()

        for _ in range(10):
            if self.worker_pid != worker_pid_before_restart:
                logging.info(f"[{self.worker_name}][Restart success], "
                             f"old_worker_pid: {worker_pid_before_restart}, "
                             f"new_worker_pid: {self.worker_pid}")
                return self._worker
            time.sleep(0.5)
        logging.warning(f"[{self.worker_name}][Restart failed]")
        return self._worker

    def get_queue_item(self, queue: mp.Queue, queue_name="", timeout=None,
                       wait_item=False):

        if queue.qsize() == 0:
            if timeout is None or not wait_item:
                return None

        queue_item = None
        if not queue_name and hasattr(queue, "name"):
            queue_name = getattr(queue, "name")

        timeout = self.Q_GET_TIMEOUT if timeout is None else timeout
        with self.butcher_knife:
            try:
                queue_item = queue.get(timeout=timeout)
            except Empty:
                if queue.qsize() > 0:
                    logging.warning(
                        f"Worker `{self.worker_name}` "
                        f"get queue-`{queue_name}` failed,"
                        f" maybe consumed by other "
                        f"process, what about use mp.Lock ? "
                        f"now {queue_name}.qsize: "
                        f"{queue.qsize()}, "
                        f"console_id: {self.q_console.console_id}")

        return queue_item

    def put_queue_item(self, queue: mp.Queue, obj: object, queue_name="",
                       timeout=None, force_put=False):
        """

        :param queue:
        :param obj:
        :param queue_name:
        :param timeout: 入队失败
        :param force_put: 是否强制入队， 如果为 True, 当发现队列满了时，会先做出队操作，再入队
        :return:
        """
        if not queue_name and hasattr(queue, "name"):
            queue_name = getattr(queue, "name")
        timeout = self.Q_PUT_TIMEOUT if timeout is None else timeout
        with self.butcher_knife:
            if queue.full() and force_put:
                try:
                    queue.get(timeout=timeout)
                except Empty:
                    logging.warning(
                        f"[{self.worker_name}] pop one item from "
                        f"queue-`{queue_name}` "
                        f"while the queue is full, but pop failed !!! which "
                        f"is totally unexpected ... "
                        f"now_queue_size: {queue.qsize()}")
            try:
                queue.put(obj, timeout=timeout)
            except Full:  # 入队超时，则放弃入队
                logging.warning(f"[{self.worker_name}] put queue item failed: "
                                f"queue_name: {queue_name}, "
                                f"q_size: {queue.qsize()} "
                                f"force_put: {force_put}")

    def _do_work_before_cleaned_up(self, work_req):
        """
            1、重置工作变量：
                - 计数器
            2、清理 HistoryObject
            3、执行子类 work_before_cleaned_up 方法
            4、设置工作状态为 BEFORE_CLEANED_UP
        :param work_req:
        :return:
        """
        self.working_handled_num = 0
        HistoryObject.clear_all_store_object()
        self._sub_work_before_cleaned_up(work_req)
        self.worker_working_state = WorkerWorkingState.BEFORE_CLEANED_UP

    def _do_work_done_cleaned_up(self, work_req):
        """
            清理工作，即使报错了，会保证工作状态为已清理
        :param work_req:
        :return:
        """
        # noinspection PyBroadException
        try:
            self._sub_work_done_cleaned_up(work_req)
        except Exception as exp:
            logging.error(f"""
                        [Error-{self.worker_name}]: {exp},  

                        _do_work_done_cleaned_up failed !!!

                        {traceback.format_exc()}
                        """)
        finally:
            self.worker_working_state = WorkerWorkingState.DONE_CLEANED_UP

    def _set_working_state_done(self):
        self.worker_working_state = WorkerWorkingState.DONE

    def _handle_work(self, work_req):
        """
            1、进入则设置工人状态：工作中
            2、如果当前工作状态为空闲中，则执行 工作前清理方法，并设置状态为 ”工作前已清理状态“ (before_cleaned_up)
            3、仅当完成了工作前的清理工作，工作状态为 before_cleaned_up, 才执行初始化方法，并设置工作状态为 init
            4、仅当工作状态为 init, 才能进入工作中状态 (doing)
            5、仅当工作状态为工作中，才能执行工作方法（self._do_working）
            6、工作状态 done 的设置，在 self._do_working 在内部进行
            7、如果工作状态变为 done, 则执行清理方法，并将工人状态设置为 空闲中 （ready）

            需要保证：
                1、第一次新请求，是闲置状态，依次执行 before_cleaned_up, init 然后状态变成 doing
                2、之后的新请求/非新请求 都只能执行 _do_working，然后在其中决定是否将状态设置成 done

            如果以上环节出了错，外部的错误处理会将工作状态设为异常状态（也是闲置状态），所以不会出现
            第一次新请求，不是空闲状态

        :param work_req:
        :return:
        """
        self.worker_state = WorkerState.WORKING
        if WorkerWorkingState.is_idle(self.worker_working_state):
            if not isinstance(work_req, WorkerEndReq):
                logging.info(f"[{self.worker_name}] start before_cleaned_up"
                             f" ...")
                self._do_work_before_cleaned_up(work_req)
                logging.info(f"[{self.worker_name}] before_cleaned_up done, "
                             f"now working_state: "
                             f"{self.worker_working_state_name}")
            else:  # 初始状态不接受结束请求
                self.worker_working_state = WorkerWorkingState.DONE_CLEANED_UP
                self.worker_state = WorkerState.READY
                logging.warning(f"[{self.worker_state}] receive WorkerEndReq "
                                f"at the begin, pass !!!")

        if self.worker_working_state == WorkerWorkingState.BEFORE_CLEANED_UP:
            logging.info(f"[{self.worker_name}] start init ...")
            self._do_work_init(work_req)
            logging.info(f"[{self.worker_name}] init done, "
                         f"now working_state: {self.worker_working_state_name}")

        if self.worker_working_state == WorkerWorkingState.INTI:
            self.worker_working_state = WorkerWorkingState.DOING
            logging.info(f"[{self.worker_name}] set working start to doing, "
                         f"now working_state: {self.worker_working_state_name}")

        if self.worker_working_state == WorkerWorkingState.DOING:
            self._do_working(work_req)

        if self.worker_working_state == WorkerWorkingState.DONE:
            logging.info(
                f"[{self.worker_name}] work done..., "
                f"now working_state: {self.worker_working_state_name}")
            logging.info(f"[{self.worker_name}] work done cleaning up ...")
            self._do_work_done_cleaned_up(work_req)
            self.worker_state = WorkerState.READY
            logging.info(f"[{self.worker_name}] work done cleaned up, "
                         f"now working_state: {self.worker_working_state_name}")

    def _renew_task_info(self):
        self._task_info = self.q_console.get_task_info()

    @classmethod
    def _notify_wait_done(cls, waiting_msg="ready_state"):
        pass

    @classmethod
    def _notify_waiting(cls, waiting_msg="ready_state"):
        pass

    def _notify_wait_timeout(self, waiting_msg="ready_state",
                             timeout=WAIT_TIMEOUT):
        logging.warning(f"[wait {self.worker_name} {waiting_msg} timeout] "
                        f"give up, time_out: {timeout}")

    def _handle_health_check(self):
        if not self._health_req_queue or not self._health_rsp_queue:
            return

        if self._health_req_queue.qsize() > 0:
            try:
                self.get_queue_item(self._health_req_queue,
                                    queue_name="self.health_req_queue",
                                    timeout=0.001)
                self.put_queue_item(
                    self._health_rsp_queue,
                    HealthRspInfo(
                        states=self.get_states_dict(),
                        worker_name=self.worker_name
                    ),
                    queue_name="self.health_rsp_queue",
                    force_put=True
                )
            except Empty:
                pass

    def _handle_side_work(self):
        """
            处理其他请求， 如： 更新人脸数据、加载模型
            处理时机：与健康检查同级，任何时候

        """
        # side work 不应该影响 worker 主要功能
        try:
            self._sub_side_work()
        except Exception as exp:
            logging.error(f"[ERROR][{self.worker_name}] handle side-work "
                          f"failed, error: {exp}, {traceback.format_exc()}")

    def _get_new_work_req(self) -> Tuple[WorkerReq, bool]:
        queue_item = self.get_queue_item(self._work_req_queue,
                                         queue_name="work_req_queue",
                                         timeout=0.5)
        if queue_item is None:
            return self._work_req, False

        self._work_req: WorkerReq = queue_item
        logging.info(f"[{self.worker_name}] new work req"
                     f"{self._work_req.desc_dict_text()}")

        return self._work_req, True

    @abstractmethod
    def _sub_work_before_cleaned_up(self, work_req):
        """
            子类执行的 clean_up
        :param work_req:
        :return:
        """

    @abstractmethod
    def _sub_init_work(self, work_req):
        """
            子类执行的 init_work
        :return:
        """

    @abstractmethod
    def _handle_start_req(self, work_req: WorkerStartReq) -> bool:
        """

        :param work_req:
        :return: 告诉后方，当前是否处理完了, 如处理完了，就会进行收尾工作，否则继续当前工作
        """
        logging.info(f"[{self.worker_name}] handling start req")
        time.sleep(1)
        self.working_handled_num += 1
        return False

    @abstractmethod
    def _handle_end_req(self, work_req: WorkerEndReq) -> bool:
        """

        :param work_req:
        :return: 告诉后方，当前是否处理完了, 如处理完了，就会进行收尾工作，否则继续当前工作
        """
        return True

    @abstractmethod
    def _sub_work_done_cleaned_up(self, work_req):
        """
            子类执行的 clean_up
        :return:
        """
        pass

    @abstractmethod
    def _sub_side_work(self):
        """处理额外自定义工作"""
        pass

    @abstractmethod
    def _sub_clear_all_output_queues(self):
        pass

    @abstractmethod
    def _handle_worker_exception(self, exp):
        pass

    def _do_working(self, work_req: Optional[WorkerReq]):
        """

        :param work_req:
        :return:
        """
        if isinstance(work_req, WorkerEndReq):
            # logging.info(f"[{self.worker_name}] handle end req: "
            #              f"{work_req.desc_dict_text()}")
            is_end = self._handle_end_req(work_req)
            # logging.info(f"[{self.worker_name}] handle end req done, "
            #              f"is_end: {is_end}")
        elif isinstance(work_req, WorkerStartReq):
            is_end = self._handle_start_req(work_req)
        else:
            raise TypeError(f"[{self.worker_name}] "
                            f"unknown type of work req: {type(work_req)}")

        if is_end:
            self._set_working_state_done()

    def _heart_pacemaker(self):
        """
            🫀心脏起搏器
        :return:
        """
        now = time.time()
        if now - self._sub_heart_beat > self.HEART_BEAT_INTERVAL:
            self._sub_heart_beat = now
            self.heart_beat = now

    def _do_work_init(self, work_req):
        """
            1、更新 self._task_info
            2、更新 self.working_task_id
            3、设置 task_info 上下文
            4、执行子类 init 方法
            5、设置工作状态为 init
        :param work_req:
        :return:
        """
        self._renew_task_info()
        self.last_working_task_id = self.working_task_id
        self.working_task_id = self._task_info.task_id
        self.q_console.set_task_info_context()
        self._sub_init_work(work_req)
        self.worker_working_state = WorkerWorkingState.INTI

    def _clear_all_output_queues(self):
        """重启前，必须调用，由非本工作进程调用
        """
        # 调用一下基于队列实现的共享变量，确保 put 数据的进程为非工作进程
        self.get_states_dict()
        self.q_console.get_task_info()

        if self._health_rsp_queue is not None:
            clear_queue_cache(self._health_rsp_queue, "health_rsp_queue")

        try:
            self._sub_clear_all_output_queues()
        except Exception as exp:
            logging.error(f"[ERROR][{self.worker_name}] handle "
                          f"_sub_clear_all_output_queues"
                          f"failed, error: {exp}, {traceback.format_exc()}")

    @property
    def worker_enable_state(self):
        return self._worker_enable_state.value

    @property
    def worker_state(self):
        return self._worker_state.value

    @property
    def worker_working_state(self):
        return self._worker_working_state.value

    @property
    def worker_working_state_name(self):
        return WorkerWorkingState.get_name(self.worker_working_state)

    @property
    def last_worker_pid(self):
        return self._last_worker_pid.value

    @property
    def worker_pid(self):
        return self._worker_pid.value

    @property
    def heart_beat(self):
        return self._heart_beat.value

    @property
    def last_heart_beat(self):
        """距离上次心跳更新时间，可以用来检查进程活性"""
        return round(time.time() - self.heart_beat, 2)

    @property
    def working_handled_num(self):
        return self._working_handled_num.value

    @property
    def worker_name(self):
        _worker_name = self.__worker_name
        with self.butcher_knife as thread_acquire_success:
            if thread_acquire_success:
                _worker_name = self._worker_name.get()
        return _worker_name.value

    @property
    def last_working_task_id(self):
        _last_working_task_id = self.__last_working_task_id
        with self.butcher_knife as thread_acquire_success:
            if thread_acquire_success:
                _last_working_task_id = self._last_working_task_id.get()

        return _last_working_task_id.value

    @property
    def working_task_id(self):
        _working_task_id = self.__working_task_id
        with self.butcher_knife as thread_acquire_success:
            if thread_acquire_success:
                _working_task_id = self._working_task_id.get()
        return _working_task_id.value

    @worker_enable_state.setter
    def worker_enable_state(self, value):
        assert WorkerEnableState.in_config(value)
        self._worker_enable_state.value = value

    @worker_state.setter
    def worker_state(self, value):
        assert WorkerState.in_config(value)
        self._worker_state.value = value

    @worker_working_state.setter
    def worker_working_state(self, value):
        assert WorkerWorkingState.in_config(value)
        self._worker_working_state.value = value

    @worker_pid.setter
    def worker_pid(self, value):
        self._worker_pid.value = value

    @last_worker_pid.setter
    def last_worker_pid(self, value):
        self._last_worker_pid.value = value

    @heart_beat.setter
    def heart_beat(self, value):
        self._heart_beat.value = int(value)

    @working_handled_num.setter
    def working_handled_num(self, value):
        self._working_handled_num.value = int(value)

    @last_working_task_id.setter
    def last_working_task_id(self, task_id):
        with self.butcher_knife as thread_acquire_success:
            if thread_acquire_success:
                self._last_working_task_id.update_attr("value", task_id)

    @working_task_id.setter
    def working_task_id(self, task_id):
        with self.butcher_knife as thread_acquire_success:
            if thread_acquire_success:
                self._working_task_id.update_attr("value", task_id)

    @worker_name.setter
    def worker_name(self, name):
        with self.butcher_knife as thread_acquire_success:
            if thread_acquire_success:
                self._worker_name.update_attr("value", name)

    def simple_test(self):
        self.start_work_in_subprocess()
        last_heat_beat = 0
        self.send_start_work_req()
        while True:
            now_heart_beat = self.heart_beat
            if now_heart_beat != last_heat_beat:
                print(f"now heart beat: {now_heart_beat}")
                last_heat_beat = now_heart_beat

            if self.working_handled_num == 10:
                self.send_end_work_req()
                break


if __name__ == "__main__":
    class TestWorker(BaseWorker):
        def _sub_work_before_cleaned_up(self, work_req):
            print("do work_before_cleaned_up")

        def _sub_init_work(self, work_req):
            print("do init_work")

        def _handle_start_req(self, work_req: WorkerStartReq) -> bool:
            time.sleep(1)
            self.working_handled_num += 1
            print(f"handled start req, working_handled_num: "
                  f"{self.working_handled_num}")
            # 可提前结束
            if self.working_handled_num == 100:
                return True

            return False

        def _handle_end_req(self, work_req: WorkerEndReq) -> bool:
            time.sleep(1)
            self.working_handled_num += 1
            print(f"handled end req: self.working_handled_num: "
                  f"{self.working_handled_num}")
            return True

        def _sub_work_done_cleaned_up(self, work_req):
            print("do work_done_cleaned_up")

        def _sub_side_work(self):
            pass

        def _sub_clear_all_output_queues(self):
            pass

        def _handle_worker_exception(self, exp):
            pass


    t = TestWorker(None, work_req_queue=mp.Queue())
    t.simple_test()
