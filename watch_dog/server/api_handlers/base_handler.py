import json
from typing import *
from abc import abstractmethod

from urllib import parse
from flask import request, make_response
from flask.views import MethodView

from watch_dog.utils.util_request import get_request_data
from watch_dog.utils.util_router import Route, HttpRouteUrl
from watch_dog.utils.util_path import join_ensure_exist, get_extensions


class _ArgDefaultMarker:
    pass


_ARG_DEFAULT = _ArgDefaultMarker()


# noinspection PyBroadException
class BaseHandler(MethodView):
    # 上传限制的文件扩展名
    UPLOAD_ALLOW_EXTENSIONS = []

    def __init__(self, *args, **kwargs):
        self.request = request
        self.request_data = get_request_data()
        self.upload_allow_extensions = {ext.lower(): 1 for ext
                                        in self.UPLOAD_ALLOW_EXTENSIONS}

    @abstractmethod
    def get(self, *args, **kwargs):
        pass

    def post(self):
        pass

    def prepare(self):
        """
        Called at the beginning of a request before  `get`/`post`/etc.
        """
        pass

    @classmethod
    def get_response(cls, data=None):
        return make_response(dict(data=data, status="Ok"), 200)

    @classmethod
    def make_ok_response(cls, result):
        rsp = cls.get_response(data=result)
        rsp.headers['Content-Type'] = 'application/json'
        rsp.headers['Access-Control-Allow-Origin'] = "*"  # 设置允许跨域
        return rsp

    def dispatch_request(self, *args, **kwargs):
        try:
            self.prepare()
            result = super().dispatch_request(*args, **kwargs)
            self.on_finish()
            return self.make_ok_response(result)
        except Exception as exp:
            return self.handle_exception(exp)

    def on_finish(self) -> None:
        """Called after the end of a request.
        """
        pass

    def handle_exception(self, exp) -> None:
        # business-logger-web 已经代理了异常处理，这里不用再处理了
        raise exp

    def get_header(self, name: str, default=None):
        return self.request.headers.get(name, default)

    def get_argument(
            self, name: str,
            default: Optional[object] = _ARG_DEFAULT,
            missing_error_msg=None,
            value_processor: Optional[Callable] = None) -> Union[Any]:
        """
        :param name: 参数名
        :param default: 参数缺失时，使用的默认值，若不提供，则返回异常
        :param missing_error_msg: 参数缺失时，返回的错误信息
        :param value_processor: 对参数值进行包装处理的函数，如转为 int
        :return:
        """

        def _process_value(value):
            return value if not value_processor else value_processor(value)

        if name in self.request_data:
            data = self.request_data.get(name)
            return _process_value(data)
        elif not isinstance(default, _ArgDefaultMarker):
            return _process_value(default)
        else:
            if not missing_error_msg:
                missing_error_msg = f"Missing argument name: {name}"
            raise AttributeError(missing_error_msg)

    def is_allow_extension(self, filename: str):
        extension = get_extensions(filename)
        return extension.lower() in self.upload_allow_extensions

    def handle_upload(self, upload_name, save_dir, save_filename=None):
        if upload_name not in request.files:
            raise AttributeError(f"Missing upload name: {upload_name}")

        file = request.files.get(upload_name)
        if not self.is_allow_extension(file.filename):
            raise TypeError(f"Not allow extension: {file.filename}")

        if not save_filename:
            save_filename = file.filename
        else:
            ext = get_extensions(file.filename)
            save_filename += f".{ext}"
        save_path = join_ensure_exist(save_dir, save_filename)
        file.save(save_path)
        return save_path

    @staticmethod
    def unquote_url(url):
        return parse.unquote(url)

    @classmethod
    def get_route(cls):
        route: "HttpRouteUrl" = Route.get_route_by_handler(cls)
        return route

    @classmethod
    def get_route_url(cls):
        route: "HttpRouteUrl" = cls.get_route()
        return route.url if route else None
