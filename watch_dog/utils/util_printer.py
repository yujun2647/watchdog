import json
import pprint
from io import StringIO

pp = pprint.PrettyPrinter(indent=4, compact=True)


def pretty_print(obj):
    pp.pprint(obj)


def to_pretty_string(obj):
    string_io = StringIO()
    if isinstance(obj, str):
        # noinspection PyBroadException
        try:
            obj = json.loads(obj)
            return json.dumps(obj, indent=4, ensure_ascii=False)
        except Exception:
            return obj
    elif isinstance(obj, (list, dict)):
        return json.dumps(obj, indent=4, ensure_ascii=False)
    pprint.PrettyPrinter(stream=string_io).pprint(obj)
    return string_io.getvalue()


if __name__ == "__main__":
    import logging
    from central_log.logger_implanter import implant_logger
    from backend_configs.config import LoggerConfig
    implant_logger(LoggerConfig().configs)

    data = {
        "gpus": "0",
        "batch_size": 32,
        "det_model": "/app/models/epoch_12_del_calss.pth",
        "pos_model": "/app/models/pose_model_20200105.pth",
        "track_model": "/app/models/atom_default.pth",
        "deductionThreshold": 10,
        "output": "/app/data/output",
        "中文": "中文"
    }
    # pp.pprint(data)
    # pretty_print(data)
    logging.info(data)
    logging.info(to_pretty_string(data))
    logging.info(to_pretty_string(json.dumps(data)))
