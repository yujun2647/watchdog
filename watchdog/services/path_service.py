import os
from watchdog.configs.constants import PathConfig
from watchdog.utils.util_path import ensure_dir_exist


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


def get_cache_videos():
    try:
        _, _, videos = next(os.walk(PathConfig.CACHE_DATAS_PATH))
    except StopIteration:
        return []

    videos = [v for v in videos if v.endswith(".mp4")]
    videos.sort(key=lambda v: v[:v.rindex("-")], reverse=True)
    return videos


if __name__ == "__main__":
    from datetime import datetime, timedelta
    ts = get_cache_videos()
    tt = datetime.now() - timedelta(days=5)
    tt_str = tt.strftime("%Y-%m-%d-%H-%M-%S-%f")
    removes = []
    for t in ts:
        _t = t[:t.rindex("-")]
        if _t < tt_str:
            removes.append(t)

    print("debug")
