@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Ambiente virtual nao encontrado. Criando...
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"

if exist "requirements.txt" (
    pip install -r requirements.txt
)

python bot.py
pause
