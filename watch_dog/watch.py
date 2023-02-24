import os
import atexit
import argparse
import logging

from watch_dog.configs.constants import CameraConfig, PathConfig
from watch_dog.utils.util_process import ProcessController
from watch_dog.utils.util_log import set_scripts_logging
from watch_dog.utils.util_resource_tracker import tracker

from watch_dog.server.monkey_patches import MonkeyPatches

MonkeyPatches.patch_all(wsgi_server=True)
from watch_dog.server.api_handlers import *
from watch_dog.server.api_handlers.watch_handler import WatchCameraHandler
from watch_dog.server.custom_server import CustomFlask
from watch_dog.utils.util_router import load_routes_to_flask
from watch_dog.services.workshop import WorkShop


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "address", help="Camera address, like '/dev/video0' or "
                        "'rtsp://[username]:[password]@[ip]'",
        default="/dev/video0")

    parser.add_argument(
        "-port", help="API server port, default: 8000",
        default=8000)

    parser.add_argument(
        "-width",
        help="video width, like 1280",
        default=1280,
    )
    parser.add_argument(
        "-height",
        help="video_height, like 720",
        default=720,
    )

    parser.add_argument(
        "-active-fps",
        help="the fps when object detected, default active_fps is "
             "os.cup_count() * 2",
        default=os.cpu_count() * 2
    )

    parser.add_argument(
        "-rest-fps",
        help="the fps when no object detected",
        default=1
    )
    parser.add_argument(
        "-cache-path",
        help="the path store the videos",
        default="/home/watch_dog/video_cache",
    )

    args = parser.parse_args()
    camera_address = args.address
    PathConfig.CACHE_DATAS_PATH = args.cache_path
    video_width = int(args.width)
    video_height = int(args.height)
    rest_fps = int(args.rest_fps)
    active_fps = int(args.active_fps)
    CameraConfig.REST_FPS.value = rest_fps
    CameraConfig.ACTIVE_FPS.value = active_fps
    port = args.port
    set_scripts_logging(__file__)

    app = CustomFlask(__name__, template_folder="templates",
                      static_folder="static")
    load_routes_to_flask(app)
    ws = WorkShop(camera_address, video_width=video_width,
                  video_height=video_height)
    WatchCameraHandler.load_workshop(camera_address, ws)

    logging.info(f"""
    --------------------------------------------------------------------------
                Start WatchDog, view stream:
                http://0.0.0.0:{port}/stream
    --------------------------------------------------------------------------
    """)
    atexit.register(ProcessController.kill_sub_processes,
                    excludes=[tracker.pid, ])
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
