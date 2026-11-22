"""
محاكاة خطط الري: لكل سيناريو يتنبأ النموذج بتغير الرطوبة، ويُعرض بجانبه التقريب الخطي المعلن في الحزمة.
النتائج مخرجات نموذج متعلم من محاكاة، وليست قياسات.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from backend.app.config import DATA_NOTICE
from backend.database.db import connect, dumps, one, session, utcnow
from backend.services import ml_service
from backend.services.decision_engine import Forecast, thresholds
from backend.services.reference import sim_config, zone
from backend.services.water_planner import linear_preview_delta


def forecast_for(d: date) -> dict[str, Optional[float]]:
    """التوقع الاصطناعي المحفوظ لذلك اليوم إن وُجد (افتراضي للمدخلات)."""
    con = connect()
    try:
        r = one(con, "select rain_mm, et0_mm, temperature_c from weather_forecasts where forecast_id = ?", (f"FC{d:%Y%m%d}",))
    finally:
        con.close()
    return r or {"rain_mm": None, "et0_mm": None, "temperature_c": None}


def run(scenarios: list[dict[str, Any]], sweep: bool = True, request_id: Optional[int] = None) -> dict[str, Any]:
    out = []
    for i, s in enumerate(scenarios):
        z = zone(s["zone_id"]); d: date = s["decision_date"]
        fc_default = forecast_for(d)
        rain = s.get("forecast_rain_mm"); et0 = s.get("forecast_et0_mm"); temp = s.get("forecast_temperature_c")
        rain = fc_default["rain_mm"] if rain is None else rain
        et0 = fc_default["et0_mm"] if et0 is None else et0
        temp = fc_default["temperature_c"] if temp is None else temp
        if rain is None or et0 is None:
            raise ValueError(f"السيناريو {i+1}: لا يوجد توقع محفوظ لهذا التاريخ؛ أدخل المطر والتبخر-النتح يدويًا.")
        duration = s.get("duration_min")
        if duration is None:
            duration = s["volume_l"] / z.nominal_flow_l_min
        x = ml_service.build_features(s["pre_vwc"], s["volume_l"], duration, z.root_depth_m, z.area_m2, rain, et0, d)
        p = ml_service.predict_one(x)
        th, _ = thresholds(z, d, Forecast(rain, et0, temp))
        lin = linear_preview_delta(z, s["volume_l"], et0, th.kc_decision)
        item = {
            "index": i, "label": s.get("label") or f"سيناريو {i+1}", "zone_id": z.zone_id, "decision_date": d.isoformat(),
            "pre_vwc": s["pre_vwc"], "volume_l": s["volume_l"], "duration_min": duration,
            "forecast_rain_mm": rain, "forecast_et0_mm": et0, "forecast_temperature_c": temp,
            "predicted_delta_vwc": p["delta_vwc"], "predicted_post_vwc": p["post_vwc"],
            "linear_delta_vwc": lin, "linear_post_vwc": s["pre_vwc"] + lin,
            "target_vwc": z.field_capacity_vwc, "trigger_vwc": th.trigger_vwc,
            "gap_to_target_vwc": z.field_capacity_vwc - p["post_vwc"],
            "water_per_delta": (s["volume_l"] / p["delta_vwc"]) if p["delta_vwc"] > 1e-6 else None,
            "model_version": p["model_version"], "warnings": p["warnings"],
        }
        if sweep and i == 0:
            vols = [v for v in range(0, int(sim_config()["max_event_l"]) + 1, 4)]
            xs = [ml_service.build_features(s["pre_vwc"], v, v / z.nominal_flow_l_min, z.root_depth_m, z.area_m2, rain, et0, d) for v in vols]
            preds = ml_service.predict_many(xs)
            rng = ml_service.load()["feature_ranges"]["planned_volume_l"]
            item["sweep"] = [{"volume_l": v, "predicted_delta_vwc": pr,
                              "linear_delta_vwc": linear_preview_delta(z, v, et0, th.kc_decision),
                              "in_training_range": rng["min"] <= v <= rng["max"]} for v, pr in zip(vols, preds)]
        out.append(item)
    with session() as con:
        for it in out:
            cur = con.execute("""INSERT INTO app_simulations(created_at, request_id, zone_id, label, pre_vwc, volume_l, duration_min,
                decision_date, forecast_rain_mm, forecast_et0_mm, predicted_delta_vwc, predicted_post_vwc, linear_delta_vwc,
                model_version, warnings_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (utcnow(), request_id, it["zone_id"], it["label"], it["pre_vwc"], it["volume_l"], it["duration_min"],
                 it["decision_date"], it["forecast_rain_mm"], it["forecast_et0_mm"], it["predicted_delta_vwc"],
                 it["predicted_post_vwc"], it["linear_delta_vwc"], it["model_version"], dumps(it["warnings"])))
            it["simulation_id"] = cur.lastrowid
    return {"scenarios": out, "data_notice": DATA_NOTICE,
            "disclaimer_ar": "نتائج المحاكاة مخرجات نموذج تعلم من بيانات محاكاة، وليست قياسات ميدانية.",
            "linear_note_ar": "الخط المقارن هو التقريب الخطي المعلن في الحزمة (plan_candidates)، وليس حقيقة مستقلة."}
