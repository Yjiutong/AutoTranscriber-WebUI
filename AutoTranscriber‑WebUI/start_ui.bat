@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ======================================
echo      AutoTranscriber‑WebUI 启动器
echo ======================================
python main.py
echo.
echo 服务退出，按任意键关闭
pause >nul
