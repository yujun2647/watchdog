import os
from watchdog.utils.util_os import run_sys_command
from watchdog.utils.util_ffmpeg import check_ffmpeg


@check_ffmpeg
def to_pcm_audio(source_audio_path, output_audio_path,
                 channel=1, sample_rate=8000, bit=16):
    if channel not in (1, 2):
        raise ValueError("wrong value of channel, only support 1 or 2")
    if bit not in (16, 32):
        raise ValueError("wrong value of bit, only support 16 or 32")
    command = f"ffmpeg -i {source_audio_path} -acodec pcm_s{bit}le " \
              f"-f s{bit}le -ac 1 -ar {sample_rate} {output_audio_path} -y"
    run_sys_command(command)
    return output_audio_path


if __name__ == "__main__":
    from watchdog.utils.util_log import set_scripts_logging

    # set_scripts_logging(__file__)
    to_pcm_audio("ffmpeg -h", "")
