import os
import av
from watch_dog.utils.util_log import time_cost_log


@time_cost_log
def to_h264_video(source_video_path, output_video_path):
    os.system(f"ffmpeg -i {source_video_path} -vcodec h264"
              f" {output_video_path}")


class H264Writer(object):
    def __init__(self, path, fps, bit_rate=1000000):
        self.container = av.open(path, mode='w')
        self.stream = self.container.add_stream('h264', rate=round(fps))
        self.stream.pix_fmt = 'yuv420p'
        self.stream.bit_rate = bit_rate
        self.is_open = True
        self.frame_num = 0

    def isOpened(self):
        return self.is_open

    def write(self, frame):
        # frame: [H, W, C]
        self.stream.width = frame.shape[1]
        self.stream.height = frame.shape[0]
        frame = av.VideoFrame.from_ndarray(frame, format='bgr24')
        self.container.mux(self.stream.encode(frame))
        self.frame_num += 1

    def release(self):
        self.container.mux(self.stream.encode())
        self.container.close()
        self.is_open = False


if __name__ == "__main__":
    t = H264Writer("test.mp4", 30)