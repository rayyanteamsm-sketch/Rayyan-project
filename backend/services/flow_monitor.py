"""
مراقبة التدفق واكتشاف المشكلات — نفس قواعد rule_alerts في الحزمة (build_dataset.py):
  • flow_first5min_rule_v1: متوسط تدفق أول 5 قراءات = 0 → no_flow ؛ < 0.7 × الاسمي → low_flow
  • positive_flow_after_planned_close_v1: تدفق موجب بعد نهاية الخطة → unexpected_flow
  • مقارنة المخطط بالمنفذ لكل رية (الانحراف باللتر والنسبة)
التنبيه لا يؤكد السبب (تسرب/عطل)؛ التأكيد يحتاج فحصًا ميدانيًا.
"""
from __future__ import annotations

from typing import Any

from backend.app.config import FLOW_LOW_FRACTION, LOCAL_TZ
from backend.database.db import connect, one, rows
from backend.services.reference import zone

ALERT_AR = {"no_flow": "لم يصل الماء", "low_flow": "تدفق منخفض", "unexpected_flow": "تدفق بعد موعد الإغلاق",
            "unaccounted_water": "ماء غير محسوب في موازنة الموقع", "stale_sensor": "قراءة حساس قديمة/مفقودة"}


def _local(ts: str | None) -> str | None:
    if not ts:
        return None
    from datetime import datetime
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(LOCAL_TZ).isoformat(timespec="minutes")


def analyse_event(event_id: str, con=None) -> dict[str, Any]:
    own = con is None
    con = con or connect()
    try:
        e = one(con, """select e.*, d.planned_volume_l, d.planned_duration_min, d.planned_start_at, d.planned_end_at
            from irrigation_events e join decisions d using(decision_id) where e.event_id = ?""", (event_id,))
        if not e:
            raise KeyError(event_id)
        series = rows(con, """select measured_at, flow_l_min, counter_l from flow_measurements
            where event_id = ? order by measured_at""", (event_id,))
        stored = rows(con, "select alert_type, detected_at, alert_value, method_version from rule_alerts where event_id = ?", (event_id,))
    finally:
        if own:
            con.close()
    z = zone(e["zone_id"]); nominal = z.nominal_flow_l_min
    rates = [r for r in series if r["flow_l_min"] is not None]
    first5 = rates[:5]
    avg5 = sum(r["flow_l_min"] for r in first5) / len(first5) if first5 else None
    detected = []
    if avg5 is not None:
        if avg5 == 0:
            detected.append({"type": "no_flow", "value": avg5})
        elif avg5 < nominal * FLOW_LOW_FRACTION:
            detected.append({"type": "low_flow", "value": avg5})
    after = [r for r in rates if r["measured_at"] > e["planned_end_at"] and r["flow_l_min"] > 0]
    if after:
        detected.append({"type": "unexpected_flow", "value": after[0]["flow_l_min"]})
    for d in detected:
        d["label_ar"] = ALERT_AR[d["type"]]
    planned, delivered = e["planned_volume_l"], e["delivered_volume_l"]
    return {
        "event_id": event_id, "decision_id": e["decision_id"], "zone_id": e["zone_id"],
        "planned_volume_l": planned, "delivered_volume_l": delivered,
        "deviation_l": delivered - planned, "deviation_pct": (delivered - planned) / planned * 100 if planned else None,
        "planned_start_local": _local(e["planned_start_at"]), "planned_end_local": _local(e["planned_end_at"]),
        "execution_ended_local": _local(e["execution_ended_at"]),
        "nominal_flow_l_min": nominal, "first5_avg_flow_l_min": avg5,
        "detected_alerts": detected, "stored_rule_alerts": stored,
        "series": [{"t": _local(r["measured_at"]), "flow_l_min": r["flow_l_min"], "meter_l": r["counter_l"]} for r in series],
        "note": "التنبيه مشتق من قراءات عداد محاكاة؛ لا يؤكد تسربًا أو عطلًا قبل الفحص الميداني.",
    }


def all_alerts(limit: int = 200, until_utc: str | None = None) -> list[dict[str, Any]]:
    con = connect()
    try:
        q = """select a.*, i.confirmed_cause, i.confirmation_status from rule_alerts a
               left join incident_reviews i on i.event_id = a.event_id and a.event_id is not null"""
        params: tuple = ()
        if until_utc:
            q += " where a.detected_at <= ?"; params = (until_utc,)
        q += " order by a.detected_at desc limit ?"
        out = rows(con, q, params + (limit,))
    finally:
        con.close()
    for a in out:
        a["label_ar"] = ALERT_AR.get(a["alert_type"], a["alert_type"])
        a["detected_local"] = _local(a["detected_at"])
        a["data_origin"] = "derived_from_simulation"
    return out
