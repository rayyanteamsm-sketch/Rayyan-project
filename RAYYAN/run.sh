#!/usr/bin/env bash
# تشغيل ريّان على Mac / Linux:  ./run.sh   |  ./run.sh --test  |  ./run.sh --rebuild
set -e
cd "$(dirname "$0")"
PY=python3
command -v $PY >/dev/null 2>&1 || PY=python
if ! $PY -c "import fastapi, starlette, uvicorn, pydantic, sklearn, pandas, joblib, PIL, openpyxl" >/dev/null 2>&1; then
  echo "▶ تثبيت المتطلبات في بيئة افتراضية .venv"
  [ -d .venv ] || $PY -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  PY=python
  $PY -m pip install --upgrade pip >/dev/null
  if [ "$1" = "--test" ]; then $PY -m pip install -r requirements-dev.txt; else $PY -m pip install -r requirements.txt; fi
fi
exec $PY scripts/run.py "$@"
