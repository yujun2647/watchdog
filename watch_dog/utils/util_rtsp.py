from typing import Any

import av
import multiprocessing as mp
import cv2


class RTSPCapture(object):
    def __init__(self, rtsp_path: str):
        self.__rtsp_path = rtsp_path

        # other_options = {
        #     'rtsp_transport': "tcp",
        #     #'fflags': 'nobuffer',
        #     #'flags': 'low_delay',
        #     #'strict': 'experimental',
        # }
        other_options = {'buffer_size': '1024000',
                         'rtsp_transport': 'tcp',
                         'stimeout': '20000000',
                         'max_delay': '200000'
                         }

        # self._container = av.open(self.__rtsp_path, 'r',
        #                           options=other_options)
        self._container = av.open(self.__rtsp_path, 'r',
                                  format=None, options=other_options,
                                  metadata_errors="nostrict")

        # dicOption = {'buffer_size': '1024000', 'rtsp_transport': 'tcp',
        #              'stimeout': '20000000', 'max_delay': '200000'}
        # video = av.open("rtsp://viewer:vieweradmin@192.16.5.69:80/1", 'r',
        #                 format=None, options=dicOption,
        #                 metadata_errors='nostrict')
        # try:
        self.stream = self._container.streams.video[0]

        self._is_opened = mp.Value("d", 0)
        self._is_opened.value = 1

        self._video_width = mp.Value("d", 0)
        self._video_height = mp.Value("d", 0)

    def isOpened(self):
        return self._is_opened.value

    def set(self, *args, **kwargs):
        pass

    def get(self, key):
        if key == cv2.CAP_PROP_FPS:
            return self.stream.average_rate

        if key == cv2.CAP_PROP_FRAME_WIDTH:
            if self._video_width.value > 0:
                return int(self._video_width.value)
            grab, frame = self.read()
            if grab:
                self._video_height.value = frame.shape[0]
                self._video_width.value = frame.shape[1]
                return int(self._video_width.value)
            return 0

        if key == cv2.CAP_PROP_FRAME_HEIGHT:
            if self._video_height.value > 0:
                return int(self._video_height.value)
            grab, frame = self.read()
            if grab:
                self._video_height.value = frame.shape[0]
                self._video_width.value = frame.shape[1]
                return int(self._video_height.value)
            return 0

        return 0

    def read(self, width: int = None, height: int = None) -> (bool, Any):
        # noinspection PyBroadException
        # try:
        #     av_frame = next(self._container.decode(self.stream))
        #     cv_frame = av_frame.to_ndarray(
        #         format='bgr24', interpolation=0x4, width=width,
        #         height=height)  # BICUBIC
        #     if self._video_height.value != cv_frame.shape[0]:
        #         self._video_height.value = cv_frame.shape[0]
        #
        #     if self._video_width.value != cv_frame.shape[1]:
        #         self._video_width.value = cv_frame.shape[1]
        #     return True, cv_frame
        # except Exception as exp:
        #     return False, None
        try:
            # for packet in self._container.demux((self.stream,)):
            #
            #     for frame in packet.decode():
            #         if packet.stream.type == "video":
            #             cv_frame = frame.to_ndarray(format='bgr24')
            #             if self._video_height.value != cv_frame.shape[0]:
            #                 self._video_height.value = cv_frame.shape[0]
            #
            #             if self._video_width.value != cv_frame.shape[1]:
            #                 self._video_width.value = cv_frame.shape[1]
            #
            #             return True, cv_frame
            #         else:
            #             print(packet.stream.type)

            for packet in self._container.demux(video=0):
                if packet.stream.type == "video":
                    for frame in packet.decode():
                        cv_frame = frame.to_ndarray(format='bgr24')
                        if self._video_height.value != cv_frame.shape[0]:
                            self._video_height.value = cv_frame.shape[0]

                        if self._video_width.value != cv_frame.shape[1]:
                            self._video_width.value = cv_frame.shape[1]
                        return True, cv_frame
                else:
                    print(packet.stream.type)

        except Exception as exp:
            return False, None

        return False, None

    def release(self):
        self._container.close()

    @property
    def video_fps(self) -> int:
        return self.stream.average_rate

    def __del__(self):
        self.release()


if __name__ == "__main__":
    from watch_dog.utils.util_log import set_scripts_logging

    set_scripts_logging(__file__)
    address = "rtsp://admin:huang7758258@192.168.3.230:554/h264/ch1/main/av_stream"
    stream = RTSPCapture(address)

    while True:
        grab, frame = stream.read()
        # grab, frame = stream.read()
        if grab:
            cv2.imshow("frame", frame)
            cv2.waitKey(1)
