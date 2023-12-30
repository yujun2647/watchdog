from watchdog.models.audios import AudioPlayMod
from watchdog.server.api_handlers.watch_handler import WatchStream
from watchdog.utils.util_router import Route
from watchdog.services.path_service import get_person_detect_audio_file


@Route("/debug/restartCamera")
class RestartCamera(WatchStream):

    def get(self):
        self.q_console.restart_camera(proxy=True)


@Route("/debug/personWelcome")
class PersonWelcome(WatchStream):

    def get(self):
        if self.q_console.camera.audio_worker is not None:
            self.q_console.camera.audio_worker.play_audio(
                get_person_detect_audio_file(),
                play_mod=AudioPlayMod.FORCE)
