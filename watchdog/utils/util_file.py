import os
import json
import pickle
import zipfile
import logging
import numpy as np

import cv2
from watchdog.utils.util_warning import ignore_error


@ignore_error
def save_json(filepath, obj: object, tag_msg=""):
    with open(filepath, "w") as fp:
        # noinspection PyBroadException
        try:
            json.dump(obj, fp, indent=4)
        except Exception as exp:
            logging.error(f"failed to save data to json, to {filepath}"
                          f"error: {exp}, tag_msg: {tag_msg}")
            filepath = filepath.replace(".json", ".pickle")
            save_pickle(filepath, obj, tag_msg=tag_msg)


@ignore_error
def save_pickle(filepath, obj: object, tag_msg=""):
    with open(filepath, "wb") as fp:
        try:
            pickle.dump(obj, fp)
        except Exception as exp:
            logging.error(f"failed to save data to pickle, {filepath}"
                          f"error: {exp}, tag_msg: {tag_msg}")


@ignore_error
def save_cv2_image(filepath, image: np.ndarray, tag_msg=""):
    try:
        cv2.imwrite(filepath, image)
        return True
    except Exception as exp:
        logging.error(f"failed to save img to {filepath}"
                      f"error: {exp}, tag_msg: {tag_msg}")
        return False


@ignore_error
def open_pickle(filepath, tag_msg=""):
    with open(filepath, "rb") as fp:
        try:
            return pickle.load(fp)
        except Exception as exp:
            logging.error(f"failed to load pickle data, {filepath}"
                          f"error: {exp}, tag_msg: {tag_msg}")


def make_zipfile(zip_filename: str, base_dir, dry_run=0, logger=None):
    """Create a zip file from all the files under 'base_dir'.

    The output zip file will be named 'base_name' + ".zip".  Returns the
    name of the output zip file.
       file_or_dir_path = _make_zipfile(
        file_or_dir_path,
        base_dir=file_or_dir_path,
    )
    """

    if zip_filename.endswith(".zip"):
        zip_filename = zip_filename[:-4]

    zip_filepath = os.path.join(os.path.dirname(base_dir), zip_filename)
    archive_dir = os.path.dirname(zip_filepath)

    zip_filepath += ".zip"

    if archive_dir and not os.path.exists(archive_dir):
        if logger is not None:
            logger.info("creating %s", archive_dir)
        if not dry_run:
            os.makedirs(archive_dir)

    if logger is not None:
        logger.info("creating '%s' and adding '%s' to it",
                    zip_filename, base_dir)

    if not dry_run:
        with zipfile.ZipFile(zip_filepath, "w",
                             compression=zipfile.ZIP_DEFLATED) as zf:
            _path = os.path.normpath(base_dir)
            if _path != os.curdir:
                zf.write(_path, _path.replace(archive_dir + "/", ""))
                if logger is not None:
                    logger.info("adding '%s'", _path)
            for dirpath, dirnames, filenames in os.walk(base_dir):
                for name in sorted(dirnames):
                    _path = os.path.normpath(os.path.join(dirpath, name))
                    zf.write(_path, _path.replace(archive_dir + "/", ""))
                    if logger is not None:
                        logger.info("adding '%s'", _path)
                for name in filenames:
                    _path = os.path.normpath(os.path.join(dirpath, name))
                    if os.path.isfile(_path):
                        zf.write(_path, _path.replace(archive_dir + "/", ""))
                        if logger is not None:
                            logger.info("adding '%s'", _path)

    return zip_filepath


if __name__ == "__main__":
    import sys
    import os
    pickle_file = "/home/walkerjun/video_school_datas/2022-08-25/standing_long_jump/83243e6b-113d-4fdf-a703-c28fa75431fc-6756/analysis_info.pickle"
    # pickle_file = "/home/walkerjun/下载/rope_jump_bend_knee_lack_count/analysis_info-10-9_10_0e07e24a-65192003-1fd7-441f-8dda-0d33accafa88-6940.pickle"
    datas = open_pickle(pickle_file)
    # round(sys.getsizeof(_frame) / 1024 / 1024, 2)
    # round(sys.getsizeof(_frame) / 1024 / 1024, 2)
    pickle_file_dir = os.path.dirname(pickle_file)
    # for data in datas:
    #     data.analyser = None

    save_pickle(os.path.join(pickle_file_dir, "test.pickle"), datas)
    print("debug")
