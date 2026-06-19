@echo off
REM RAG 系统启动脚本 - 自动设置代理
set HTTPS_PROXY=http://127.0.0.1:7897
set PYTHONIOENCODING=utf-8
python main.py %*
