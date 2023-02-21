import os
from watch_dog.configs.constants import PathConfig
from watch_dog.utils.util_path import ensure_dir_exist


def get_hc_sdk_lib_path():
    return os.path.join(PathConfig.PROJECT_PATH, "libs/hc_net_sdk/linux")


def get_static_dir_path():
    return os.path.join(PathConfig.PROJECT_PATH, "static")


def get_static_filepath(filename):
    return os.path.join(get_static_dir_path(), filename)


def get_person_detect_audio_file():
    return get_static_filepath("person_detect.pcm")


def get_alart_audio_file():
    return get_static_filepath("car_alart.pcm")


def get_cache_path():
    return ensure_dir_exist(PathConfig.CACHE_DATAS_PATH)


def get_cache_filepath(filename):
    return os.path.join(get_cache_path(), filename)


if __name__ == "__main__":
    t = get_cache_filepath("test.mp4")
    print("debug")
