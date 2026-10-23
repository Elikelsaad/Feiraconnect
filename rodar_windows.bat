@echo off
cd /d "%~dp0"
if not exist venv (python -m venv venv)
call venv\Scripts\activate
pip install -r requirements.txt
if not exist feiraconnect.db (python seed.py)
start http://127.0.0.1:5000
python run.py
pause
