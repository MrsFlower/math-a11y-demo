@echo off
chcp 65001 >nul
title 数学公式无障碍学习助手 - 理解服务
cd /d %~dp0
echo ============================================
echo  正在启动理解服务 http://127.0.0.1:8321
echo  请保持此窗口开着，关掉窗口服务就停了。
echo ============================================
python -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8321
echo.
echo 服务已退出。如果是闪退，请确认已安装依赖（pip install fastapi uvicorn 等）。
pause
