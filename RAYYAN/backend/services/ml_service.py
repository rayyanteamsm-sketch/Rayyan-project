"""
خدمة نموذج الاستجابة: تُحمَّل مرة واحدة عند تشغيل الخادم.
إن فشل التحميل (مثلًا اختلاف إصدار scikit-learn) يُعاد تدريب النموذج محليًا بالإعدادات
المختارة المحفوظة في metrics.json وعلى نفس بيانات التدريب+التحقق، ويُعلَن ذلك في الإصدار.
"""
from __future__ import annotations

import json
import logging
import math
import threading
from datetime import date
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd

from backend.app.config import METRICS_PATH, MODEL_PATH
from backend.database.db import connect

log = logging.getLogger("rayyan.ml")
_lock = threading.Lock()
_bundle: dict[str, Any] | None = None
_status: dict[str, Any] = {"loaded": False, "source": None, "error": None}

FEATURE_AR = {
    "pre_vwc": "الرطوبة قبل الري", "planned_volume_l": "حجم الري المخطط", "planned_duration_min": "مدة الري المخططة",
    "root_depth_m": "عمق الجذور", "area_m2": "مساحة المنطقة", "forecast_rain_mm": "المطر المتوقع",
    "forecast_et0_mm": "التبخر-النتح المتوقع", "doy_sin": "الموسم (sin)", "doy_cos": "الموسم (cos)",
}


def _retrain_from_metrics() -> dict[str, Any]:
    from sklearn.ensemble import RandomForestRegressor
    m = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    feats, params, seed = m["features"], m["selection"]["best_params"], m["software"]["seed"]
    con = connect()
    try:
        df = pd.read_sql("""select f.*, t.delta_vwc, s.split, s.eligible from ml_features f
            join ml_targets t using(decision_id) join split_manifest s using(decision_id, zone_id)""", con)
    finally:
        con.close()
    df = df[(df.eligible.astype(str).isin(["1", "True", "true"])) & df.delta_vwc.notna() & df.split.isin(["train", "validation"])]
    model = RandomForestRegressor(random_state=seed, n_jobs=-1, **params).fit(df[feats], df.delta_vwc)
    model.set_params(n_jobs=1)
    return {"model": model, "features": feats, "version": m["model_version"] + "-retrained-local",
            "trained_at": None, "feature_ranges": m["feature_ranges"], "params": params, "seed": seed}


def load(force: bool = False) -> dict[str, Any]:
    global _bundle
    with _lock:
        if _bundle is not None and not force:
            return _bundle
        try:
            _bundle = joblib.load(MODEL_PATH)
            _status.update(loaded=True, source="joblib", error=None)
            _bundle["model"].set_params(n_jobs=1)  # أسرع لتنبؤات صف واحد في الـAPI
        except Exception as e:  # نسجل السبب ولا نخفيه
            log.warning("تعذر تحميل النموذج المحفوظ (%s)؛ إعادة تدريب محلية بالإعدادات المحفوظة", e)
            _bundle = _retrain_from_metrics()
            _status.update(loaded=True, source="retrained_local", error=str(e))
        return _bundle


def status() -> dict[str, Any]:
    b = _bundle or {}
    return {**_status, "version": b.get("version"), "features": b.get("features"), "params": b.get("params")}


def doy_features(d: date) -> tuple[float, float]:
    """نفس تعريف build_dataset.make_ml: يوم السنة على 365.25 من التقويم المحلي."""
    doy = d.timetuple().tm_yday
    return math.sin(2 * math.pi * doy / 365.25), math.cos(2 * math.pi * doy / 365.25)


def range_warnings(x: dict[str, float]) -> list[str]:
    b = load(); out = []
    for f, r in b["feature_ranges"].items():
        v = x.get(f)
        if v is None or f.startswith("doy"):
            continue
        if v < r["min"] - 1e-9 or v > r["max"] + 1e-9:
            out.append(f"{FEATURE_AR.get(f, f)} = {v:g} خارج نطاق بيانات التدريب [{r['min']:g}، {r['max']:g}]؛ التنبؤ استقراء غير موثوق.")
    if x.get("planned_volume_l") and x.get("planned_duration_min"):
        implied = x["planned_volume_l"] / x["planned_duration_min"]
        if abs(implied - 2.0) > 0.05:
            out.append(f"معدل {implied:.2f} لتر/دقيقة يختلف عن 2 لتر/دقيقة الثابت في كل بيانات التدريب؛ "
                       "النموذج لم يرَ هذا التركيب.")
    return out


def predict_many(xs: list[dict[str, float]]) -> list[float]:
    b = load()
    X = pd.DataFrame(xs)[b["features"]].astype(float)
    if X.isna().any().any():
        missing = [c for c in X.columns if X[c].isna().any()]
        raise ValueError(f"مدخلات مفقودة للنموذج: {missing}")
    return [float(v) for v in b["model"].predict(X)]


def build_features(pre_vwc: float, volume_l: float, duration_min: float, root_depth_m: float, area_m2: float,
                   rain_mm: Optional[float], et0_mm: Optional[float], d: date) -> dict[str, float]:
    s, c = doy_features(d)
    return {"pre_vwc": pre_vwc, "planned_volume_l": volume_l, "planned_duration_min": duration_min,
            "root_depth_m": root_depth_m, "area_m2": area_m2,
            "forecast_rain_mm": np.nan if rain_mm is None else rain_mm,
            "forecast_et0_mm": np.nan if et0_mm is None else et0_mm, "doy_sin": s, "doy_cos": c}


def predict_one(x: dict[str, float]) -> dict[str, Any]:
    d = predict_many([x])[0]
    return {"model_version": load()["version"], "delta_vwc": d, "post_vwc": x["pre_vwc"] + d, "warnings": range_warnings(x)}
