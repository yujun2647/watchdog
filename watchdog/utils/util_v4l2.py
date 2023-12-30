import os
import logging
from glob import glob


def get_video_devices():
    usb_addresses = glob("/dev/video*")
    usb_addresses.sort(key=lambda k: int(k.replace("/dev/video", "")))
    return usb_addresses


def is_videocap_device(video_device):
    query_results = os.popen('v4l2-ctl -D -d ' + video_device).read().split('\n')
    device_capabilities = []
    for i, line in enumerate(query_results):
        if 'Device Caps' in line:
            for j in range(i+1, len(query_results)):
                if query_results[j].startswith('\t\t'):
                    device_capabilities.append(query_results[j].lstrip('\t\t'))
                else:
                    break
            break

    return True if 'Video Capture' in device_capabilities else False


def get_videocap_devices():
    video_devices = get_video_devices()
    videocap_devices = [vd for vd in video_devices if is_videocap_device(vd)]
    return videocap_devices


def get_videocap_device_ids():
    videocap_devices = get_videocap_devices()
    device_ids = [int(vd.replace("/dev/video", "")) for vd in videocap_devices]
    return device_ids


if __name__ == "__main__":
    dd = get_videocap_devices()
    print("debug")