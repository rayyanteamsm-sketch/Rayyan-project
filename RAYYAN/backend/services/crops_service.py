"""
خدمة المحاصيل الأربع (نخيل، برسيم، خضار، نجيل) — مجموعة v2 المستقلة عن نظام البرمودا.

القرار والكمية: معادلات FAO-56 الفصل 8 بقيم المنطقة من الملف (FC، WP، عمق الجذور، المساحة، الكفاءة، التدفق، Kc)
ونسبة p من FAO-56 الجدول 22. التنبؤ: نموذج المحاصيل (ml/saved_models/crops) للرطوبة بعد 6 ساعات.
لا توجد قواعد قرار موثقة في الملف لهذه المجموعة؛ القواعد هنا معادلات FAO-56 المنشورة، ومعروضة صراحة للمستخدم.
"""
from __future__ import annotations

import json
import math
import threading
from typing import Any

import joblib
import numpy as np
import pandas as pd

from backend.app.config import CROPS_MODEL_DIR, DATA_NOTICE
from backend.database.db import connect, dumps, one, rows, session, utcnow
from backend.services.crops_lib import FAO56_P, fao56, water_balance_6h

_lock = threading.Lock()
_bundle: dict[str, Any] | None = None
_status: dict[str, Any] = {"loaded": False, "error": None}
OVERRIDABLE = ("before_VWC_pct", "et0_forecast_24h_mm", "rain_forecast_24h_mm", "air_temp_observed_C", "humidity_observed_pct")
DECISION_UTC, DECISION_LOCAL = "06:00 UTC", "09:00 بتوقيت السعودية"


# ------------------------------------------------------------------ تحميل النموذج
def load() -> dict[str, Any] | None:
    global _bundle
    with _lock:
        if _bundle is None and (CROPS_MODEL_DIR / "crops_model.joblib").exists():
            try:
                b = joblib.load(CROPS_MODEL_DIR / "crops_model.joblib")
                est = b["model"]
                inner = getattr(est, "estimator_", est)
                try:
                    inner.set_params(model__n_jobs=1)  # تنبؤ سريع لصف واحد
                except ValueError:
                    pass
                _bundle = b
                _status.update(loaded=True, error=None)
            except Exception as e:  # لا نخفي السبب
                _status.update(loaded=False, error=str(e))
        return _bundle


def status() -> dict[str, Any]:
    b = _bundle or {}
    return {**_status, "version": b.get("version"), "family": b.get("family"), "target_mode": b.get("target_mode"),
            "trained_at": b.get("trained_at")}


def available() -> bool:
    con = connect()
    try:
        has = one(con, "select 1 x from sqlite_master where name='v2_ml_ready'") is not None
    finally:
        con.close()
    return has and load() is not None


def metrics() -> dict[str, Any]:
    m = json.loads((CROPS_MODEL_DIR / "crops_metrics.json").read_text(encoding="utf-8"))
    m.pop("feature_ranges", None)
    m["runtime"] = status()
    m["data_notice"] = DATA_NOTICE
    return m


# ------------------------------------------------------------------ المناطق
def date_range() -> dict[str, str]:
    con = connect()
    try:
        r = one(con, "select min(substr(feature_cutoff_at,1,10)) a, max(substr(feature_cutoff_at,1,10)) b from v2_ml_ready")
    finally:
        con.close()
    return {"min": r["a"], "max": r["b"]}


def zones() -> list[dict[str, Any]]:
    b = load() or {}
    con = connect()
    try:
        zs = rows(con, "select * from v2_zones order by zone_id")
    finally:
        con.close()
    out = []
    for z in zs:
        p, src = FAO56_P.get(z["crop"], (0.5, "افتراضي 0.5"))
        f = fao56(z["field_capacity_pct"], z["wilting_pct"], z["root_depth_m"], None, None, z["kc_assumed"], p)
        out.append({**z, "p_table": p, "p_source": src, "taw_mm": f["taw_mm"],
                    "training_volume_range_l": (b.get("zone_ranges", {}).get(z["zone_id"], {}) or {}).get("planned_volume_L"),
                    "model": "crops", "dataset": "v2 (RAYYAN_ML_Ready.xlsx)"})
    return out


def _zone(zone_id: str) -> dict[str, Any]:
    for z in zones():
        if z["zone_id"] == zone_id:
            return z
    raise KeyError(f"لا توجد منطقة {zone_id}")


def day_record(zone_id: str, date: str) -> dict[str, Any]:
    con = connect()
    try:
        r = one(con, """select m.*, o.target_after_6h_VWC_pct recorded_after_6h, o.actual_volume_L recorded_actual_volume_l,
            o.simulated_fault_label from v2_ml_ready m join v2_outcomes o using(event_id)
            where m.zone_id = ? and substr(m.feature_cutoff_at, 1, 10) = ?""", (zone_id, date))
    finally:
        con.close()
    if not r:
        rng = date_range()
        raise KeyError(f"لا يوجد سجل للمنطقة {zone_id} في {date}؛ النطاق المتاح {rng['min']} — {rng['max']}")
    return r


# ------------------------------------------------------------------ التنبؤ
def _predict_many(xs: list[dict[str, Any]]) -> np.ndarray:
    b = load()
    if b is None:
        raise RuntimeError("نموذج المحاصيل غير متاح؛ شغّلي ml/training/train_crops_model.py")
    return b["model"].predict(pd.DataFrame(xs)[b["features"]])


def _with_volume(x: dict[str, Any], volume_l: float) -> dict[str, Any]:
    y = dict(x)
    y["planned_volume_L"] = float(volume_l)
    y["planned_duration_min"] = float(volume_l) / x["nominal_flow_L_min"] if x["nominal_flow_L_min"] else 0.0
    return y


def _range_warnings(x: dict[str, Any]) -> list[str]:
    b = load() or {}
    out = []
    for f, r in (b.get("feature_ranges") or {}).items():
        v = x.get(f)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        if v < r["min"] - 1e-9 or v > r["max"] + 1e-9:
            out.append(f"{f} = {v:,.4g} خارج نطاق التدريب [{r['min']:,.4g}، {r['max']:,.4g}]؛ التنبؤ استقراء غير موثوق.")
    return out


def build_inputs(zone_id: str, date: str, overrides: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    rec = day_record(zone_id, date)
    b = load()
    feats = b["features"] if b else []
    x = {f: rec[f] for f in feats}
    changed = {}
    for k in OVERRIDABLE:
        if k in overrides and overrides[k] is not None and overrides[k] != x.get(k):
            changed[k] = {"from": x.get(k), "to": overrides[k]}
            x[k] = overrides[k]
    if overrides.get("sensor_missing"):
        changed["before_VWC_pct"] = {"from": x.get("before_VWC_pct"), "to": None}
        x["before_VWC_pct"] = None
    x["before_missing"] = 1 if x.get("before_VWC_pct") is None else 0
    return rec, x, changed


def response_curve(x: dict[str, Any], vmax: float, steps: int = 24) -> list[dict[str, float]]:
    vols = np.linspace(0, vmax, steps + 1)
    xs = [_with_volume(x, v) for v in vols]
    model = _predict_many(xs)
    wb = water_balance_6h(pd.DataFrame(xs), float((load() or {}).get("fallback_vwc", 20.0)))
    return [{"volume_l": float(v), "predicted_vwc_pct": float(p), "water_balance_vwc_pct": float(w)} for v, p, w in zip(vols, model, wb)]


def recommend(zone_id: str, date: str, overrides: dict[str, Any] | None = None, p_override: float | None = None,
              target_vwc_pct: float | None = None, budget_l: float | None = None) -> dict[str, Any]:
    """قرار FAO-56 + الكمية + تنبؤ النموذج بالرطوبة بعد 6 ساعات. لا يحفظ (انظر save)."""
    overrides = overrides or {}
    z = _zone(zone_id)
    rec, x, changed = build_inputs(zone_id, date, overrides)
    theta = x.get("before_VWC_pct")
    p_tab = p_override if p_override is not None else z["p_table"]
    f = fao56(z["field_capacity_pct"], z["wilting_pct"], z["root_depth_m"], theta, x.get("et0_forecast_24h_mm"),
              z["kc_assumed"], p_tab)
    rain = float(x.get("rain_forecast_24h_mm") or 0.0)
    reasons, warnings = [], _range_warnings(x)
    sat = z["saturation_pct_assumed"]

    # 1) فحص الحساس — قاعدة أمان مستقلة
    if theta is None or not (0 <= theta <= sat):
        action, code = "CHECK_SENSOR", "sensor_missing" if theta is None else "sensor_out_of_range"
        reasons.append("لا توجد قراءة رطوبة حالية؛ لا يُحسب استنزاف ولا كمية حتى يُفحص الحساس." if theta is None else
                       f"القراءة {theta:g}% خارج المدى الفيزيائي [0، {sat:g}%] (التشبع المفترض في الملف).")
        dr = None
    else:
        dr = f["depletion_mm"]
        dr24 = dr + f["etc_mm"] - rain
        reasons.append(f"الاستنزاف الحالي Dr = 1000 × ({z['field_capacity_pct']:g}% − {theta:.2f}%) × {z['root_depth_m']:g} م = {dr:.1f} مم "
                       f"({100 * f['depletion_frac_taw']:.0f}% من الماء المتاح TAW = {f['taw_mm']:.1f} مم).")
        reasons.append(f"حد الإجهاد RAW = p × TAW = {f['p_adjusted']:.2f} × {f['taw_mm']:.1f} = {f['raw_mm']:.1f} مم "
                       f"(p من FAO-56 = {p_tab:g} معدلة بـ ETc = {f['etc_mm']:.2f} مم). عتبة الري ≈ {f['trigger_vwc_pct']:.2f}%.")
        # (أ) هل يلزم الري دون اعتبار المطر؟  (ب) ثم هل يغني المطر المتوقع عنه؟ — كل سبب برمز مستقل
        need_now, need_24 = dr >= f["raw_mm"], dr + f["etc_mm"] >= f["raw_mm"]
        if not (need_now or need_24):
            action, code = "DEFER", "depletion_below_raw"
            reasons.append(f"Dr + ETc = {dr + f['etc_mm']:.1f} مم < RAW ({f['raw_mm']:.1f} مم): الماء سهل الإتاحة كافٍ لـ 24 ساعة — تأجيل.")
        elif rain > 0 and rain >= dr:
            action, code = "DEFER", "rain_covers_depletion"
            reasons.append(f"الري لازم بحساب الاستنزاف، لكن المطر المتوقع ({rain:g} مم) يغطي الاستنزاف ({dr:.1f} مم) — تأجيل وإعادة التقييم غدًا.")
        elif not need_now and dr24 < f["raw_mm"]:
            action, code = "DEFER", "rain_offsets_etc"
            reasons.append(f"دون مطر ستبلغ الرطوبة حد الإجهاد خلال 24 ساعة، لكن Dr + ETc − المطر ({rain:g} مم) = {dr24:.1f} مم < RAW — تأجيل.")
        elif need_now:
            action, code = "IRRIGATE", "depletion_ge_raw"
            reasons.append(f"Dr ({dr:.1f} مم) ≥ RAW ({f['raw_mm']:.1f} مم): الرطوبة عند حد الإجهاد أو دونه — ري.")
        else:
            action, code = "IRRIGATE", "will_cross_raw_24h"
            reasons.append(f"Dr + ETc − المطر المتوقع = {dr24:.1f} مم ≥ RAW: ستعبر الرطوبة حد الإجهاد خلال 24 ساعة — ري اليوم.")

    # 2) الكمية: إعادة الملء حتى السعة الحقلية (FAO-56) ÷ الكفاءة
    plan = None
    target = target_vwc_pct if target_vwc_pct is not None else z["field_capacity_pct"]
    train_rng = z.get("training_volume_range_l") or [0, 0]
    if action == "IRRIGATE":
        net_mm = max(0.0, 1000 * (target - theta) / 100 * z["root_depth_m"])
        gross_l = net_mm * z["area_m2"] / z["efficiency"]
        limits = []
        if budget_l is not None and gross_l > budget_l:
            gross_l, limits = budget_l, ["daily_budget"]
        plan = {"net_mm": net_mm, "volume_l": round(gross_l, 1), "duration_min": round(gross_l / z["nominal_flow_L_min"], 1),
                "flow_l_min": z["nominal_flow_L_min"], "efficiency": z["efficiency"], "area_m2": z["area_m2"],
                "target_vwc_pct": target, "limits_applied": limits,
                "formula": f"({target:g}% − {theta:.2f}%) × {z['root_depth_m']:g} م × 1000 = {net_mm:.1f} مم صافي؛ "
                           f"× {z['area_m2']:g} م² ÷ {z['efficiency']:g} = {gross_l:,.0f} لتر؛ ÷ {z['nominal_flow_L_min']:g} ل/د = "
                           f"{gross_l / z['nominal_flow_L_min']:.1f} دقيقة"}
        if train_rng and gross_l > train_rng[1]:
            warnings.append(f"الكمية المقترحة {gross_l:,.0f} ل أكبر من أقصى كمية في بيانات تدريب هذه المنطقة ({train_rng[1]:,.0f} ل)؛ "
                            "تنبؤ النموذج عندها استقراء والنموذج الشجري يثبت خارج نطاقه.")

    # 3) النموذج: الرطوبة بعد 6 ساعات دون ري وبالكمية المقترحة، ومنحنى الاستجابة
    model = None
    if load() is not None:
        vol = plan["volume_l"] if plan else 0.0
        p_none, p_plan = _predict_many([_with_volume(x, 0.0), _with_volume(x, vol)])
        vmax = max(train_rng[1] if train_rng else 0, (plan or {}).get("volume_l", 0) * 1.15, 100.0)
        curve = response_curve(x, vmax)
        reach = next((c["volume_l"] for c in curve if c["predicted_vwc_pct"] >= target), None)
        model = {"version": (load() or {}).get("version"), "predicted_vwc_no_irrigation_pct": float(p_none),
                 "predicted_vwc_with_plan_pct": float(p_plan), "volume_used_l": vol, "curve": curve,
                 "training_volume_range_l": train_rng, "target_vwc_pct": target,
                 "model_min_volume_for_target_l": reach,
                 "model_min_volume_note": None if reach is not None else
                 "لا يصل التنبؤ إلى الهدف ضمن المدى المعروض؛ الهدف يُقاس بعد 6 ساعات وجزء من الماء يتصرف أو يتبخر."}
        if x["before_missing"]:
            warnings.append("القراءة الحالية مفقودة؛ النموذج يعتمد على قراءة الأمس ومتوسط 7 أيام، والتنبؤ أقل موثوقية.")
    else:
        warnings.append("نموذج المحاصيل غير محمّل؛ شغّلي ml/training/train_crops_model.py")

    return {
        "zone": {k: z[k] for k in ("zone_id", "zone_name", "crop", "area_m2", "irrigation_system", "soil_type", "root_depth_m",
                                   "field_capacity_pct", "wilting_pct", "saturation_pct_assumed", "efficiency", "nominal_flow_L_min",
                                   "kc_assumed", "p_table", "p_source")},
        "date": date, "decision_time": f"{DECISION_UTC} ({DECISION_LOCAL})", "event_id": rec["event_id"],
        "temporal_split": rec["temporal_split"],
        "decision": {"action": action, "rule_code": code, "reasons": reasons},
        "fao56": {**f, "rain_forecast_mm": rain, "depletion_mm": dr}, "water_plan": plan, "model": model,
        "inputs_used": x, "changed_inputs": changed,
        "recorded_in_file": {"before_vwc_pct": rec["before_VWC_pct"], "after_6h_vwc_pct": rec["recorded_after_6h"],
                             "planned_volume_l": rec["planned_volume_L"], "actual_volume_l": rec["recorded_actual_volume_l"],
                             "simulated_fault_label": rec["simulated_fault_label"],
                             "note": "خطة المولد في الملف للمقارنة فقط؛ قاعدتها غير موثقة في الملف."},
        "warnings": warnings, "method_note": "القرار والكمية: FAO-56 الفصل 8 بقيم المنطقة من الملف و p من الجدول 22. "
                                             "الرطوبة المتوقعة: نموذج المحاصيل المدرب على بيانات محاكاة.",
        "valve_command": None, "data_notice": DATA_NOTICE,
    }


def save(res: dict[str, Any], source: str, request_id: int | None, strategy: str = "fao56_refill") -> int:
    m = res.get("model") or {}
    plan = res.get("water_plan") or {}
    with session() as con:
        cur = con.execute("""INSERT INTO app_crop_recommendations(created_at, request_id, zone_id, base_event_id, decision_date, source,
            strategy, action, rule_code, before_vwc_pct, target_vwc_pct, trigger_vwc_pct, depletion_mm, raw_mm, volume_l, duration_min,
            predicted_vwc_pct, predicted_no_irrigation_vwc_pct, model_version, reasons_json, warnings_json, inputs_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (utcnow(), request_id, res["zone"]["zone_id"], res["event_id"], res["date"], source, strategy, res["decision"]["action"],
             res["decision"]["rule_code"], res["inputs_used"].get("before_VWC_pct"), plan.get("target_vwc_pct", m.get("target_vwc_pct")),
             res["fao56"].get("trigger_vwc_pct"), res["fao56"].get("depletion_mm"), res["fao56"].get("raw_mm"),
             plan.get("volume_l", m.get("volume_used_l", 0.0)) or 0.0, plan.get("duration_min", 0.0) or 0.0,
             m.get("predicted_vwc_with_plan_pct"), m.get("predicted_vwc_no_irrigation_pct"), m.get("version"),
             dumps(res["decision"]["reasons"]), dumps(res["warnings"]), dumps({"changed": res["changed_inputs"], "used": res["inputs_used"]})))
        return int(cur.lastrowid)


# ------------------------------------------------------------------ المحاكاة
def simulate(zone_id: str, date: str, scenarios: list[dict[str, Any]], request_id: int | None) -> dict[str, Any]:
    z = _zone(zone_id)
    out = []
    fb = float((load() or {}).get("fallback_vwc", 20.0))
    for s in scenarios:
        ov = {k: s.get(k) for k in OVERRIDABLE}
        rec, x, changed = build_inputs(zone_id, date, ov)
        xv = _with_volume(x, s["volume_l"])
        pred = float(_predict_many([xv])[0])
        wb = float(water_balance_6h(pd.DataFrame([xv]), fb)[0])
        warn = _range_warnings(xv)
        res = {"label": s.get("label") or f"{s['volume_l']:,.0f} ل", "volume_l": s["volume_l"],
               "duration_min": xv["planned_duration_min"], "before_vwc_pct": x.get("before_VWC_pct"),
               "predicted_vwc_pct": pred, "water_balance_vwc_pct": wb,
               "change_pp": None if x.get("before_VWC_pct") is None else pred - x["before_VWC_pct"],
               "depth_mm_net": s["volume_l"] * z["efficiency"] / z["area_m2"], "changed_inputs": changed, "warnings": warn}
        with session() as con:
            cur = con.execute("""INSERT INTO app_crop_recommendations(created_at, request_id, zone_id, base_event_id, decision_date, source,
                strategy, action, rule_code, before_vwc_pct, volume_l, duration_min, predicted_vwc_pct, model_version, reasons_json,
                warnings_json, inputs_json) VALUES (?,?,?,?,?,'simulation','user_scenario',?,?,?,?,?,?,?,?,?,?)""",
                (utcnow(), request_id, zone_id, rec["event_id"], date, "IRRIGATE" if s["volume_l"] > 0 else "DEFER", "scenario",
                 x.get("before_VWC_pct"), s["volume_l"], xv["planned_duration_min"], pred, (load() or {}).get("version"),
                 dumps([res["label"]]), dumps(warn), dumps({"changed": changed, "used": xv})))
            res["saved_id"] = int(cur.lastrowid)
        out.append(res)
    _, x0, _ = build_inputs(zone_id, date, {k: scenarios[0].get(k) for k in OVERRIDABLE})
    rng = (load() or {}).get("zone_ranges", {}).get(zone_id, {}).get("planned_volume_L", [0, 0])
    vmax = max([rng[1], *[s["volume_l"] * 1.15 for s in scenarios], 100.0])
    return {"zone_id": zone_id, "crop": z["crop"], "date": date, "scenarios": out, "curve": response_curve(x0, vmax),
            "training_volume_range_l": rng, "field_capacity_pct": z["field_capacity_pct"], "wilting_pct": z["wilting_pct"],
            "model_version": (load() or {}).get("version"),
            "disclaimer_ar": "نتائج نموذج مدرب على بيانات محاكاة؛ ليست قياسات ميدانية.", "data_notice": DATA_NOTICE}


# ------------------------------------------------------------------ لوحة التحكم والسجل
def dashboard(date: str | None) -> dict[str, Any]:
    rng = date_range()
    date = date or rng["max"]
    if not (rng["min"] <= date <= rng["max"]):
        raise ValueError(f"التاريخ {date} خارج نطاق بيانات المحاصيل {rng['min']} — {rng['max']}")
    con = connect()
    try:
        trend = rows(con, """select m.zone_id, substr(m.feature_cutoff_at,1,10) date, m.before_VWC_pct before_vwc,
            o.target_after_6h_VWC_pct after_vwc, m.planned_volume_L planned_l, o.actual_volume_L actual_l
            from v2_ml_ready m join v2_outcomes o using(event_id)
            where substr(m.feature_cutoff_at,1,10) between date(?, '-29 day') and ? order by 2, 1""", (date, date))
        usage = rows(con, """select m.zone_id, sum(m.planned_volume_L) planned_l, sum(o.actual_volume_L) actual_l,
            sum(m.planned_volume_L > 0) irrigations from v2_ml_ready m join v2_outcomes o using(event_id)
            where substr(m.feature_cutoff_at,1,10) between date(?, '-29 day') and ? group by 1""", (date, date))
        recent = rows(con, """select crop_rec_id, created_at, zone_id, decision_date, source, action, volume_l, predicted_vwc_pct
            from app_crop_recommendations order by crop_rec_id desc limit 8""")
    finally:
        con.close()
    zs = []
    for z in zones():
        try:
            r = recommend(z["zone_id"], date)
        except KeyError:
            continue
        zs.append({"zone": r["zone"], "decision": r["decision"], "fao56": r["fao56"], "water_plan": r["water_plan"],
                   "model": {k: v for k, v in (r["model"] or {}).items() if k != "curve"}, "warnings": r["warnings"],
                   "before_vwc_pct": r["inputs_used"].get("before_VWC_pct"), "recorded_in_file": r["recorded_in_file"]})
    return {"date": date, "range": rng, "zones": zs, "trend_30d": trend, "usage_30d": usage, "recent_saved": recent,
            "model": status(), "data_notice": DATA_NOTICE,
            "note": "التوصيات هنا محسوبة عند الطلب ولا تُحفظ؛ احفظيها من صفحة المناطق والمحاصيل."}


def history(zone_id: str | None, action: str | None, source: str | None, date_from: str | None, date_to: str | None,
            search: str | None, limit: int, offset: int) -> dict[str, Any]:
    where, params = [], []
    for col, val in (("zone_id", zone_id), ("action", action), ("source", source)):
        if val:
            where.append(f"r.{col} = ?"); params.append(val)
    if date_from:
        where.append("r.decision_date >= ?"); params.append(date_from)
    if date_to:
        where.append("r.decision_date <= ?"); params.append(date_to)
    if search:
        where.append("(r.base_event_id like ? or cast(r.crop_rec_id as text) = ? or z.crop like ?)")
        params += [f"%{search}%", search, f"%{search}%"]
    w = ("where " + " and ".join(where)) if where else ""
    con = connect()
    try:
        total = one(con, f"select count(*) n from app_crop_recommendations r join v2_zones z using(zone_id) {w}", tuple(params))["n"]
        items = rows(con, f"""select r.*, z.crop, z.zone_name from app_crop_recommendations r join v2_zones z using(zone_id) {w}
            order by r.crop_rec_id desc limit ? offset ?""", (*params, limit, offset))
    finally:
        con.close()
    for it in items:
        for k in ("reasons_json", "warnings_json", "inputs_json"):
            it[k.removesuffix("_json")] = json.loads(it.pop(k) or "null")
    return {"total": total, "items": items, "limit": limit, "offset": offset}


def predictions(split: str) -> list[dict[str, Any]]:
    con = connect()
    try:
        return rows(con, """select p.*, m.feature_cutoff_at from app_crop_predictions p join v2_ml_ready m using(event_id)
            where p.split = ? order by m.feature_cutoff_at, p.zone_id""", (split,))
    finally:
        con.close()
