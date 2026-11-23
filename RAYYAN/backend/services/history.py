"""
سجل العمليات: يربط decisions ← irrigation_events ← event_outcomes بالمفاتيح decision_id/event_id/zone_id
دون تكرار سجلات، ويضيف توصيات التطبيق المحفوظة (app_recommendations) كمصدر مستقل.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from backend.app.config import LOCAL_TZ
from backend.database.db import connect, one, rows
from backend.services.flow_monitor import ALERT_AR, analyse_event

ACTION_MAP = {"irrigate": "IRRIGATE", "defer": "DEFER", "inspect": "CHECK_SENSOR"}
ACTION_SQL = {v: k for k, v in ACTION_MAP.items()}
STATUS_AR = {"not_executed": "لا تنفيذ", "completed": "مكتملة", "no_flow": "لم يصل الماء", "low_flow": "تدفق منخفض",
             "stuck_open": "صمام لم يغلق في موعده", "label_missing": "نتيجة الرطوبة ناقصة", "app_only": "توصية فقط — لا تنفيذ"}

SIM_SQL = """
select d.decision_id, d.zone_id, d.issued_at, d.action, d.reason, d.method_version,
       d.planned_volume_l, d.planned_duration_min, m.usable_vwc as input_vwc,
       e.event_id, e.delivered_volume_l, t.scenario_type,
       o.pre_vwc, o.post_vwc, o.delta_vwc, o.label_status, o.confounding_flags,
       p.predicted_delta_vwc as ml_predicted_delta, p.split as ml_split, p.out_of_sample as ml_out_of_sample,
       (select group_concat(alert_type) from rule_alerts a where a.event_id = e.event_id) as alerts
from decisions d
left join measurements_clean m on m.sample_id = d.input_sample_id
left join irrigation_events e on e.decision_id = d.decision_id
left join test_scenarios t on t.scenario_id = e.scenario_id
left join event_outcomes o on o.event_id = e.event_id
left join app_model_predictions p on p.decision_id = d.decision_id
"""


def _utc(d: date) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=LOCAL_TZ).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local(ts: str) -> str:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(LOCAL_TZ).isoformat(timespec="minutes")


def _status(r: dict) -> str:
    if not r.get("event_id"):
        return "not_executed"
    if r.get("scenario_type") in ("no_flow", "low_flow", "stuck_open"):
        return r["scenario_type"]
    if r.get("label_status") and not str(r["label_status"]).startswith("valid"):
        return "label_missing"
    return "completed"


def query(source: str = "all", zone_id: Optional[str] = None, action: Optional[str] = None,
          date_from: Optional[date] = None, date_to: Optional[date] = None, status: Optional[str] = None,
          search: Optional[str] = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    con = connect()
    try:
        if source in ("all", "simulation"):
            where, params = [], []
            if zone_id: where.append("d.zone_id = ?"); params.append(zone_id)
            if action: where.append("d.action = ?"); params.append(ACTION_SQL[action])
            if date_from: where.append("d.issued_at >= ?"); params.append(_utc(date_from))
            if date_to: where.append("d.issued_at < ?"); params.append(_utc(date_to + timedelta(days=1)))
            if search:
                where.append("(d.decision_id like ? or e.event_id like ?)"); params += [f"%{search}%", f"%{search}%"]
            sql = SIM_SQL + (" where " + " and ".join(where) if where else "")
            for r in rows(con, sql, tuple(params)):
                st = _status(r)
                items.append({
                    "source": "simulation", "source_ar": "سجل المحاكاة", "id": r["decision_id"],
                    "decision_id": r["decision_id"], "event_id": r["event_id"], "zone_id": r["zone_id"],
                    "time_local": _local(r["issued_at"]), "action": ACTION_MAP[r["action"]], "reason": r["reason"],
                    "method_version": r["method_version"],
                    "pre_vwc": r["pre_vwc"] if r["pre_vwc"] is not None else r["input_vwc"],
                    "planned_volume_l": r["planned_volume_l"], "planned_duration_min": r["planned_duration_min"],
                    "delivered_volume_l": r["delivered_volume_l"], "post_vwc": r["post_vwc"], "delta_vwc": r["delta_vwc"],
                    "ml_predicted_delta": r["ml_predicted_delta"], "ml_split": r["ml_split"],
                    "ml_out_of_sample": bool(r["ml_out_of_sample"]) if r["ml_out_of_sample"] is not None else None,
                    "alerts": [ALERT_AR.get(a, a) for a in (r["alerts"] or "").split(",") if a],
                    "confounding": r["confounding_flags"], "status": st, "status_ar": STATUS_AR[st],
                })
        if source in ("all", "app"):
            where, params = [], []
            if zone_id: where.append("zone_id = ?"); params.append(zone_id)
            if action: where.append("action = ?"); params.append(action)
            if date_from: where.append("created_at >= ?"); params.append(_utc(date_from))
            if date_to: where.append("created_at < ?"); params.append(_utc(date_to + timedelta(days=1)))
            if search: where.append("(cast(recommendation_id as text) like ? or coalesce(based_on_decision_id,'') like ?)"); params += [f"%{search}%"] * 2
            sql = "select * from app_recommendations" + (" where " + " and ".join(where) if where else "")
            for r in rows(con, sql, tuple(params)):
                items.append({
                    "source": "app", "source_ar": "توصية من التطبيق", "id": f"R{r['recommendation_id']}",
                    "decision_id": r["based_on_decision_id"], "event_id": None, "zone_id": r["zone_id"],
                    "time_local": _local(r["created_at"]), "action": r["action"], "reason": r["rule_code"],
                    "method_version": "rule_v1 + " + (r["model_version"] or "—"), "pre_vwc": r["pre_vwc"],
                    "planned_volume_l": r["suggested_volume_l"], "planned_duration_min": r["duration_min"],
                    "delivered_volume_l": None, "post_vwc": r["predicted_post_vwc"], "delta_vwc": r["predicted_delta_vwc"],
                    "post_is_prediction": True, "ml_predicted_delta": r["predicted_delta_vwc"], "ml_split": None,
                    "ml_out_of_sample": None, "alerts": [], "confounding": None,
                    "status": "app_only", "status_ar": STATUS_AR["app_only"], "app_source": r["source"],
                })
    finally:
        con.close()
    if status:
        items = [i for i in items if i["status"] == status]
    items.sort(key=lambda i: (i["time_local"], i["source"], i["zone_id"]), reverse=True)
    counts = {"IRRIGATE": 0, "DEFER": 0, "CHECK_SENSOR": 0}
    for i in items:
        counts[i["action"]] += 1
    return {"total": len(items), "limit": limit, "offset": offset, "counts_by_action": counts,
            "items": items[offset:offset + limit]}


def detail(decision_id: str) -> dict[str, Any]:
    con = connect()
    try:
        r = one(con, SIM_SQL + " where d.decision_id = ?", (decision_id,))
        if not r:
            raise KeyError(decision_id)
        apps = rows(con, "select recommendation_id, created_at, action, suggested_volume_l from app_recommendations where based_on_decision_id = ?",
                    (decision_id,))
    finally:
        con.close()
    out = {**r, "time_local": _local(r["issued_at"]), "action": ACTION_MAP[r["action"]], "status": _status(r),
           "app_replays": apps}
    out["status_ar"] = STATUS_AR[out["status"]]
    out["flow"] = analyse_event(r["event_id"]) if r["event_id"] else None
    return out


def operations_log(limit: int = 100) -> list[dict[str, Any]]:
    con = connect()
    try:
        return rows(con, "select request_id, created_at, method, path, query, status_code, duration_ms, error "
                         "from app_requests order by request_id desc limit ?", (limit,))
    finally:
        con.close()
