import os
import argparse
from watchdog import __version__

parser = argparse.ArgumentParser()

parser.add_argument(
    "address", help="Camera address, like '/dev/video0' or "
                    "'rtsp://[username]:[password]@[ip]'",
    default="/dev/video0", type=str)

parser.version = str(__version__)
parser.add_argument('-V', action='version', help='print the version and exit')

parser.add_argument(
    "-port", help="API server port, default: 8000",
    default=8000, type=int)

parser.add_argument(
    "-width",
    help="video width, like 1280",
    default=1280,
    type=int
)
parser.add_argument(
    "-height",
    help="video_height, like 720",
    default=720,
    type=int
)

parser.add_argument(
    "-active-fps",
    help="the fps when object detected, default active_fps is "
         "os.cup_count() * 2",
    default=os.cpu_count() * 2,
    type=int
)

parser.add_argument(
    "-rest-fps",
    help="the fps when no object detected",
    default=1,
    type=int
)

parser.add_argument(
    "-car-alart-secs",
    help="car detected alart time",
    default=2 * 60,
    type=int
)
parser.add_argument(
    "-cache-path",
    help="the path store the videos, default cache_path is "
         "{$HOME}/.watchdog/video_cache",
    default="",
    type=str
)

parser.add_argument(
    "-cache-days",
    help="the days cache videos",
    default=30,
    type=int
)

args = parser.parse_args()

import logging

import setproctitle

from watchdog.configs.constants import CameraConfig, PathConfig
from watchdog.utils.util_log import set_scripts_logging

from watchdog.server.monkey_patches import MonkeyPatches

MonkeyPatches.patch_all(wsgi_server=True)
from watchdog.server.api_handlers import *
from watchdog.server.api_handlers.watch_handler import WatchCameraHandler
from watchdog.server.custom_server import CustomFlask
from watchdog.utils.util_router import load_routes_to_flask
from watchdog.services.workshop import WorkShop


def main():
    project_name = os.environ.get("PROJECT_NAME", "")
    setproctitle.setproctitle(f"{project_name}-MainProcess-{os.getpid()}")
    camera_address = args.address
    if args.cache_path:
        PathConfig.CACHE_DATAS_PATH = args.cache_path
    CameraConfig.REST_FPS.value = args.rest_fps
    CameraConfig.ACTIVE_FPS.value = args.active_fps
    CameraConfig.CAR_ALART_SECS.value = args.car_alart_secs
    CameraConfig.CACHE_DAYS.value = args.cache_days
    port = args.port
    set_scripts_logging(__file__)

    app = CustomFlask(__name__, template_folder="templates",
                      static_folder="static")
    load_routes_to_flask(app)
    ws = WorkShop(camera_address, video_width=args.width,
                  video_height=args.height)
    WatchCameraHandler.load_workshop(camera_address, ws)

    logging.info(f"""
    --------------------------------------------------------------------------
                Start WatchDog, view stream:
                http://0.0.0.0:{port}/stream
    --------------------------------------------------------------------------
    """)
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
