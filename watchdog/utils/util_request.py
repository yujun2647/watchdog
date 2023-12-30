"""
    接口请求相关的 工具方法
"""
import json
from flask import request


class RequestParser(object):
    @staticmethod
    def get_json_data():
        return json.loads(request.get_data(as_text=True))

    @staticmethod
    def get_form_data():
        return request.form.to_dict()

    @staticmethod
    def get_args():
        return request.args.to_dict()


DEFAULT_REQUEST_DATA_FUNC = RequestParser.get_json_data
CONTENT_TYPE_REQUEST_DATA_FUNC = {
    None: RequestParser.get_args,
    "application/x-www-form-urlencoded": RequestParser.get_form_data,
    "multipart/form-data": RequestParser.get_form_data,
    "application/json": RequestParser.get_json_data,
}


def get_content_type():
    content_type = request.headers.get("Content-Type", None)
    if content_type:
        content_type = content_type.split(";")[0]
    return content_type


def get_request_data() -> [dict, list]:
    """
        获取请求参数数据 (兼容多种参数传递方式)
    """
    content_type = get_content_type()
    get_data_func = CONTENT_TYPE_REQUEST_DATA_FUNC.get(
                                                    content_type,
                                                    DEFAULT_REQUEST_DATA_FUNC)
    return get_data_func()
