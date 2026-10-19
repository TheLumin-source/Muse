@echo off
rem Muse - local visual board. Opens a desktop window; add --browser for a browser tab.
rem
rem pythonw.exe rather than python.exe so no console window sits behind the app.
rem Set MUSE_PYTHON to pick a specific interpreter; otherwise the newest Python
rem under the per-user install location is used, then whatever is on PATH. Bare
rem "python" is deliberately not trusted: on a default Windows it resolves to the
rem Microsoft Store stub, which only prints an error.
setlocal
cd /d "%~dp0"

set "PY=%MUSE_PYTHON%"
if not defined PY (
    for /f "delims=" %%P in ('dir /b /o-n "%LOCALAPPDATA%\Programs\Python\Python3*" 2^>nul') do (
        if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\%%P\pythonw.exe" (
            set "PY=%LOCALAPPDATA%\Programs\Python\%%P\pythonw.exe"
        )
    )
)
if not defined PY (
    for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do if not defined PY set "PY=%%P"
)
if not defined PY (
    echo Muse: no Python found. Install Python 3.10 or newer, or set MUSE_PYTHON.
    pause
    exit /b 1
)

start "" "%PY%" run.py %*
