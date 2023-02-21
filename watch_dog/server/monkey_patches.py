from werkzeug import serving
from werkzeug.serving import (BaseWSGIServer,
                              ForkingWSGIServer)

from watch_dog.server.custom_server import EnhanceThreadedWSGIServer


def make_server(
        host=None,
        port=None,
        app=None,
        threaded=False,
        processes=1,
        request_handler=None,
        passthrough_errors=False,
        ssl_context=None,
        fd=None,
):
    """Create a new server instance that is either threaded, or forks
    or just processes one request after another.
    """
    if threaded and processes > 1:
        raise ValueError(
            "cannot have a multithreaded and multi process server.")
    elif threaded:
        return EnhanceThreadedWSGIServer(
            host, port, app, request_handler, passthrough_errors, ssl_context,
            fd=fd
        )
    elif processes > 1:
        return ForkingWSGIServer(
            host,
            port,
            app,
            processes,
            request_handler,
            passthrough_errors,
            ssl_context,
            fd=fd,
        )
    else:
        return BaseWSGIServer(
            host, port, app, request_handler, passthrough_errors, ssl_context,
            fd=fd
        )


class MonkeyPatches(object):

    @classmethod
    def patch_all(cls, wsgi_server=True):
        if wsgi_server:
            serving.make_server = make_server
