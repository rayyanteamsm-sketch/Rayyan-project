@echo off
REM RAYYAN launcher for Windows (kept ASCII-only on purpose: cmd.exe misreads UTF-8 batch files).
REM   run.bat                 setup what is missing, start the server, open the browser
REM   run.bat --test          run all tests
REM   run.bat --rebuild       rebuild data + retrain all models from the original files
REM   run.bat --port 9000 --no-browser
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM Pick a Python 3.11+ that really runs ("python" may be the Microsoft Store stub, so try "py -3" first).
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul && set "PY=python"
if not defined PY (
  echo [RAYYAN] Python 3.11+ was not found. Install it from https://www.python.org/downloads/ and run again.
  exit /b 1
)

REM Use the installed libraries if present; otherwise create .venv and install requirements.txt there.
%PY% -c "import fastapi, starlette, uvicorn, pydantic, sklearn, pandas, joblib, PIL, openpyxl" >nul 2>nul
if not errorlevel 1 goto run
if not exist .venv\Scripts\python.exe (
  echo [RAYYAN] Creating virtual environment .venv ...
  %PY% -m venv .venv || exit /b 1
)
set "PY=.venv\Scripts\python.exe"
%PY% -c "import fastapi, sklearn, pandas, PIL, openpyxl" >nul 2>nul
if not errorlevel 1 goto run
echo [RAYYAN] Installing requirements into .venv ...
%PY% -m pip install --upgrade pip >nul
if "%1"=="--test" (%PY% -m pip install -r requirements-dev.txt) else (%PY% -m pip install -r requirements.txt)
if errorlevel 1 exit /b 1

:run
%PY% scripts\run.py %*
endlocal
