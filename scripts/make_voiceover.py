# -*- coding: utf-8 -*-
"""视频旁白合成：用系统 SAPI 中文语音（Microsoft Huihui）生成 WAV。

NVDA 本身不能导出音频文件，但如果 NVDA 用的是 Windows 中文语音（Huihui），
用它合成旁白可以和演示时的读屏声音保持同一音色。
产物：dist/video_voiceover/N1..N5.wav，对应《展示视频脚本.md》的旁白位。
"""
import os
from pathlib import Path

import win32com.client
from win32com.client import constants  # noqa: F401  (确保常量表加载)

OUT = Path(__file__).resolve().parent.parent / "dist" / "video_voiceover"

SEGMENTS = {
    "N1_开场旁白": "屏幕阅读器能把文字读得流畅，可一遇到公式，只能逐字符朗读，结构全部丢失。这就是视障学生每天面对的公式朗读黑洞。",
    "N2_转译旁白": "数学公式无障碍学习助手，选中公式按下快捷键，立刻转成一句完整的中文，读屏直接听懂。",
    "N3_讲解旁白": "不止读得出来，还要学得明白。AI 老师从五个角度讲解公式，还能把讲解合成语音直接听。",
    "N4_追问旁白": "没听懂？随时追问，就像有位老师坐在旁边。",
    "N5_结尾旁白": "数学公式无障碍学习助手，让每个公式都读得出来，学得明白。",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sapi = win32com.client.Dispatch("SAPI.SpVoice")
    # 选中 Huihui 中文语音；语速稍慢便于观众听清
    voices = sapi.GetVoices()
    for i in range(voices.Count):
        if "Huihui" in voices.Item(i).GetDescription():
            sapi.Voice = voices.Item(i)
            break
    sapi.Rate = -2
    for name, text in SEGMENTS.items():
        path = OUT / f"{name}.wav"
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(str(path), 3, False)  # SSFMCreateForWrite
        sapi.AudioOutputStream = stream
        sapi.Speak(text, 0)  # SVSFDefault 同步
        stream.Close()
        sapi.AudioOutputStream = None
        print(f"{name}.wav  {path.stat().st_size / 1024:.0f} KB")
    print("全部旁白已生成：", OUT)


if __name__ == "__main__":
    main()
