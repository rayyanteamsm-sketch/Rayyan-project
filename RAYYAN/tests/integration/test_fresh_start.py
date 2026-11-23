"""
اختبار تشغيل المشروع من البداية: نسخة نظيفة تحتوي الملف الأصلي والكود فقط — دون بيانات مجهزة ولا نماذج مدربة —
ثم: scripts/run.py --setup-only (تجهيز + تدريب + تحقق) ثم تشغيل الخادم وطلب توصية حقيقية.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
KEEP = ["backend", "ml/training", "ml/evaluation", "scripts", "frontend/dist", "image_processing", "requirements.txt", "pytest.ini"]


@pytest.mark.slow
def test_project_runs_from_scratch(tmp_path):
    proj = tmp_path / "RAYYAN"
    for rel in KEEP:
        src = ROOT / rel
        dst = proj / rel
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "output"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, dst)
    (proj / "data/raw").mkdir(parents=True)
    shutil.copy2(ROOT / "data/raw/original_upload.zip", proj / "data/raw/original_upload.zip")
    if (ROOT / "data/raw/RAYYAN_ML_Ready.xlsx").exists():
        shutil.copy2(ROOT / "data/raw/RAYYAN_ML_Ready.xlsx", proj / "data/raw/RAYYAN_ML_Ready.xlsx")
    assert not (proj / "data/database").exists() and not (proj / "ml/saved_models").exists()

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.pop("RAYYAN_DB", None)
    r = subprocess.run([sys.executable, "scripts/run.py", "--setup-only"], cwd=proj, env=env, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    for f in ["data/database/rayyan.sqlite", "ml/saved_models/response_model.joblib", "ml/saved_models/metrics.json",
              "ml/saved_models/MODEL_CARD.md", "ml/saved_models/decision_engine_validation.json", "data/processed/images/manifest.json"]:
        assert (proj / f).exists(), f
    if (ROOT / "data/raw/RAYYAN_ML_Ready.xlsx").exists():
        assert (proj / "ml/saved_models/v2/v2_model.joblib").exists() and (proj / "ml/saved_models/v2/MODEL_CARD_V2.md").exists()
        v2a = json.loads((proj / "ml/saved_models/v2/v2_metrics.json").read_text(encoding="utf-8"))
        v2b = json.loads((ROOT / "ml/saved_models/v2/v2_metrics.json").read_text(encoding="utf-8"))
        for a, b in zip(v2a["results"], v2b["results"]):
            assert a["model_id"] == b["model_id"] and a["rmse"] == pytest.approx(b["rmse"], rel=1e-9, abs=1e-12)
    v = json.loads((proj / "ml/saved_models/decision_engine_validation.json").read_text(encoding="utf-8"))
    assert v["action_matches"] == v["decisions_compared"] == 731
    m = json.loads((proj / "ml/saved_models/metrics.json").read_text(encoding="utf-8"))
    orig = json.loads((ROOT / "ml/saved_models/metrics.json").read_text(encoding="utf-8"))
    # إعادة الإنتاج حتى دقة الفاصلة العائمة (ترتيب الجمع في الحساب المتوازي قد يغير الخانة الأخيرة)
    assert len(m["results"]) == len(orig["results"])
    for a, b in zip(m["results"], orig["results"]):
        assert a["model_id"] == b["model_id"] and a["n"] == b["n"]
        for k in ("mae", "rmse", "r2"):
            assert a[k] == pytest.approx(b[k], rel=1e-9, abs=1e-12), (a["model_id"], k)
    assert m["selection"]["best_params"] == orig["selection"]["best_params"]

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    srv = subprocess.Popen([sys.executable, "-m", "backend.main"], cwd=proj, env={**env, "RAYYAN_PORT": str(port)},
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/health", timeout=1); break
            except Exception:
                time.sleep(0.2)
        body = json.dumps({"zone_id": "Z02", "decision_date": "2025-07-15", "pre_vwc": 0.098, "forecast_rain_mm": 0,
                           "forecast_et0_mm": 9.4, "forecast_temperature_c": 37}).encode()
        req = urllib.request.Request(base + "/api/irrigation/recommend", data=body, method="POST", headers={"Content-Type": "application/json"})
        res = json.loads(urllib.request.urlopen(req, timeout=30).read())
        assert res["decision"]["action"] == "IRRIGATE" and res["prediction"]["available"] and res["recommendation_id"] >= 1
        html = urllib.request.urlopen(base + "/").read()
        assert b'id="root"' in html
    finally:
        srv.terminate(); srv.wait(timeout=10)
