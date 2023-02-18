import os
from typing import *
from tempfile import NamedTemporaryFile

from watch_dog.utils.util_audio import to_pcm_audio


class AudioPlayMod(object):
    """
        use when you are going to play an audio, tell the speaker when to play
        this audio
    """
    QUEUE_PLAY = 0
    # put into the audio queue, and play the audio in turn
    FORCE = 1
    # force to play the audio at once, after that, play the audios
    # remain in the audio queue one by one
    CLEAR_QUEUE_FORCE = 2
    # clear the cache audio queue at once and play the audio


class AudioPlayReq(object):

    def __init__(self, audio_file: str,
                 play_mod=AudioPlayMod.CLEAR_QUEUE_FORCE,
                 is_heartbeat=False):
        self.audio_file: str = audio_file
        self.play_mod: int = play_mod
        self._audio_pcm_file: Optional[str] = None
        self.is_heartbeat = is_heartbeat

    @property
    def audio_pcm_file(self):
        if self._audio_pcm_file is None:
            self._audio_pcm_file = self.to_standard_pcm_file()
        return self._audio_pcm_file

    def to_standard_pcm_file(self):
        if self.audio_file.endswith(".pcm"):
            return self.audio_file

        if not os.path.exists(self.audio_file):
            raise FileNotFoundError(f"file not exist: {self.audio_file}")

        base_name = os.path.basename(self.audio_file)
        filename = os.path.splitext(base_name)[0]
        temp_pcm_file = NamedTemporaryFile(prefix=f"{filename}-", suffix=".pcm",
                                           delete=False)
        return to_pcm_audio(self.audio_file, temp_pcm_file.name)


if __name__ == "__main__":
    from watch_dog.utils.util_log import set_scripts_logging

    set_scripts_logging(__file__)
    t = AudioPlayReq(
        audio_file="/home/walkerjun/myPythonCodes/sharingFiles/特别的人.wav")
    print("debug")
