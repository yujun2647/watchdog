import os

import numpy as np
import cv2

from watch_dog.utils.util_log import time_cost_log
from watch_dog.services.path_service import get_static_filepath


class CarDetector(object):
    # CAR_CASCADE = cv2.CascadeClassifier(get_static_filepath("cars.xml"))
    CAR_CASCADE = cv2.CascadeClassifier(
        "/home/walkerjun/myPythonCodes/watchDogCv/watch-dog-cv-backend/train/cascade/cascade.xml")

    @classmethod
    @time_cost_log
    def detect_cars(cls, frame: np.ndarray, mark_cars=True):
        # convert to gray scale of each frames
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Detects cars of different sizes in the input image
        # cars = cls.CAR_CASCADE.detectMultiScale(gray, 1.1, 200)
        cars = cls.CAR_CASCADE.detectMultiScale(gray, 1.1, 500)

        if mark_cars:
            for (x, y, w, h) in cars:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)

        return cars, frame


if __name__ == "__main__":
    from watch_dog.utils.util_log import set_scripts_logging
    from watch_dog.utils.util_camera import MultiprocessVideoCapture

    set_scripts_logging(__file__)
    address = ""

    foldles = ""
    for filename in os.listdir(foldles):
        filepath = os.path.join(foldles, filename)
        image = cv2.imread(filepath)
        cars, frame = CarDetector.detect_cars(image)
        cv2.imshow('video2', frame)
        cv2.waitKey(0)

    mvc = MultiprocessVideoCapture()
    mvc.register_camera(address)
    # capture frames from a video
    # cap = cv2.VideoCapture(address)

    camera = mvc.get_camera(address)

    while True:
        # grab, _frame = cap.read()
        # if not grab:
        #     break

        frame_box = camera.store_queue.get(timeout=5)
        cars, marked_frame = CarDetector.detect_cars(frame_box.frame)

        cv2.imshow('video2', marked_frame)
        cv2.waitKey(0)

        # # Wait for Esc key to stop
        # if cv2.waitKey(33) == 27:
        #     break

    cv2.destroyAllWindows()
