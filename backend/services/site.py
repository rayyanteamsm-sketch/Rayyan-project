"""معلومات الموقع والمناطق والأجهزة وتصنيف أصل البيانات ومعرض الصور."""
from __future__ import annotations

import json
from typing import Any

from backend.app.config import DATA_NOTICE, IMAGES, PROVENANCE
from backend.database.db import connect, one, rows

DEVICE_AR = {"soil_sensor": "حساس رطوبة تربة", "flow_meter": "عداد تدفق", "valve_relay": "صمام/مرحّل"}
ARM_AR = {"conventional": "جدول ري تقليدي ثابت (مقارنة)", "rayyan": "قواعد ريّان"}


def site_info() -> dict[str, Any]:
    con = connect()
    try:
        site = one(con, "select * from sites")
        zones = rows(con, """select z.*, p.profile_id, p.soil_texture, p.root_depth_m, p.field_capacity_vwc, p.wilting_point_vwc,
            p.saturation_vwc, p.depletion_fraction, p.application_efficiency, p.nominal_flow_l_min, p.response_lag_min,
            p.parameter_basis from zones z join zone_profiles p using(zone_id) order by z.zone_id""")
        devices = rows(con, "select * from devices order by zone_id, device_type")
        study = rows(con, "select * from study_parameters")
        assumptions = rows(con, "select * from assumptions")
        catalog = rows(con, "select [table] as table_name, file, grain_ar, data_type, row_count from _table_catalog") \
            if one(con, "select 1 from sqlite_master where name='_table_catalog'") else []
        gaps = rows(con, "select * from field_collection_plan order by priority")
        readiness = rows(con, "select * from function_readiness")
        sources = rows(con, "select * from sources")
    finally:
        con.close()
    for z in zones:
        z["trial_arm_ar"] = ARM_AR.get(z["trial_arm"], z["trial_arm"])
    for d in devices:
        d["device_type_ar"] = DEVICE_AR.get(d["device_type"], d["device_type"])
        d["installed"] = d["installation_status"] != "virtual_not_installed"
    groups: dict[str, dict[str, Any]] = {}
    for t in catalog:
        key, label, desc = PROVENANCE.get(t["data_type"], ("other", t["data_type"], ""))
        g = groups.setdefault(key, {"key": key, "label_ar": label, "description_ar": desc, "tables": []})
        g["tables"].append({"table": t["table_name"], "rows": t["row_count"], "grain_ar": t["grain_ar"]})
    order = ["observed", "reference", "simulated", "derived", "missing_field", "documentation"]
    return {"site": site, "zones": zones, "devices": devices, "study_parameters": study, "assumptions": assumptions,
            "provenance": [groups[k] for k in order if k in groups], "field_data_gaps": gaps,
            "function_readiness": readiness, "sources": sources, "data_notice": DATA_NOTICE}


def gallery() -> list[dict[str, Any]]:
    path = IMAGES / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
