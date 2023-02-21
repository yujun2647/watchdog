import logging
import os
import time
from typing import *
from ctypes import *
import multiprocessing as mp
from threading import Thread, Event as TEvent

from watch_dog.libs.hc_net_sdk.HCNetSDK import (
    NET_DVR_LOCAL_SDK_PATH, NET_DVR_DEVICEINFO_V30, NET_DVR_COMPRESSION_AUDIO,
    NET_DVR_AUDIOENC_INFO, NET_DVR_AUDIOENC_PROCESS_PARAM
)
from watch_dog.utils.util_path import get_hc_sdk_lib_path
from watch_dog.utils.util_thread import new_thread


class HCHetSdk(object):
    SDK_LIB_DIR = get_hc_sdk_lib_path()
    PtrPcmData = c_byte * 640
    PtrG711Data = c_byte * 320
    PtrG711PlayData = c_byte * 160

    AUDIO_ENCTYPE_G711TYPE_MAP = {
        1: 0,
        2: 1
    }

    def __init__(self, host: str, username: str, password: str, port=8000):
        self.host = create_string_buffer(host.encode())
        self.username = create_string_buffer(username.encode())
        self.password = create_string_buffer(password.encode())
        self.port = port
        os.chdir(self.SDK_LIB_DIR)
        self._hc_sdk = cdll.LoadLibrary("./libhcnetsdk.so")
        self._init_sdk()
        self._login_user_id, self._device_info = self._login()
        self._audio_type_info = self._get_device_audio_type_info()

        self._encoder = self._init_encoder()
        self._decoder = self._init_decoder()

        self.voice_handler = None

        self.playing_status = mp.Event()

        self._history_heartbeat_thread_stop_signal: Optional[List[TEvent]] = []
        self._keep_heartbeat_thread: Optional[Thread] = None

    def _stop_history_heartbeat_thread(self):
        for event in self._history_heartbeat_thread_stop_signal:
            event.set()

    @new_thread
    def _keep_heartbeats_async(self, stop_event: TEvent):
        while True:
            time.sleep(10)
            if stop_event.is_set():
                break
            if not self.playing_status.is_set():
                # self.play_audio_data()
                pass

    def init_voice_handler(self, callback: callable):
        voice_channel = 1
        voice_handler = self._hc_sdk.NET_DVR_StartVoiceCom_MR_V30(
            self._login_user_id, voice_channel, callback, None)
        if voice_handler != 0:
            raise ValueError("init voice_handler failed, error id: "
                             f"{self._hc_sdk.NET_DVR_GetLastError()}")
        self.voice_handler = voice_handler

        return voice_handler

    def _gen_one_encode_param(self) -> NET_DVR_AUDIOENC_PROCESS_PARAM:
        encode_param = NET_DVR_AUDIOENC_PROCESS_PARAM()
        encode_param.out_frame_size = 320
        encode_param.g711_type = self.AUDIO_ENCTYPE_G711TYPE_MAP[
            self._audio_type_info.byAudioEncType]
        return encode_param

    def _encode_g711_frame(self, audio_data) -> Tuple[
        PtrG711Data, NET_DVR_AUDIOENC_PROCESS_PARAM]:
        encode_param = self._gen_one_encode_param()

        ptr_pcm_data = self.PtrPcmData(*audio_data)
        ptr_g711_data = self.PtrG711Data()
        lp_ptr_pcm_data = pointer(ptr_pcm_data)
        lp_ptr_g711_data = pointer(ptr_g711_data)

        encode_param.in_buf = lp_ptr_pcm_data
        encode_param.out_buf = lp_ptr_g711_data

        # audio_data
        ret = self._hc_sdk.NET_DVR_EncodeG711Frame(
            self._encoder, byref(encode_param))

        if ret <= 0:
            raise ValueError(f"EncodeG711Frame failed, "
                             f"error id: {self._hc_sdk.NET_DVR_GetLastError()}")

        return ptr_g711_data, encode_param

    def play_audio_data(self, audio_data):
        ptr_g711_data, encode_param = self._encode_g711_frame(audio_data)

        # 改成生成器
        for i in range(0, encode_param.out_frame_size, 160):
            _end = i + 160
            if _end > encode_param.out_frame_size:
                _end = encode_param.out_frame_size
            ptr_g711_play_data = self.PtrG711PlayData(*ptr_g711_data[i:i + 160])
            lp_ptr_g711_play_data = pointer(ptr_g711_play_data)

            send_ret = self._hc_sdk.NET_DVR_VoiceComSendData(
                self.voice_handler, lp_ptr_g711_play_data, 160)

            if send_ret <= 0:
                raise ValueError(f"voice send failed, error id:"
                                 f" {self._hc_sdk.NET_DVR_GetLastError()}")

            time.sleep(20 / 1000.0)
            yield

    def _init_sdk(self):
        str_path = os.getcwd().encode('gbk')
        sdk_com_path = NET_DVR_LOCAL_SDK_PATH()
        sdk_com_path.sPath = str_path
        self._hc_sdk.NET_DVR_SetSDKInitCfg(2, byref(sdk_com_path))
        self._hc_sdk.NET_DVR_SetSDKInitCfg(3, create_string_buffer(
            str_path + b'\libcrypto.so.1.1'))
        self._hc_sdk.NET_DVR_SetSDKInitCfg(4, create_string_buffer(
            str_path + b'\libssl.so.1.1'))

        # 初始化DLL
        self._hc_sdk.NET_DVR_Init()
        # 启用SDK写日志
        self._hc_sdk.NET_DVR_SetLogToFile(3, bytes('.', encoding="gbk"), False)

    def _login(self):
        device_info = NET_DVR_DEVICEINFO_V30()
        login_user_id = self._hc_sdk.NET_DVR_Login_V30(self.host, self.port,
                                                       self.username,
                                                       self.password,
                                                       byref(device_info))
        if login_user_id < 0:
            raise ValueError(f"Login device fail, error code："
                             f" {self._hc_sdk.NET_DVR_GetLastError()}")

        return login_user_id, device_info

    def _get_device_audio_type_info(self):
        audio_type_info = NET_DVR_COMPRESSION_AUDIO()
        r = self._hc_sdk.NET_DVR_GetCurrentAudioCompress(self._login_user_id,
                                                         byref(audio_type_info))

        if r != 1:
            raise ValueError(f"get AudioCompress failed, "
                             f"error_id: {self._hc_sdk.NET_DVR_GetLastError()}")

        # 这里只实现对 1-G711-U, 2-G711-A 编码的编解码调用
        # if audio_type_info.byAudioEncType not in (1, 2):
        #     raise TypeError(f"not support byAudioEncType:"
        #                     f" {audio_type_info.byAudioEncType}")
        return audio_type_info

    def _init_encoder(self):

        audio_encode_info = NET_DVR_AUDIOENC_INFO()
        encoder = self._hc_sdk.NET_DVR_InitG711Encoder(
            byref(audio_encode_info))
        if encoder < 0:
            raise ValueError(f"InitG711Encoder failed, "
                             f"error code is: "
                             f"{self._hc_sdk.NET_DVR_GetLastError()}")
        return encoder

    def _init_decoder(self):
        decoder = self._hc_sdk.NET_DVR_InitG711Decoder()
        if decoder is None:
            raise ValueError(f"InitG711Encoder failed, "
                             f"error code is: "
                             f"{self._hc_sdk.NET_DVR_GetLastError()}")
        return decoder

    @CFUNCTYPE(c_bool, c_void_p, c_int, POINTER(c_char * 160), c_int, c_byte,
               c_void_p)
    def record_voice(self, lVoiceComHandle, pRecvDataBuffer, dwBufSize,
                     byAudioFlag, pUser):
        pass

    def __enter__(self):
        self._init_sdk()
        self._login_user_id, self._device_info = self._login()
        self._encoder = self._init_encoder()
        self._decoder = self._init_decoder()
        self._audio_type_info = self._get_device_audio_type_info()
        self.init_voice_handler(self.record_voice)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def stop_voice(self):
        r = self._hc_sdk.NET_DVR_ReleaseG711Encoder(self._encoder)
        if not r:
            print(f"[HC-SDK] ReleaseG711Encoder failed, error_id: "
                  f"{self._hc_sdk.NET_DVR_GetLastError()}")

        r = self._hc_sdk.NET_DVR_ReleaseG711Decoder(self._decoder)
        if not r:
            print(f"[HC-SDK] ReleaseG711Decoder failed, error_id: "
                  f"{self._hc_sdk.NET_DVR_GetLastError()}")

        r = self._hc_sdk.NET_DVR_StopVoiceCom(self.voice_handler)
        if not r:
            print(f"[HC-SDK] stop_voice failed, error_id: "
                  f"{self._hc_sdk.NET_DVR_GetLastError()}")

    def release(self):
        try:
            self.stop_voice()
            self._hc_sdk.NET_DVR_Logout(self._login_user_id)
            self._hc_sdk.NET_DVR_Cleanup()
        finally:
            time.sleep(0.1)
            print("hc_sdk released")

    def __del__(self):
        self.release()


if __name__ == "__main__":
    hc = HCHetSdk(host="192.168.3.230", username="admin",
                  password="huang7758258")

    for i in range(1000):
        print(f"play start {i}")
        print(f"play start {i}")
        print(f"play start {i}")
        with hc:
            print(f"play audio: {i}")
            print(f"play audio: {i}")
            print(f"play audio: {i}")
        print(f"play end {i}")
        print(f"play end {i}")
        print(f"play end {i}")

        print("--------------------------------------------------\n\n")
        #time.sleep(0.1)
