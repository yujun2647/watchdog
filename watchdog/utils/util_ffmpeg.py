from watchdog.utils.util_os import run_sys_command


def check_ffmpeg(func):
    def wrapper(*args, **kwargs):
        run_sys_command("ffmpeg -h", print_output=False)
        return func(*args, **kwargs)

    return wrapper
