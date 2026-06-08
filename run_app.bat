@echo off
cd /d "%~dp0"
set "ANACONDA_PY=%USERPROFILE%\anaconda3\python.exe"
if exist "%ANACONDA_PY%" (
  "%ANACONDA_PY%" wxchat_desktop.py
  pause
  exit /b
)

where python >nul 2>nul
if %errorlevel%==0 (
  python wxchat_desktop.py
) else (
  py wxchat_desktop.py
)
pause
