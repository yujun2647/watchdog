import time
import logging
from datetime import datetime, timedelta, timezone

SHA_TZ = timezone(timedelta(hours=8), name='Asia/Shanghai')


def get_utc_time() -> datetime:
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def get_bj_time() -> datetime:
    return get_utc_time().astimezone(SHA_TZ)


def get_bj_time_str(fmt="%Y-%m-%d-%H-%M-%S-%f") -> str:
    return get_bj_time().strftime(fmt)


def get_bj_date_str(fmt="%Y-%m-%d") -> str:
    return get_bj_time().strftime(fmt)


class Timer(object):

    def __init__(self, timeout=2, enable=True):
        self._start_timestamp = time.time()
        self._timeout = timeout
        if not enable:
            self.disable()

    def disable(self):
        self._start_timestamp -= self._timeout + 1

    def is_timeout(self):
        return time.time() - self._start_timestamp > self._timeout

    def reset_timer(self):
        self._start_timestamp = time.time()
        logging.info("reset")


def datetime2date_str(_time: datetime):
    return _time.strftime("%Y-%m-%d")


def time_test(test_time=None):
    if not test_time:
        test_time = get_bj_time_str()
    logging.debug(test_time)


if __name__ == "__main__":
    timer = Timer(timeout=3, enable=True)
    _timeout = timer.is_timeout()
    print("debug")
    tt = get_bj_time()
    tt2 = get_bj_time_str()
    tt3 = get_bj_date_str()

    time_test()
    time.sleep(2)
    time_test()
    time.sleep(2)
    time_test()
    time.sleep(2)
    time_test()
    logging.debug("debug")
