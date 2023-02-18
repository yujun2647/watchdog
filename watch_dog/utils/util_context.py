from typing import *
from contextvars import ContextVar

# from socketio import Client

TEMP = ContextVar("temp var")
CLIENT_SIO = ContextVar("client_socketio")


def set_temp_var(value):
    TEMP.set(value)


def get_temp_var():
    return TEMP.get(None)

# def set_context_client_sio_data(client_sio: [Tuple[Client, int], None]):
#     CLIENT_SIO.set(client_sio)
#
#
# def get_context_client_sio_data() -> Tuple[Client, int]:
#     """
#
#     :return: 返回 client 对象和所属 进程id
#     """
#     return CLIENT_SIO.get((None, None))
