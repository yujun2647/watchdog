import os


class StartInst(object):

    def __init__(self, max_fps=8):
        self.max_fps = max_fps


class StartService(object):

    @classmethod
    def start_inst(cls):
        return StartInst(
            max_fps=os.cpu_count() * 2
        )
