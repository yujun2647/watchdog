from typing import *

import os
import logging
from watch_dog.configs.constants import PathConfig

if TYPE_CHECKING:
    pass


def ensure_dir_exist(dir_path):
    if dir_path and not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
    return dir_path


def judge_not_exist_isfile(path):
    return "." in path[-10:]


def join_ensure_exist(*paths):
    paths = [str(p) for p in paths]
    _path = os.path.join(*paths)
    if judge_not_exist_isfile(_path):
        ensure_dir_exist(os.path.dirname(_path))
    else:
        ensure_dir_exist(_path)
    return _path


def gen_process_dir(source_dir, process_name):
    parent_dir = os.path.dirname(source_dir)
    process_folder = f"{source_dir}_{process_name}"
    return join_ensure_exist(parent_dir, process_folder)


def gen_process_filepath(source_filepath, process_name):
    parent_dir = os.path.dirname(source_filepath)
    process_dir = gen_process_dir(parent_dir, process_name)
    return os.path.join(process_dir, os.path.basename(source_filepath))


def get_endpoint_index(filepath):
    return filepath.rindex(".")


def get_dir_file_extension_name(filepath):
    dir_name = os.path.dirname(filepath)
    base_filename = os.path.basename(filepath)
    endpoint_index = get_endpoint_index(base_filename)
    return (dir_name, base_filename[:endpoint_index],
            base_filename[endpoint_index + 1:])


def get_basename_without_extension(filepath):
    return get_dir_file_extension_name(filepath)[1]


def get_extensions(filepath):
    return get_dir_file_extension_name(filepath)[2]


def get_filepath_no_ext(filepath):
    endpoint_index = get_endpoint_index(filepath)
    return filepath[:endpoint_index]


def raise_error_if_not_exists(filepaths):
    for filepath in filepaths:
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Missing filepath: {filepath}")
    return True


TEMP_FOLDER = "temp"


def get_temp_path():
    return join_ensure_exist(PathConfig.PROJECT_PATH, TEMP_FOLDER)


def get_project_path():
    return PathConfig.PROJECT_PATH


def get_temp_process_dir(process: str):
    return join_ensure_exist(PathConfig.PROJECT_PATH, TEMP_FOLDER, process)


def get_temp_process_filepath(process: str, filename: str):
    return join_ensure_exist(get_temp_process_dir(process), filename)


def get_log_path(_file_):
    folder_path = get_temp_process_dir("scripts_logs")
    file = os.path.basename(_file_)
    log_filename = f"{file[:file.rindex('.')]}.log"
    return os.path.join(folder_path, log_filename)


def get_result_dir(video_filepath):
    """在上层文件夹下，生成与文件名同名的文件夹"""
    pre_video_dir = os.path.dirname(os.path.dirname(video_filepath))
    video_name = video_filepath.split('/')[-1].split('.')[0]
    result_dir = os.path.join(pre_video_dir, video_name)
    return result_dir


def get_hc_sdk_lib_path():
    return os.path.join(PathConfig.PROJECT_PATH, "libs/hc_net_sdk/linux")
