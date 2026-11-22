"""البيانات المرجعية الثابتة: خصائص المناطق، إعدادات المحاكي، Kc الشهري للدراسة."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from backend.app.config import PACKAGE
from backend.database.db import connect, rows


@dataclass(frozen=True)
class ZoneProfile:
    zone_id: str
    profile_id: str
    trial_arm: str
    area_m2: float
    plant_species: str
    root_depth_m: float
    field_capacity_vwc: float
    wilting_point_vwc: float
    saturation_vwc: float
    depletion_fraction: float
    application_efficiency: float
    nominal_flow_l_min: float
    response_lag_min: int
    soil_texture: str
    parameter_basis: str

    @property
    def root_mm(self) -> float:
        return self.root_depth_m * 1000.0


@lru_cache(maxsize=1)
def sim_config() -> dict:
    """إعدادات المحاكي الأصلية (config.json في الحزمة) — مصدر حد الرية والميزانية."""
    return json.loads((PACKAGE / "config.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def zone_profiles() -> dict[str, ZoneProfile]:
    con = connect()
    try:
        data = rows(con, """select z.zone_id, p.profile_id, z.trial_arm, z.area_m2, z.plant_species, p.root_depth_m,
            p.field_capacity_vwc, p.wilting_point_vwc, p.saturation_vwc, p.depletion_fraction, p.application_efficiency,
            p.nominal_flow_l_min, p.response_lag_min, p.soil_texture, p.parameter_basis
            from zones z join zone_profiles p on p.zone_id = z.zone_id order by z.zone_id""")
    finally:
        con.close()
    return {r["zone_id"]: ZoneProfile(**r) for r in data}


@lru_cache(maxsize=1)
def monthly_kc() -> dict[int, float]:
    """Kc الشهري من دراسة Saeed 2018 (study_crop) — يستخدمه المحاكي في عتبة القرار."""
    con = connect()
    try:
        return {int(r["month"]): float(r["kc"]) for r in rows(con, "select month, kc from study_crop")}
    finally:
        con.close()


def zone(zone_id: str) -> ZoneProfile:
    zp = zone_profiles()
    if zone_id not in zp:
        raise KeyError(zone_id)
    return zp[zone_id]
