import logging
import os
import time
from typing import *
from threading import Lock

import socketio
from socketio import Client
from engineio.payload import Payload
from engineio.server import Server as EngineioServer
from flask import Flask, session, request
from flask_socketio import SocketIO, emit

from backend_configs.config import ServiceConfig
from backend_configs.constants import SportWebsocketEvent
from backend_utils.util_context import set_context_client_sio_data, \
    get_context_client_sio_data
from backend_utils.util_thread import new_thread
from backend_utils.util_warning import ignore_error
from backend_models.websocket_event import WebsocketEvent, DebugLogEvent


class WebsocketServer(object):
    _EMIT_LOCK = Lock()

    class _WrapperEngineioServer(EngineioServer):
        # 解决日志报错：Session is disconnected
        def _get_socket(self, sid):
            """Return the socket object for a given session."""
            try:
                s = self.sockets[sid]
            except KeyError:
                raise KeyError("Session not found")
            if s.closed:
                del self.sockets[sid]
                # raise KeyError('Session is disconnected')
                raise ConnectionError("Session is disconnected")
            return s

    socketio.Server._engineio_server_class = (
        lambda self: WebsocketServer._WrapperEngineioServer)

    COMMON_ACCEPT_EVENT = "video_school_event"
    NAMESPACE = "/video_school"
    BROADCAST_EVENT = "video_school_broadcast"

    SOCKETIO: Optional[SocketIO] = None

    # 设置这个 防止 ValueError: Too many packets in payload
    # https://github.com/miguelgrinberg/python-engineio/issues/142
    ENGINEIO_MAX_DECODE_PACKETS = 500

    # Set this variable to "threading", "eventlet" or "gevent" to test the
    # different async modes, or leave it set to None for the application to choose
    # the best option based on installed packages.
    ASYNC_MODE = "threading"

    @classmethod
    def init_sport_websocket(cls, app: Flask):
        app.config['SECRET_KEY'] = 'secret!23928lkjsldjlkf'
        if cls.SOCKETIO is None:
            Payload.max_decode_packets = cls.ENGINEIO_MAX_DECODE_PACKETS
            cls.SOCKETIO = SocketIO(app, async_mode=cls.ASYNC_MODE,
                                    cors_allowed_origins="*")

        @cls.SOCKETIO.on(cls.COMMON_ACCEPT_EVENT, namespace=cls.NAMESPACE)
        def test_message(message):
            session["receiveCount"] = session.get("receiveCount", 0) + 1
            logging.info(message)

        @cls.SOCKETIO.on(cls.BROADCAST_EVENT, namespace=cls.NAMESPACE)
        def mtest_broadcast_message(message):
            session["receiveCount"] = session.get("receiveCount", 0) + 1
            message["receiveCount"] = session["receiveCount"]
            wm = WebsocketEvent(**message)
            data = wm.get_msg()
            logging.info(f"[Websocket broadcast msg]: {data}")
            cls.broadcast_msg(wm)

        @cls.SOCKETIO.on("disconnect", namespace=cls.NAMESPACE)
        def mtest_disconnect():
            print("Client disconnected", request.sid)

    @classmethod
    def test_msg(cls, extra_msg=None):
        session["receiveCount"] = session.get("receiveCount", 0) + 1
        data_msg = dict(data=f"this is test msg: {extra_msg}",
                        count=session["receiveCount"])
        cls.SOCKETIO.emit("response-0", data_msg,
                          broadcast=True,
                          namespace=cls.NAMESPACE)

    @classmethod
    def bind_event(cls, event: WebsocketEvent, callback: Callable,
                   args=None, kwargs=None):
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}

        @cls.SOCKETIO.on(event.EVENT, namespace=cls.NAMESPACE)
        def bind_call(message):
            callback(*args, **kwargs)
            wm = WebsocketEvent(**message)
            if wm.event == SportWebsocketEvent.ACTION_DEBUG:
                wm.msgType = "Debug"
            with cls._EMIT_LOCK:
                emit(wm.event, wm.get_msg(), broadcast=True)

    @classmethod
    @ignore_error
    def broadcast_msg(cls, wsm: WebsocketEvent):
        if wsm.event == SportWebsocketEvent.ACTION_DEBUG:
            wsm.msgType = "Debug"
        wsm.notify_end()
        with cls._EMIT_LOCK:
            cls.SOCKETIO.emit(wsm.event, wsm.get_msg(), broadcast=True,
                              namespace=cls.NAMESPACE)


class SportWebsocketClient(WebsocketServer):
    @classmethod
    def get_context_client_sio(cls, domain="localhost"):
        client_sio_data = get_context_client_sio_data()
        client_sio, pid = client_sio_data
        this_pid = os.getpid()
        if this_pid == pid and client_sio:
            return client_sio

        client_sio = Client()
        setattr(client_sio, "true_connected", False)

        @client_sio.on('connect', namespace=cls.NAMESPACE)
        def on_connect():
            client_sio.emit(
                cls.COMMON_ACCEPT_EVENT,
                data=f"\nPython client {client_sio.sid} connected...\n",
                namespace=cls.NAMESPACE)
            setattr(client_sio, "true_connected", True)

        url = f"http://{domain}:{ServiceConfig.PORT}"
        try:
            client_sio.connect(url, namespaces=[cls.NAMESPACE, ])
        except Exception as exp:
            logging.error(f"connect to {url} failed")
            raise
        set_context_client_sio_data((client_sio, this_pid))

        connect_cost = 0
        # 确保真正连上了
        for _ in range(500):
            if getattr(client_sio, "true_connected"):
                break
            time.sleep(0.01)
            connect_cost += 0.01
        true_connected = getattr(client_sio, "true_connected")
        if not true_connected:
            logging.warning(f"client_sio: {client_sio.sid} "
                            f"is not true_connected")
        print(f"new client_sio, connect_cost: {connect_cost} seconds")
        return client_sio

    @classmethod
    @ignore_error
    def client_msg_proxy_broadcast(cls, wsm: WebsocketEvent,
                                   client_sio: Client = None,
                                   callback=None):
        if client_sio is None:
            client_sio = cls.get_context_client_sio()
        data = wsm.get_msg()
        logging.debug(f"[Websocket msg]: {data} "
                      f"true_connected: {getattr(client_sio, 'true_connected')}")

        with cls._EMIT_LOCK:
            client_sio.emit(event=cls.BROADCAST_EVENT, data=wsm.get_msg(),
                            namespace=cls.NAMESPACE, callback=callback)

    @classmethod
    @new_thread
    def client_msg_send(cls, wsm: WebsocketEvent,
                        client_sio: Client = None,
                        callback=None):
        if client_sio is None:
            client_sio = cls.get_context_client_sio()
        data = wsm.get_msg()
        logging.debug(f"[Websocket msg]: {data}")
        client_sio.emit(event=wsm.event, data=wsm.get_msg(),
                        namespace=cls.NAMESPACE, callback=callback)

    @classmethod
    @new_thread
    def disconnect_context_client_sio(cls):
        client_sio, pid = get_context_client_sio_data()
        if client_sio:
            client_sio.disconnect()

    @classmethod
    def bind_event(cls, event: WebsocketEvent, callback: Callable,
                   args=None, kwargs=None, domain="localhost"):
        client_sio: Client = cls.get_context_client_sio(domain=domain)
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}

        @client_sio.on(event.EVENT, namespace=cls.NAMESPACE)
        def bind_call(message):
            kwargs["message"] = message
            callback(*args, **kwargs)

    @classmethod
    def debug_notify(cls, msg):
        SportWebsocketClient.client_msg_proxy_broadcast(
            wsm=DebugLogEvent(data=dict(msg=msg)))
