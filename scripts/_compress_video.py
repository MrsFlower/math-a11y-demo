# -*- coding: utf-8 -*-
"""百炼应用奖视频压缩：两遍编码精确控码率，音频降为 56k 单声道。"""
import glob
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

FF = r"C:\Users\15866\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
src = [p for p in glob.glob(os.path.join(HERE, "*.mp4")) if not os.path.basename(p).startswith("_")][0]
out = os.path.join(HERE, "_compressed.mp4")

DUR = 153.58
TARGET_MB = 19.0
total_k = int(TARGET_MB * 8 * 1024 / DUR / 1.024)  # kb/s
audio_k = 64
video_k = 1500  # 高于原片 1116k，尽量减少二代编码损失
print(f"target total {total_k} kb/s, video {video_k} kb/s, audio {audio_k} kb/s")

common = [FF, "-y", "-i", src, "-c:v", "libx264", "-preset", "slow",
          "-b:v", f"{video_k}k", "-maxrate", f"{video_k * 1.3}k",
          "-bufsize", f"{video_k * 2}k"]

p1 = subprocess.run(common + ["-pass", "1", "-an", "-f", "mp4", "NUL"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=HERE)
print("pass1 rc", p1.returncode)
if p1.returncode != 0:
    print(p1.stderr[-2000:]); sys.exit(1)

p2 = subprocess.run(common + ["-pass", "2", "-c:a", "aac", "-b:a", f"{audio_k}k",
                              "-ac", "1", "-movflags", "+faststart", out],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=HERE)
print("pass2 rc", p2.returncode)
if p2.returncode != 0:
    print(p2.stderr[-2000:]); sys.exit(1)

mb = os.path.getsize(out) / 1024 / 1024
print(f"compressed: {mb:.2f} MB")
