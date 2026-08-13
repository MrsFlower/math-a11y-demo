# -*- coding: utf-8 -*-
"""仅针对 _cdp_profile 测试浏览器：按命令行里的 user-data-dir 精准终止，
再按原参数重启（扩展随之重新加载）。绝不影响用户的主 Edge。"""
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

MARK = "_cdp_profile"
PROFILE = r"c:\Users\15866\Documents\codeheaven\小程序大赛\_cdp_profile"
EXT = r"c:\Users\15866\Documents\codeheaven\小程序大赛\math-a11y-assistant\extension"

ps = r"""
Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
  Where-Object { $_.CommandLine -and $_.CommandLine -like '*_cdp_profile*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force; "killed $($_.ProcessId)" }
"""
r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
print(r.stdout.strip() or "(没有匹配的进程)")
if r.stderr.strip():
    print("stderr:", r.stderr.strip()[:300])

time.sleep(2)
cmd = [
    "msedge",
    f"--user-data-dir={PROFILE}",
    "--remote-debugging-port=9333",
    "--no-first-run",
    "--no-default-browser-check",
    f"--load-extension={EXT}",
    "https://example.com",
]
subprocess.Popen(cmd)
print("已重启测试浏览器")
