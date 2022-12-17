import os


class HealthInfo(object):

    def __init__(self):
        self.pid = None
        self.worker_msg = None
        self.worker_name = None
        self.worker_status = None
        self.worker_states = None


class HealthReqInfo(object):
    def __init__(self):
        pass


class HealthRspInfo(HealthInfo):

    def __init__(self, states=None, worker_name=None):
        super().__init__()
        self.pid = os.getpid()
        self.worker_states = states
        self.worker_name = worker_name


if __name__ == "__main__":
    health_rsp_info = HealthRspInfo()
    print("debug")
