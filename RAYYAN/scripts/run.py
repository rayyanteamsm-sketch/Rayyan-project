"""
مشغّل ريّان الموحّد — يستدعيه run.sh و run.bat.

    python scripts/run.py               تجهيز ما ينقص ثم تشغيل الخادم وفتح المتصفح
    python scripts/run.py --setup-only  تجهيز البيانات والنماذج والواجهة دون تشغيل
    python scripts/run.py --rebuild     إعادة كل شيء من الملف الأصلي (بيانات + تدريب)
    python scripts/run.py --test        تشغيل كل الاختبارات
    python scripts/run.py --port 9000   منفذ مختلف
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def step(title: str, args: list[str]):
    print(f"\n▶ {title}")
    t = time.time()
    subprocess.run([PY, *args], cwd=ROOT, check=True)
    print(f"  ✓ {time.time() - t:.0f} ث")


def setup(rebuild: bool):
    db = ROOT / "data/database/rayyan.sqlite"
    v2_missing = (ROOT / "data/raw/RAYYAN_ML_Ready.xlsx").exists() and db.exists() and \
        not __import__("sqlite3").connect(db).execute("select 1 from sqlite_master where name='v2_ml_ready'").fetchone()
    if rebuild or v2_missing or not db.exists() or not (ROOT / "data/processed/images/manifest.json").exists():
        step("تجهيز البيانات من الملف الأصلي", ["scripts/prepare_data.py", *(["--rebuild"] if rebuild else [])])
    else:
        step("التحقق من جداول التطبيق في قاعدة البيانات", ["-c", "import sys; sys.path.insert(0,'.'); from backend.database.db import ensure_schema; ensure_schema()"])
    sm = ROOT / "ml/saved_models"
    if rebuild or not (sm / "response_model.joblib").exists() or not (sm / "metrics.json").exists():
        step("تدريب نموذج استجابة الرطوبة", ["ml/training/train_response_model.py"])
    if rebuild or not (sm / "workbook_experiment.json").exists():
        step("التجربة الثانوية على مصنف التدريب", ["ml/training/train_workbook_experiment.py"])
    if rebuild or not (sm / "decision_engine_validation.json").exists():
        step("التحقق من محرك القرار مقابل قرارات المحاكي", ["ml/evaluation/validate_decision_engine.py"])
    if rebuild or not (sm / "MODEL_CARD.md").exists():
        step("توليد بطاقة النموذج", ["ml/evaluation/build_model_card.py"])
    v2 = ROOT / "ml/saved_models/v2"
    if (ROOT / "data/raw/RAYYAN_ML_Ready.xlsx").exists():
        if rebuild or not (v2 / "v2_model.joblib").exists():
            step("تدريب النموذج الثاني (مجموعة v2، أربع مناطق)", ["ml/training/train_v2_model.py"])
        if rebuild or not (v2 / "MODEL_CARD_V2.md").exists():
            step("توليد بطاقة النموذج الثاني", ["ml/evaluation/build_v2_model_card.py"])
        crops = ROOT / "ml/saved_models/crops"
        if rebuild or not (crops / "crops_model.joblib").exists() or not (crops / "crops_metrics.json").exists():
            step("تدريب نموذج المحاصيل الأربع (مقارنة النماذج وخطوط الأساس)", ["ml/training/train_crops_model.py"])
    if (ROOT / "image_processing/main.py").exists() and not (ROOT / "image_processing/output/report.csv").exists():
        step("معالجة الصور الميدانية كمصفوفات NumPy (image_processing)", ["image_processing/main.py"])
    if not (ROOT / "frontend/dist/index.html").exists():
        node = shutil.which("node")
        if not node:
            raise SystemExit("الواجهة غير مبنية ولا يوجد Node.js. ثبّتي Node 18+ ثم: cd frontend && npm install && npm run build")
        print("\n▶ بناء الواجهة")
        subprocess.run([node, "frontend/build.mjs"], cwd=ROOT, check=True)


def serve(port: int, open_browser: bool):
    os.environ.setdefault("RAYYAN_PORT", str(port))
    url = f"http://127.0.0.1:{port}"
    if open_browser and not os.environ.get("RAYYAN_NO_BROWSER"):
        threading.Timer(2.5, lambda: webbrowser.open(url)).start()
    subprocess.run([PY, "-m", "backend.main"], cwd=ROOT, env={**os.environ, "RAYYAN_PORT": str(port)})


def main():
    ap = argparse.ArgumentParser(description="تشغيل ريّان")
    ap.add_argument("--setup-only", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--port", type=int, default=int(os.environ.get("RAYYAN_PORT", 8000)))
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit("ريّان يحتاج Python 3.11 أو أحدث.")
    setup(a.rebuild)
    if a.test:
        raise SystemExit(subprocess.run([PY, "-m", "pytest", "tests", "-q"], cwd=ROOT).returncode)
    if a.setup_only:
        print("\n✓ التجهيز اكتمل."); return
    serve(a.port, not a.no_browser)


if __name__ == "__main__":
    main()
