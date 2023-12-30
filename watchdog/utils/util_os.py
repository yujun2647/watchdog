from typing import *
import logging
import subprocess


def run_sys_command(command, raise_if_failed=True,
                    print_output=True) -> bool:
    """

    :param command:
    :param raise_if_failed:
    :param print_output:
    :return:
    """
    logging.info(f"""
    -----------------------------------------------------------------------
                Running Command: {command}
    -----------------------------------------------------------------------
    """)
    subp = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, encoding="utf-8",
                            universal_newlines=True,
                            bufsize=1)

    def _live_process():
        while True:
            buff = subp.stdout.readline()
            if print_output:
                print(buff)
            if buff == '' and subp.poll() is not None:
                break

    _live_process()

    if subp.poll() == 0:
        outputs = subp.communicate()
        end_outputs_str = "".join(outputs)
        if print_output:
            logging.info(end_outputs_str)
        return True
    else:
        outputs = subp.communicate()
        end_outputs_str = "".join(outputs)
        if print_output:
            logging.info(end_outputs_str)
        if raise_if_failed:
            raise Exception(f"shell execute Failed: {command}, \n"
                            f"{end_outputs_str}")
        return False


if __name__ == "__main__":
    run_sys_command("echo 123 && sleep 6 && echo 124")
