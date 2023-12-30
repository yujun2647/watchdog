import os
import av
from watchdog.utils.util_log import time_cost_log


@time_cost_log
def to_h264_video(source_video_path, output_video_path):
    os.system(f"ffmpeg -i {source_video_path} -vcodec h264"
              f" {output_video_path}")


class H264Writer(object):
    def __init__(self, path, fps, bit_rate=1000000):
        self.container = av.open(path, "w", "mp4")
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
    import cv2
    from tqdm import tqdm
    from io import StringIO, BytesIO
    from av.container import OutputContainer
    from av.codec import CodecContext
    from threading import Thread

    video_buffer = BytesIO()
    writer = H264Writer(video_buffer, fps=30)
    stream = cv2.VideoCapture(0)

    _, frame = stream.read()
    code_ctx = CodecContext.create("h264", "w")
    packets = code_ctx.parse(frame)
    for i, packet in enumerate(packets):
        frames = code_ctx.decode(packet)
        # if frames:
        #     return frames[0].to_image()

    while True:
        t = video_buffer.getvalue()
        print(len(t))

    video_buffer.close()
    writer.release()
    #
    # # the x.mp4 has the same content as the some_byte_file
    # #container = av.open(some_bytesio_object)
    # container = av.open(video_buffer, 'wb', 'mp4')
    # stream = container.add_stream('h264', rate=round(30))
    # stream.pix_fmt = 'yuv420p'
    # stream.bit_rate = 1000000
    # stream.width = frame.shape[1]
    # stream.height = frame.shape[0]
    # frame2 = av.VideoFrame.from_ndarray(frame, format='bgr24')
    # container.mux(stream.encode(frame2))
    #
    # t = video_buffer.getbuffer()
    # print(
    #     container.streams.video)  # <av.VideoStream #? h264, yuv420p 1280x720 at 0x7eff2ac89168>, ? means the result can be random, like 0, 1054153136, -649221856.
    # for frame in container.decode(video=0):
    #     frame.to_image().save('frame-{}.jpg'.format(frame.index))
