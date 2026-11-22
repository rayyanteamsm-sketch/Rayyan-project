"""
النموذج الثاني (RAYYAN v2، أربع مناطق): تحميل النموذج، القيم الافتراضية ليوم ومنطقة، التنبؤ، والنتائج.
مجموعة مستقلة عن نظام البرمودا؛ لا تمر عبر محرك القرار rule_v1.
"""
from __future__ import annotations

import json
import math
import threading
from typing import Any

import joblib
import pandas as pd

from backend.app.config import DATA_NOTICE, MODEL_DIR
from backend.database.db import connect, one, rows

V2_DIR = MODEL_DIR / "v2"
_lock = threading.Lock()
_bundle: dict[str, Any] | None = None
_status: dict[str, Any] = {"available": False, "error": None}


def available() -> bool:
    con = connect()
    try:
        return one(con, "select 1 x from sqlite_master where name='v2_ml_ready'") is not None and (V2_DIR / "v2_model.joblib").exists()
    finally:
        con.close()


def load() -> dict[str, Any] | None:
    global _bundle
    with _lock:
        if _bundle is None and (V2_DIR / "v2_model.joblib").exists():
            try:
                _bundle = joblib.load(V2_DIR / "v2_model.joblib")
                _bundle["model"].set_params(model__n_jobs=1)
                _status.update(available=True, error=None)
            except Exception as e:  # لا نخفي السبب
                _status.update(available=False, error=str(e))
        return _bundle


def status() -> dict[str, Any]:
    b = _bundle or {}
    return {**_status, "version": b.get("version")}


def metrics() -> dict[str, Any]:
    m = json.loads((V2_DIR / "v2_metrics.json").read_text(encoding="utf-8"))
    m.pop("feature_ranges", None)
    m["runtime"] = status()
    m["data_notice"] = DATA_NOTICE
    return m


def overview() -> dict[str, Any]:
    con = connect()
    try:
        zones = rows(con, "select * from v2_zones order by zone_id")
        counts = rows(con, """select temporal_split split, count(*) n, sum(target_after_6h_VWC_pct is null) missing_targets,
            min(feature_cutoff_at) first, max(feature_cutoff_at) last from v2_ml_ready group by temporal_split""")
        faults = rows(con, """select o.zone_id, o.simulated_fault_label label, count(*) n from v2_outcomes o group by 1, 2 order by 1, 2""")
        readme = rows(con, "select * from v2_readme")
        monthly = rows(con, """select m.zone_id, substr(m.feature_cutoff_at, 1, 7) month, avg(m.before_VWC_pct) before_vwc,
            avg(o.target_after_6h_VWC_pct) after_vwc, sum(m.planned_volume_L) planned_l, sum(o.actual_volume_L) actual_l
            from v2_ml_ready m join v2_outcomes o using(event_id) group by 1, 2 order by 2, 1""")
    finally:
        con.close()
    return {"zones": zones, "splits": counts, "faults": faults, "readme": readme, "monthly": monthly,
            "provenance": "SIMULATED (seed 42603)", "data_notice": DATA_NOTICE,
            "independence_note": "مجموعة مستقلة عن نظام البرمودا: لا ترتبط بقراراته أو أحداثه، ولا يغذيها محرك القرار."}


def defaults(zone_id: str, date: str) -> dict[str, Any]:
    """مدخلات النموذج كما سُجلت في الملف لهذه المنطقة واليوم (وقت القرار 06:00 UTC)."""
    b = load()
    con = connect()
    try:
        r = one(con, """select m.*, o.target_after_6h_VWC_pct actual, o.actual_volume_L, o.simulated_fault_label
            from v2_ml_ready m join v2_outcomes o using(event_id)
            where m.zone_id = ? and substr(m.feature_cutoff_at, 1, 10) = ?""", (zone_id, date))
        rng = one(con, "select min(substr(feature_cutoff_at,1,10)) a, max(substr(feature_cutoff_at,1,10)) b from v2_ml_ready")
    finally:
        con.close()
    if not r:
        raise KeyError(f"لا يوجد سجل للمنطقة {zone_id} في {date}؛ النطاق {rng['a']} — {rng['b']}")
    feats = b["features"] if b else []
    return {"event_id": r["event_id"], "zone_id": zone_id, "date": date, "temporal_split": r["temporal_split"],
            "inputs": {f: r[f] for f in feats}, "recorded_actual_vwc_pct": r["actual"],
            "recorded_actual_volume_l": r["actual_volume_L"], "simulated_fault_label": r["simulated_fault_label"],
            "field_capacity_pct": r["field_capacity_pct"], "wilting_pct": r["wilting_pct"]}


def predict(zone_id: str, date: str, overrides: dict[str, Any]) -> dict[str, Any]:
    b = load()
    if b is None:
        raise RuntimeError("نموذج v2 غير متاح؛ شغّلي ml/training/train_v2_model.py")
    base = defaults(zone_id, date)
    x = dict(base["inputs"])
    changed = {}
    for k, v in overrides.items():
        if k in x and v is not None and v != x[k]:
            changed[k] = {"from": x[k], "to": v}; x[k] = v
    if "before_VWC_pct" in overrides:
        x["before_missing"] = 1 if overrides["before_VWC_pct"] is None else 0
    if "planned_volume_L" in changed and "planned_duration_min" not in overrides:
        x["planned_duration_min"] = x["planned_volume_L"] / x["nominal_flow_L_min"] if x["nominal_flow_L_min"] else 0
    X = pd.DataFrame([x])[b["features"]]
    pred = float(b["model"].predict(X)[0])
    warnings = []
    for f, r in b["feature_ranges"].items():
        v = x.get(f)
        if v is not None and not (isinstance(v, float) and math.isnan(v)) and (v < r["min"] - 1e-9 or v > r["max"] + 1e-9):
            warnings.append(f"{f} = {v:g} خارج نطاق التدريب [{r['min']:g}، {r['max']:g}]؛ التنبؤ استقراء غير موثوق.")
    if x.get("before_missing") == 1:
        warnings.append("القراءة الحالية مفقودة؛ عوّضها النموذج بوسيط التدريب، فالتنبؤ أقل موثوقية.")
    return {"model_version": b["version"], "zone_id": zone_id, "date": date, "event_id": base["event_id"],
            "predicted_vwc_pct": pred, "before_vwc_pct": x.get("before_VWC_pct"), "field_capacity_pct": base["field_capacity_pct"],
            "wilting_pct": base["wilting_pct"], "changed_inputs": changed, "inputs_used": x, "warnings": warnings,
            "recorded_actual_vwc_pct": base["recorded_actual_vwc_pct"] if not changed else None,
            "recorded_note": None if not changed else "غُيّرت المدخلات؛ لا توجد قيمة مسجلة مقابلة لهذا السيناريو.",
            "data_notice": DATA_NOTICE}


def predictions(split: str) -> list[dict[str, Any]]:
    con = connect()
    try:
        return rows(con, """select p.*, m.feature_cutoff_at from app_v2_predictions p join v2_ml_ready m using(event_id)
            where p.split = ? order by m.feature_cutoff_at, p.zone_id""", (split,))
    finally:
        con.close()
