@echo off
cd /d D:\RAG\rag_system
python app.py --port 8082 --open
if errorlevel 1 pause
