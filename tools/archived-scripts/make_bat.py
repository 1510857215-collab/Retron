# -*- coding: utf-8 -*-
"""把 启动.bat 重写为最稳版本：GBK 编码（中文 Windows 原生）+ ping 等待法（不依赖 timeout.exe）。"""
content = """@echo off
title hx 有机合成工作台
cd /d "%~dp0"
echo.
echo  hx 有机合成工作台 —— 正在启动...
echo.
echo  [1/2] 启动本地服务窗口...
start "hx 服务" "%~dp0tools\\venv\\Scripts\\python.exe" "%~dp0app\\server.py"
ping -n 4 127.0.0.1 >nul
echo  [2/2] 打开浏览器...
start "" "http://127.0.0.1:8765"
echo.
echo  启动完成，本窗口即将关闭。
echo  用完关闭【hx 服务】窗口即退出软件。
ping -n 6 127.0.0.1 >nul
exit
"""
p = r"C:/Users/zzl/Desktop/hx/启动.bat"
with open(p, "w", encoding="gbk", newline="\r\n") as f:
    f.write(content)
print("启动.bat 已重写：GBK 编码 + CRLF 换行")
