import os
import logging
import multiprocessing as mp

from watch_dog.utils.utils_string import line2hump

PROJECT_NAME = "watch_dog"

os.environ["PROJECT_NAME"] = PROJECT_NAME

logger = logging.getLogger(PROJECT_NAME)


class Base(object):
    ENM_VALUE_MAP_NAME = "enum_values_map"

    @classmethod
    def config_value_set(cls):
        configs_map = cls.config_dict()
        value_set = set(configs_map.values())
        return value_set

    @classmethod
    def name_processor(cls, config_name, lower_case=False,
                       to_hump=False):
        if lower_case:
            config_name = config_name.lower()
        if to_hump:
            config_name = config_name.lower()
            config_name = line2hump(config_name)
        return config_name

    @classmethod
    def config_dict(cls, lower_case=False, to_hump=False):
        base_attrs = set(dir(Base))
        class_attrs = set(dir(cls))
        class_attrs = class_attrs - base_attrs
        return {
            cls.name_processor(
                key, lower_case=lower_case, to_hump=to_hump): getattr(cls, key)
            for key in class_attrs
            if not key.startswith("__")
               and not key.startswith("_")
               and not isinstance(getattr(cls, key), classmethod)
               and not callable(getattr(cls, key))
        }

    @classmethod
    def config_value_name_dict(cls):
        configs_map = cls.config_dict()
        return {value: key for key, value in configs_map.items()}

    @classmethod
    def get_name(cls, value, lower_case=False, to_hump=False) -> str:
        config_name = cls.config_value_name_dict()[value]
        config_name = cls.name_processor(config_name,
                                         lower_case=lower_case,
                                         to_hump=to_hump)
        return config_name

    @classmethod
    def in_config(cls, value):
        return value in cls.config_value_set()

    @classmethod
    def raise_if_config_not_exist(cls, value):
        value_set = cls.config_value_set()
        if value not in value_set:
            raise TypeError(f"{cls.__name__} must in {value_set} not {value}")


CURRENT_DIR = os.path.dirname(__file__)


class PathConfig(object):
    PROJECT_PATH = os.path.dirname(CURRENT_DIR)
    CACHE_DATAS_PATH = "/home/watch_dog/video_cache"


class WorkerEnableState(Base):
    """工作节点启用状态"""
    ENABLE = 1
    DISABLE = 0
    KILLED = -1


class WorkerState(Base):
    """ 工作进程状态
    """
    # 准备好接受新任务
    READY = 0

    # 正在工作，不接受另外的 task
    WORKING = 1
    # 卡死了，可以回收重启
    STUCK = -1


class WorkerWorkingState(Base):
    """
        工人工作状态下的子状态：
            一个工作，包括 未工作， 初始化，处理中，完成, 异常退出，已清理完成 六个状态
    """
    ERROR_EXIT = -3
    NOT_START = -2
    BEFORE_CLEANED_UP = -1
    INTI = 0
    DOING = 1
    DONE = 2
    DONE_CLEANED_UP = 3

    @classmethod
    def is_idle(cls, state):
        return state in (cls.NOT_START, cls.ERROR_EXIT, cls.DONE_CLEANED_UP)


class _MonitorState(Base):
    """ 监控状态 """
    # 负状态
    NEGATIVE = 0
    # 正状态
    POSITIVE = 1


class ActiveMonitorState(_MonitorState):
    """
        监控状态：
            非活跃、活跃， 分别表示是否当前画面是否有监控目标
    """
    # NEGATIVE、POSITIVE 分别表示 非活跃、活跃


class CarMonitorState(_MonitorState):
    """
        监控车辆状态

        # NEGATIVE、POSITIVE 分别表示 无车遮挡、有车遮挡

    """
    # 额外状态：车辆未离开，持续遮挡
    CAR_NOT_LEAVE = 2


class PersonMonitorState(_MonitorState):
    """ 行人监测
        NEGATIVE、POSITIVE 分别表示 无行人、有行人
    """


class DetectLabels(Base):
    PERSON = "person"
    BICYCLE = "bicycle"
    CAR = "car"
    MOTORCYCLE = "motorcycle"
    AIRPLANE = "airplane"
    BUS = "bus"
    TRAIN = "train"
    TRUCK = "truck"
    BOAT = "boat"
    TRAFFIC_LIGHT = "traffic light"
    FIRE_HYDRANT = "fire hydrant"
    STREET_SIGN = "street sign"
    STOP_SIGN = "stop sign"
    PARKING_METER = "parking meter"
    BENCH = "bench"
    BIRD = "bird"
    CAT = "cat"
    DOG = "dog"
    HORSE = "horse"
    SHEEP = "sheep"
    COW = "cow"
    ELEPHANT = "elephant"
    BEAR = "bear"
    ZEBRA = "zebra"
    GIRAFFE = "giraffe"
    HAT = "hat"
    BACKPACK = "backpack"
    UMBRELLA = "umbrella"
    SHOE = "shoe"
    EYE_GLASSES = "eye glasses"
    HANDBAG = "handbag"
    TIE = "tie"
    SUITCASE = "suitcase"
    FRISBEE = "frisbee"
    SKIS = "skis"
    SNOWBOARD = "snowboard"
    SPORTS_BALL = "sports ball"
    KITE = "kite"
    BASEBALL_BAT = "baseball bat"
    BASEBALL_GLOVE = "baseball glove"
    SKATEBOARD = "skateboard"
    SURFBOARD = "surfboard"
    TENNIS_RACKET = "tennis racket"
    BOTTLE = "bottle"
    PLATE = "plate"
    WINE_GLASS = "wine glass"
    CUP = "cup"
    FORK = "fork"
    KNIFE = "knife"
    SPOON = "spoon"
    BOWL = "bowl"
    BANANA = "banana"
    APPLE = "apple"
    SANDWICH = "sandwich"
    ORANGE = "orange"
    BROCCOLI = "broccoli"
    CARROT = "carrot"
    HOT_DOG = "hot dog"
    PIZZA = "pizza"
    DONUT = "donut"
    CAKE = "cake"
    CHAIR = "chair"
    COUCH = "couch"
    POTTED_PLANT = "potted plant"
    BED = "bed"
    MIRROR = "mirror"
    DINING_TABLE = "dining table"
    WINDOW = "window"
    DESK = "desk"
    TOILET = "toilet"
    DOOR = "door"
    TV = "tv"
    LAPTOP = "laptop"
    MOUSE = "mouse"
    REMOTE = "remote"
    KEYBOARD = "keyboard"
    CELL_PHONE = "cell phone"
    MICROWAVE = "microwave"
    OVEN = "oven"
    TOASTER = "toaster"
    SINK = "sink"
    REFRIGERATOR = "refrigerator"
    BLENDER = "blender"
    BOOK = "book"
    CLOCK = "clock"
    VASE = "vase"
    SCISSORS = "scissors"
    TEDDY_BEAR = "teddy bear"
    HAIR_DRIER = "hair drier"
    TOOTHBRUSH = "toothbrush"
    HAIR_BRUSH = "hair brush"


class CameraConfig(object):
    REST_FPS = mp.Value("i", 1)
    ACTIVE_FPS = mp.Value("i", os.cpu_count() * 2)
    REC_SECS = mp.Value("i", 60)
    VIDEO_WIDTH = mp.Value("i", 1280)
    VIDEO_HEIGHT = mp.Value("i", 720)
    CAR_ALART_SECS = mp.Value("i", 3 * 60)
    CACHE_DAYS = mp.Value("i", 30)
