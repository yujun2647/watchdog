from watch_dog.server.api_handlers.watch_handler import WatchStream
from watch_dog.utils.util_router import Route


@Route("/debug/restartCamera")
class RestartCamera(WatchStream):

    def get(self):
        self.q_console.restart_camera(proxy=True)
