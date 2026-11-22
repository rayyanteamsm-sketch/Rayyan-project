"""
لوحة التحكم: حالة النظام والمنطقتين في يوم مختار من المحاكاة (افتراضيًا آخر يوم متاح).
لا توجد حساسات حية؛ "الحالي" = آخر نقطة قرار في المحاكاة لذلك اليوم، ويُذكر ذلك صراحة.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from backend.app.config import DATA_NOTICE, LOCAL_TZ
from backend.database.db import connect, one, rows
from backend.services import ml_service
from backend.services.flow_monitor import all_alerts
from backend.services.recommendation import replay
from backend.services.reference import zone_profiles

STATUS_AR = {"normal": "مكتملة", "no_flow": "لم يصل الماء", "low_flow": "تدفق منخفض", "stuck_open": "صمام لم يغلق في موعده"}


def _utc(d: date, hh: int = 0) -> str:
    """بداية اليوم المحلي (الرياض) بصيغة UTC المخزنة في القاعدة."""
    local = datetime(d.year, d.month, d.day, hh, tzinfo=LOCAL_TZ)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def data_range(con) -> dict[str, str]:
    r = one(con, "select min(issued_at) a, max(issued_at) b from decisions")
    m = one(con, "select max(measured_at) m from measurements_clean where usable_vwc is not null")
    first = datetime.fromisoformat(r["a"].replace("Z", "+00:00")).astimezone(LOCAL_TZ).date()
    last = datetime.fromisoformat(r["b"].replace("Z", "+00:00")).astimezone(LOCAL_TZ).date()
    lastm = datetime.fromisoformat(m["m"].replace("Z", "+00:00")).astimezone(LOCAL_TZ)
    return {"first_date": first.isoformat(), "last_date": last.isoformat(), "last_reading_local": lastm.isoformat(timespec="minutes")}


def build(day: Optional[date] = None) -> dict[str, Any]:
    con = connect()
    try:
        rng = data_range(con)
        first, last = date.fromisoformat(rng["first_date"]), date.fromisoformat(rng["last_date"])
        day = day or last
        if not (first <= day <= last):
            raise ValueError(f"التاريخ خارج نطاق المحاكاة [{first} — {last}]")
        tag = day.strftime("%Y%m%d")
        end_utc = _utc(day + timedelta(days=1))
        zones_out = []
        for zid, zp in zone_profiles().items():
            rep = replay(f"D{tag}{zid}")
            last_ev = one(con, """select e.event_id, e.decision_id, e.execution_started_at, e.delivered_volume_l, d.planned_volume_l,
                coalesce(t.scenario_type, 'normal') kind, o.pre_vwc, o.post_vwc, o.delta_vwc, o.label_status
                from irrigation_events e join decisions d using(decision_id)
                left join test_scenarios t on t.scenario_id = e.scenario_id
                left join event_outcomes o on o.event_id = e.event_id
                where e.zone_id = ? and e.execution_started_at < ? order by e.execution_started_at desc limit 1""", (zid, end_utc))
            if last_ev:
                last_ev["started_local"] = datetime.fromisoformat(last_ev["execution_started_at"].replace("Z", "+00:00")) \
                    .astimezone(LOCAL_TZ).isoformat(timespec="minutes")
                last_ev["status_ar"] = STATUS_AR.get(last_ev["kind"], last_ev["kind"])
            trend = rows(con, """select substr(datetime(measured_at, '+3 hours'), 1, 10) d, avg(usable_vwc) v, count(usable_vwc) n
                from measurements_clean where device_id = ? and measured_at >= ? and measured_at < ? group by d order by d""",
                         ("S" + zid, _utc(day - timedelta(days=29)), end_utc))
            use30 = one(con, """select coalesce(sum(e.delivered_volume_l),0) delivered, coalesce(sum(d.planned_volume_l),0) planned, count(*) n
                from irrigation_events e join decisions d using(decision_id)
                where e.zone_id = ? and e.execution_started_at >= ? and e.execution_started_at < ?""",
                        (zid, _utc(day - timedelta(days=29)), end_utc))
            total = one(con, """select coalesce(sum(e.delivered_volume_l),0) delivered, coalesce(sum(d.planned_volume_l),0) planned, count(*) n
                from irrigation_events e join decisions d using(decision_id) where e.zone_id = ? and e.execution_started_at < ?""",
                        (zid, end_utc))
            zones_out.append({
                "zone_id": zid, "trial_arm": zp.trial_arm, "area_m2": zp.area_m2, "plant": zp.plant_species,
                "field_capacity_vwc": zp.field_capacity_vwc, "wilting_point_vwc": zp.wilting_point_vwc,
                "recommendation": rep, "last_irrigation": last_ev, "moisture_trend_30d": trend,
                "water_30d": use30, "water_to_date": total,
            })
        alerts = all_alerts(limit=6, until_utc=end_utc)
        budget = one(con, "select allocated_volume_l from water_budgets where budget_id = ?", (f"B{tag}",))
        counts = one(con, """select (select count(*) from decisions) decisions, (select count(*) from irrigation_events) events,
            (select count(*) from measurements_clean) samples, (select count(*) from rule_alerts) alerts,
            (select count(*) from app_recommendations) app_recommendations, (select count(*) from app_simulations) app_simulations""")
    finally:
        con.close()
    ms = ml_service.status()
    return {
        "date": day.isoformat(), "data_range": rng, "data_notice": DATA_NOTICE,
        "system": {"mode": "simulation_replay", "mode_ar": "إعادة تشغيل بيانات المحاكاة — لا حساسات حية متصلة",
                   "model_loaded": ms["loaded"], "model_version": ms["version"], "model_source": ms["source"],
                   "database": "ok", "valve_control": "disabled_no_hardware", "counts": counts,
                   "daily_budget_l": budget["allocated_volume_l"] if budget else None},
        "zones": zones_out, "alerts": alerts,
    }


def water_usage() -> dict[str, Any]:
    con = connect()
    try:
        monthly = rows(con, """select substr(datetime(e.execution_started_at, '+3 hours'), 1, 7) month, e.zone_id,
            round(sum(d.planned_volume_l), 2) planned_l, round(sum(e.delivered_volume_l), 2) delivered_l, count(*) events
            from irrigation_events e join decisions d using(decision_id) group by 1, 2 order by 1, 2""")
        totals = rows(con, """select e.zone_id, z.trial_arm, round(sum(d.planned_volume_l), 2) planned_l,
            round(sum(e.delivered_volume_l), 2) delivered_l, count(*) events
            from irrigation_events e join decisions d using(decision_id) join zones z on z.zone_id = e.zone_id group by 1, 2""")
        cost = rows(con, "select zone_id, year, delivered_volume_l, water_tariff_sar_m3, water_cost_sar, cost_basis from cost_summary")
        stress = rows(con, """select zone_id, round(sum(stress_minutes)/60.0, 2) stress_hours from root_balance_daily group by zone_id""")
    finally:
        con.close()
    return {"monthly": monthly, "totals": totals, "cost": cost, "simulated_stress_hours": stress,
            "interpretation_ar": ("في هذا السيناريو المحاكى استهلكت منطقة قواعد ريّان (Z02) ماءً أكثر من منطقة الجدول التقليدي (Z01) "
                                  "مع ساعات إجهاد محاكاة أقل. لا توجد نتيجة توفير ماء مثبتة، والتكلفة بسعر افتراضي."),
            "data_origin": "simulation + derived_from_simulation", "data_notice": DATA_NOTICE}
