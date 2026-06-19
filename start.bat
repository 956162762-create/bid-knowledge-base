@echo off
chcp 65001 >nul
title 招投标知识库

echo ========================================
echo   招投标知识库 v3
echo ========================================
echo.
echo 正在启动服务...
echo.

cd /d D:\RAG\rag_system

REM 启动浏览器（等 3 秒让服务先起来）
start "" http://localhost:8080

REM 启动应用
python app.py --port 8080

pause
