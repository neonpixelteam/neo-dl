@echo off
REM ساخت NEO-DL.exe  —  Build a single-file Windows exe
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name NEO-DL neo_dl.py
if errorlevel 1 (echo BUILD FAILED & pause & exit /b 1)
echo.
echo Built: dist\NEO-DL.exe
pause
