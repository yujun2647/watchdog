import socket
import logging
from urllib.parse import urlparse

import urllib3


def get_local_ip():
    """import urllib3


def is_internet_connected():
    # noinspection PyBroadException
    try:
        http = urllib3.PoolManager()
        http.request('GET', 'https://baidu.com')
        return True
    except Exception as exp:
        return False
    查询本机ip地址
    :return:
    """
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        if s is not None:
            s.close()

    return ip


def get_host_name(url):
    return urlparse(url).hostname


def is_internet_connected():
    return is_connected("https://baidu.com")


def is_connected(host_name, time_out=1.5):
    # noinspection PyBroadException
    try:
        http = urllib3.PoolManager()
        time_out = time_out / 3  # 默认会 retry 3 次
        time_out_obj = urllib3.util.Timeout(connect=time_out)
        http.request("GET", host_name, timeout=time_out_obj)
        return True
    except Exception as exp:
        logging.warning(f"host_name: {host_name} is not connected..., \n"
                        f"request error: {exp}")
        return False


if __name__ == "__main__":
    logging.info("d")
    _host_name = "192.168.8.161"
    print(is_connected(_host_name, time_out=1))
