import uuid
import time
import random
import logging


def unique_uuid():
    return f"{uuid.uuid4()}-{int(random.random() * 10000)}"


def unique_time_id():
    return int(time.time() * 10000000)


if __name__ == "__main__":
    logging.debug(unique_uuid())
    logging.debug(unique_uuid())
    logging.debug(unique_uuid())
    logging.debug(unique_uuid())
    logging.debug(unique_uuid())
    logging.debug(unique_uuid())
