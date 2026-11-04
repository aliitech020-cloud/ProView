@echo off
REM Build a standalone Windows program: dist\ProView\ProView.exe
cd /d "%~dp0"
if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm ProView.spec
echo.
echo Done. Run dist\ProView\ProView.exe
pause
