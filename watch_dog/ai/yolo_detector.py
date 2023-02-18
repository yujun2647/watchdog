import os.path
import numpy as np

from cv2 import cv2
from typing import *

from watch_dog.models.detect_info import DetectInfo
from watch_dog.utils.util_log import time_cost_log_with_desc
from watch_dog.utils.util_camera import FrameBox

DIR_PATH = os.path.dirname(__file__)


class YoloDetector(object):
    DEFAULT_MODEL_DATA_PATH = os.path.join(
        DIR_PATH, "object_detect/model_data")
    DEFAULT_CONFIG_PATH = os.path.join(
        DEFAULT_MODEL_DATA_PATH,
        "ssd_mobilenet_v3_large_coco_2020_01_14.pbtxt")

    DEFAULT_MODEL_PATH = os.path.join(DEFAULT_MODEL_DATA_PATH,
                                      "frozen_inference_graph.pb")
    DEFAULT_CLASS_PATH = os.path.join(DEFAULT_MODEL_DATA_PATH, "coco.names")

    def __init__(self, model_path=None, config_path=None, class_path=None):
        self.model_path = model_path if model_path else self.DEFAULT_MODEL_PATH
        self.config_path = (config_path if config_path
                            else self.DEFAULT_CONFIG_PATH)
        self.class_path = class_path if class_path else self.DEFAULT_CLASS_PATH
        self.net = cv2.dnn_DetectionModel(self.model_path, self.config_path)
        self.net.setInputSize(320, 320)
        self.net.setInputScale(1.0 / 127.5)
        self.net.setInputMean((127.5, 127.5, 127.5))
        self.net.setInputSwapRB(True)
        self.classes_list: Optional[List[str]] = None
        self.color_list: Optional[List[str]] = None

        self.init_classes()

    def init_classes(self):
        with open(self.class_path, "r") as fp:
            self.classes_list = fp.readlines()

        self.classes_list.insert(0, "__Background__")
        self.color_list = np.random.uniform(low=0, high=255,
                                            size=(len(self.classes_list), 3))

    #@time_cost_log_with_desc(min_cost=35)
    def detect(self, frame_box: FrameBox) -> List[DetectInfo]:
        frame = frame_box.frame
        class_label_ids, confidences, bboxes = self.net.detect(
            frame, confThreshold=0.5)
        bboxes = list(bboxes)
        confidences = list(np.array(confidences).reshape(1, -1)[0])
        confidences = list(map(float, confidences))

        bboxes_idx = cv2.dnn.NMSBoxes(bboxes, confidences, score_threshold=0.5,
                                      nms_threshold=0.2)

        detect_infos = []
        if len(bboxes_idx) != 0:
            for i in range(len(bboxes_idx)):
                j = np.squeeze(bboxes_idx[i])
                bbox = bboxes[j]
                class_confidence = confidences[j]
                class_label_id = np.squeeze(class_label_ids[j])
                class_label = self.classes_list[class_label_id]
                class_label = class_label.replace("\n", "")
                class_color = [int(c) for c in self.color_list[class_label_id]]
                x, y, w, h = bbox
                # if w * h < 5000:
                #     continue
                detect_infos.append(DetectInfo(
                    frame_id=frame_box.frame_id,
                    fps=frame_box.fps,
                    label=class_label,
                    bbox=(x, y, w, h),
                    confidence=class_confidence,
                    suggest_color=class_color
                ))
        return detect_infos

    def landmarks(self, frame: np.ndarray, detect_infos: List[DetectInfo]):
        for detect_info in detect_infos:
            class_color = detect_info.suggest_color
            display_text = (f"{detect_info.label}: "
                            f"{round(detect_info.confidence, 4)}")
            x, y, w, h = detect_info.bbox
            text_font = int(w * 0.005)
            text_font = max(1, text_font)
            cv2.rectangle(frame, (x, y), (x + w, y + h), class_color, 1)
            cv2.putText(frame, display_text, (x + 5, y + text_font * 15),
                        cv2.FONT_HERSHEY_PLAIN, text_font,
                        class_color, text_font + 1)

            line_width = int(w * 0.2)

            cv2.line(frame, (x, y), (x + line_width, y), class_color, 5)
            cv2.line(frame, (x + w, y), (x + w - line_width, y),
                     class_color, 5)

            cv2.line(frame, (x, y), (x, y + line_width), class_color, 5)
            cv2.line(frame, (x + w, y), (x + w, y + line_width),
                     class_color, 5)

            cv2.line(frame, (x, y + h), (x + line_width, y + h),
                     class_color, 5)
            cv2.line(frame, (x + w, y + h), (x + w - line_width, y + h),
                     class_color, 5)

            cv2.line(frame, (x, y + h), (x, y - line_width + h),
                     class_color, 5)
            cv2.line(frame, (x + w, y + h), (x + w, y - line_width + h),
                     class_color, 5)

        return frame

    def detect_landmarks(self, frame_box: FrameBox) \
            -> Tuple[np.ndarray, List[DetectInfo]]:
        detect_infos = self.detect(frame_box)
        marked_frame = self.landmarks(frame_box.frame, detect_infos)
        return frame_box.frame, detect_infos


if __name__ == "__main__":
    from watch_dog.utils.util_log import set_scripts_logging
    from watch_dog.utils.util_camera import MultiprocessVideoCapture

    set_scripts_logging(__file__)
    address = "/home/walkerjun/myPythonCodes/watchDogCv/watch-dog-cv-backend/watch_dog/static/video.avi"

    address = "/home/walkerjun/myPythonCodes/watchDogCv/watch-dog-cv-backend/watch_dog/utils/test_night.mp4"
    address = "/home/walkerjun/myPythonCodes/watchDogCv/watch-dog-cv-backend/watch_dog/utils/test_own.mp4"
    address = "rtsp://admin:huang7758258@192.168.3.230:554/h265/ch1/main/av_stream"
    address = 0

    detector = YoloDetector()

    mvc = MultiprocessVideoCapture()

    set_params = {
        cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*"MJPG"),
        cv2.CAP_PROP_FRAME_WIDTH: 1920,
        cv2.CAP_PROP_FRAME_HEIGHT: 1080,
        cv2.CAP_PROP_FPS: 30,
        cv2.CAP_PROP_AUTO_EXPOSURE: 3,  # 曝光模式设置， 1：手动； 3: 自动
        cv2.CAP_PROP_EXPOSURE: 25,  # 曝光为手动模式时设置的曝光值， 若为自动，则这个值无效
    }
    mvc.register_camera(address, set_params=set_params)

    camera = mvc.get_camera(address)

    while True:
        frame_box = camera.store_queue.get(timeout=15)
        marked_frame, detect_infos = detector.detect_landmarks(frame_box)

        # print(f"{marked_frame.shape}")
        cv2.imshow('video2', marked_frame)
        cv2.waitKey(1)

    cv2.destroyAllWindows()
