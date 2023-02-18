# # The route helpers were originally written by
# # Jeremy Kelley (http://github.com/nod).
from typing import *


class HttpRouteUrl(object):
    def __init__(self, url, handler, name):
        self.url = url
        self.handler = handler
        self.name = name


class WebsocketRouteUrl(object):
    def __init__(self, event_url, handler, name, namespace):
        self.url = event_url
        self.handler = handler
        self.name = name
        self.namespace = namespace


class Route(object):
    """
    decorates RequestHandlers and builds up a list of routables handlers

    Tech Notes (or 'What the *@# is really happening here?')
    --------------------------------------------------------

    Everytime @route('...') is called, we instantiate a new route object which
    saves off the passed in URI.  Then, since it's a decorator, the function is
    passed to the route.__call__ method as an argument.  We save a reference to
    that handler with our uri in our class level routes list then return that
    class to be instantiated as normal.

    Later, we can call the classmethod route.get_routes to return that list of
    tuples which can be handed directly to the tornado.web.Application
    instantiation.

    Example
    -------

    @route('/some/path')
    class SomeRequestHandler(RequestHandler):
        pass

    @route('/some/path', name='other')
    class SomeOtherRequestHandler(RequestHandler):
        pass

    my_routes = route.get_routes()
    """

    routes = []

    def __init__(self, uri, name=None):
        self._uri = uri
        self.name = name

    def __call__(self, _handler):
        """gets called when we class decorate"""
        name = self.name and self.name or _handler.__name__
        self.routes.append(HttpRouteUrl(url=self._uri, handler=_handler,
                                        name=name))
        return _handler

    @classmethod
    def get_routes(cls) -> List[HttpRouteUrl]:
        return cls.routes

    @classmethod
    def get_tornado_routes(cls):
        from tornado import web
        return [web.url(route.url, route.handler, name=route.name)
                for route in cls.routes]

    @classmethod
    def get_route_by_handler(cls, handler) -> [HttpRouteUrl, None]:
        for route in cls.routes:
            if route.handler == handler:
                return route
        return None


class WebsocketRoute(Route):
    web_socket_routes = []

    def __init__(self, uri, name=None, namespace=None):
        super().__init__(uri, name)
        self.namespace = namespace
        self.name = name

    def __call__(self, _handler):
        """gets called when we class decorate"""
        self.web_socket_routes.append(WebsocketRouteUrl(
            event_url=self._uri,
            handler=_handler,
            name=self.name,
            namespace=self.namespace,
        ))
        return _handler

    @classmethod
    def get_routes(cls) -> List[HttpRouteUrl]:
        return cls.web_socket_routes


def load_routes_to_flask(flask_app):
    routes = Route.get_routes()
    for route in routes:
        flask_app.add_url_rule(route.url,
                               view_func=route.handler.as_view(route.name))


def load_routes_to_sanic(sanic_app):
    routes = Route.get_routes()
    for route in routes:
        sanic_app.add_route(handler=route.handler.as_view(), uri=route.url)
