"""
تجميع التوصية الكاملة: محرك القرار → حساب الكمية → تنبؤ النموذج → حفظ في SQLite.
ويوفر إعادة تشغيل أي قرار محفوظ في جدول decisions بنفس مدخلاته الأصلية.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

from backend.app.config import DATA_NOTICE, LOCAL_TZ
from backend.database.db import connect, dumps, one, session, utcnow
from backend.services import ml_service
from backend.services.decision_engine import Decision, Forecast, Reason, SensorReading, decide
from backend.services.reference import ZoneProfile, sim_config, zone
from backend.services.water_planner import linear_preview_delta, plan

HOT_MONTHS = {5, 6, 7, 8, 9}


@dataclass
class Inputs:
    zone_id: str
    decision_date: date
    reading: SensorReading
    forecast: Forecast
    daily_budget_l: Optional[float]
    other_zone_request_l: float
    decision_time_local: Optional[str] = None


def build(inp: Inputs) -> dict[str, Any]:
    z = zone(inp.zone_id)
    dec: Decision = decide(z, inp.reading, inp.forecast, inp.decision_date)
    out: dict[str, Any] = {"zone_id": z.zone_id, "trial_arm": z.trial_arm, "decision": dec.to_dict(),
                           "water_plan": None, "prediction": None, "data_notice": DATA_NOTICE}
    warnings = list(dec.warnings)
    if dec.action == "IRRIGATE":
        wp = plan(z, float(inp.reading.vwc), inp.daily_budget_l, inp.other_zone_request_l)
        out["water_plan"] = wp.to_dict()
        if wp.volume_l <= 0:
            # نفس سلوك المحاكي: لا حجم بعد التخصيص ⇒ تأجيل مع ذكر السبب
            dec.action, dec.action_ar, dec.rule_code = "DEFER", "تأجيل", "defer_no_budget_after_allocation"
            dec.reasons.insert(0, Reason("no_budget",
                               "الرطوبة تحت العتبة لكن الميزانية المتاحة لا تسمح بدقيقة تشغيل واحدة.", kind="decisive"))
            out["decision"] = dec.to_dict()
        else:
            x = ml_service.build_features(float(inp.reading.vwc), wp.volume_l, wp.duration_min, z.root_depth_m,
                                          z.area_m2, inp.forecast.rain_mm, inp.forecast.et0_mm, inp.decision_date)
            out["prediction"] = _predict(z, x, inp.forecast, dec)
    out["warnings"] = warnings
    return out


def _predict(z: ZoneProfile, x: dict, fc: Forecast, dec: Decision) -> dict[str, Any]:
    lin = linear_preview_delta(z, x["planned_volume_l"], fc.et0_mm, dec.thresholds.kc_decision)
    if fc.rain_mm is None or fc.et0_mm is None:
        return {"available": False, "reason": "النموذج يحتاج توقع المطر والتبخر-النتح؛ أحدهما غير متاح.",
                "linear_delta_vwc": lin, "linear_post_vwc": x["pre_vwc"] + lin}
    p = ml_service.predict_one(x)
    return {"available": True, **p, "linear_delta_vwc": lin, "linear_post_vwc": x["pre_vwc"] + lin,
            "target_vwc": z.field_capacity_vwc,
            "note": "تنبؤ النموذج بالاستجابة بعد ساعتين من نهاية الرية، متعلَّم من بيانات محاكاة."}


def save(result: dict[str, Any], inp: Inputs, source: str, request_id: Optional[int] = None,
         based_on: Optional[str] = None) -> int:
    d, wp, pr = result["decision"], result["water_plan"] or {}, result["prediction"] or {}
    with session() as con:
        cur = con.execute("""INSERT INTO app_recommendations(created_at, request_id, zone_id, profile_id, source,
            based_on_decision_id, decision_time_local, pre_vwc, sensor_status, action, rule_code, reasons_json, trigger_vwc,
            target_vwc, requested_volume_l, suggested_volume_l, duration_min, budget_l, predicted_delta_vwc,
            predicted_post_vwc, model_version, warnings_json, inputs_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (utcnow(), request_id, inp.zone_id, zone(inp.zone_id).profile_id, source, based_on, inp.decision_time_local,
             inp.reading.vwc, d["sensor"]["status"], d["action"], d["rule_code"], dumps(d["reasons"]),
             d["thresholds"]["trigger_vwc"], d["thresholds"]["target_vwc"], wp.get("requested_l"),
             wp.get("volume_l", 0.0), wp.get("duration_min", 0), wp.get("daily_budget_l"),
             pr.get("delta_vwc"), pr.get("post_vwc"), pr.get("model_version"),
             dumps(result.get("warnings", []) + pr.get("warnings", [])),
             dumps({"zone_id": inp.zone_id, "decision_date": inp.decision_date, "reading": inp.reading.__dict__,
                    "forecast": inp.forecast.__dict__, "daily_budget_l": inp.daily_budget_l,
                    "other_zone_request_l": inp.other_zone_request_l})))
        return int(cur.lastrowid)


# ------------------------------------------------------------------ إعادة تشغيل القرارات المحفوظة
def _calendar_request(month: int, planned: float) -> float:
    """طلب الجدول التقليدي Z01 قبل التخصيص (60 لترًا صيفًا، 40 غير ذلك) في أيام جدوله."""
    if planned <= 0:
        return 0.0
    return 60.0 if month in HOT_MONTHS else 40.0


def stored_inputs(decision_id: str, con=None) -> tuple[Inputs, dict[str, Any]]:
    own = con is None
    con = con or connect()
    try:
        r = one(con, """select d.*, m.usable_vwc, m.measured_at, m.quality_flag, f.rain_mm, f.et0_mm, f.temperature_c,
            b.allocated_volume_l from decisions d
            left join measurements_clean m on m.sample_id = d.input_sample_id
            join weather_forecasts f on f.forecast_id = d.forecast_id
            join water_budgets b on b.budget_id = d.budget_id where d.decision_id = ?""", (decision_id,))
        if not r:
            raise KeyError(decision_id)
        issued = datetime.fromisoformat(r["issued_at"].replace("Z", "+00:00"))
        local = issued.astimezone(LOCAL_TZ)
        age = None if not r["measured_at"] else (issued - datetime.fromisoformat(r["measured_at"].replace("Z", "+00:00"))).total_seconds() / 60
        other_id = "Z01" if r["zone_id"] == "Z02" else "Z02"
        o = one(con, """select d.planned_volume_l, d.action, m.usable_vwc, m.measured_at, m.quality_flag
            from decisions d left join measurements_clean m on m.sample_id = d.input_sample_id
            where d.budget_id = ? and d.zone_id = ?""", (r["budget_id"], other_id))
    finally:
        if own:
            con.close()
    if other_id == "Z01":
        other_req = _calendar_request(local.month, o["planned_volume_l"] if o else 0.0)
    else:
        # المنطقة الثانية بقواعد ريّان: طلبها بعد القص قبل التخصيص
        other_req = 0.0
        if o and o["action"] == "irrigate" and o["usable_vwc"] is not None:
            oz = zone(other_id)
            other_req = plan(oz, o["usable_vwc"], 1e9).capped_l
    inp = Inputs(zone_id=r["zone_id"], decision_date=local.date(),
                 reading=SensorReading(r["usable_vwc"], age, r["quality_flag"] or "missing"),
                 forecast=Forecast(r["rain_mm"], r["et0_mm"], r["temperature_c"]),
                 daily_budget_l=r["allocated_volume_l"], other_zone_request_l=other_req,
                 decision_time_local=local.isoformat(timespec="minutes"))
    stored = {"decision_id": r["decision_id"], "action": r["action"], "reason": r["reason"],
              "planned_volume_l": r["planned_volume_l"], "planned_duration_min": r["planned_duration_min"],
              "method_version": r["method_version"], "predicted_delta_vwc_linear": r["predicted_delta_vwc"],
              "issued_at_local": local.isoformat(timespec="minutes")}
    return inp, stored


SIM_ACTION = {"irrigate": "IRRIGATE", "defer": "DEFER", "inspect": "CHECK_SENSOR"}


def replay(decision_id: str) -> dict[str, Any]:
    inp, stored = stored_inputs(decision_id)
    res = build(inp)
    wp = res["water_plan"] or {}
    res["stored_decision"] = stored
    res["agreement"] = {
        "comparable": stored["method_version"] == "rule_v1",
        "action_match": SIM_ACTION[stored["action"]] == res["decision"]["action"],
        "volume_match": abs((wp.get("volume_l") or 0.0) - stored["planned_volume_l"]) < 1e-6,
        "note": ("قرار المنطقة الثانية في المحاكاة صدر بقواعد ريّان rule_v1؛ المقارنة مباشرة."
                 if stored["method_version"] == "rule_v1" else
                 "المنطقة الأولى في المحاكاة تُروى بجدول تقليدي ثابت (calendar_v1)؛ توصية ريّان هنا للمقارنة فقط."),
    }
    res["inputs"] = {"decision_date": inp.decision_date.isoformat(), "decision_time_local": inp.decision_time_local,
                     "pre_vwc": inp.reading.vwc, "sensor_age_min": inp.reading.age_min, "sensor_quality": inp.reading.quality_flag,
                     "forecast_rain_mm": inp.forecast.rain_mm, "forecast_et0_mm": inp.forecast.et0_mm,
                     "forecast_temperature_c": inp.forecast.temperature_c, "daily_budget_l": inp.daily_budget_l,
                     "other_zone_request_l": inp.other_zone_request_l}
    return res
