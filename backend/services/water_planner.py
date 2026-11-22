"""
حساب كمية الري المقترحة — نفس معادلات rule_v1 في الحزمة، وليست جرعة مثلى متعلَّمة.

  الطلب (لتر)   = (FC − θ) × root_mm × area_m2 / application_efficiency      (مم × م² = لتر)
  الحد الأعلى   = max_event_l من config.json (80 لترًا)
  التخصيص       = min(1, الميزانية اليومية / مجموع طلب المنطقتين)            (توزيع بالنسبة عند العجز)
  الحجم المنفذ  = floor(الطلب × التخصيص / التدفق) × التدفق                  (دقائق تشغيل كاملة)
  المدة         = الحجم / التدفق الاسمي
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Optional

from backend.services.reference import ZoneProfile, sim_config


@dataclass
class WaterPlan:
    deficit_mm: float
    requested_l: float
    cap_l: float
    capped_l: float
    daily_budget_l: float
    other_zone_request_l: float
    allocation_factor: float
    volume_l: float
    duration_min: int
    flow_l_min: float
    application_efficiency: float
    limits_applied: list[str] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def plan(zone: ZoneProfile, vwc: float, daily_budget_l: Optional[float] = None,
         other_zone_request_l: float = 0.0, target_vwc: Optional[float] = None) -> WaterPlan:
    cfg = sim_config()
    target = zone.field_capacity_vwc if target_vwc is None else target_vwc
    budget = float(cfg["normal_daily_budget_l"] if daily_budget_l is None else daily_budget_l)
    cap = float(cfg["max_event_l"])
    flow = zone.nominal_flow_l_min
    deficit_mm = max(0.0, (target - vwc) * zone.root_mm)
    requested = deficit_mm * zone.area_m2 / zone.application_efficiency
    capped = min(cap, requested)
    total = capped + max(0.0, other_zone_request_l)
    alloc = min(1.0, budget / total) if total > 0 else 1.0
    volume = math.floor(capped * alloc / flow) * flow if flow > 0 else 0.0
    duration = int(round(volume / flow)) if flow > 0 else 0

    limits, expl = [], []
    expl.append(f"عجز الرطوبة حتى السعة الحقلية {target:.3f}: ({target:.3f} − {vwc:.3f}) × {zone.root_mm:.0f} مم = {deficit_mm:.2f} مم.")
    expl.append(f"الطلب = {deficit_mm:.2f} مم × {zone.area_m2:g} م² ÷ كفاءة {zone.application_efficiency:g} = {requested:.1f} لتر.")
    if requested > cap:
        limits.append("max_event_l")
        expl.append(f"قُصّ الطلب إلى الحد الأعلى للرية الواحدة {cap:g} لترًا.")
    if alloc < 1:
        limits.append("daily_budget")
        expl.append(f"الميزانية اليومية {budget:g} لترًا لا تكفي طلب المنطقتين ({total:.1f} لترًا)؛ "
                    f"خُصص {alloc*100:.0f}٪ من الطلب.")
    if volume < capped * alloc - 1e-9:
        limits.append("whole_minutes")
        expl.append(f"قُرّب الحجم لأسفل إلى دقائق تشغيل كاملة بتدفق {flow:g} لتر/دقيقة: {volume:g} لترًا.")
    expl.append(f"المدة = {volume:g} ÷ {flow:g} = {duration} دقيقة.")
    return WaterPlan(deficit_mm, requested, cap, capped, budget, other_zone_request_l, alloc, volume, duration, flow,
                     zone.application_efficiency, limits, expl)


def linear_preview_delta(zone: ZoneProfile, volume_l: float, et0_mm: Optional[float], kc_decision: float) -> float:
    """التقريب الخطي المعلن في الحزمة (decisions.predicted_delta_vwc و plan_candidates):
    Δθ = V × eff / (area × root_mm) − ET0 × Kc × (4/24) / root_mm"""
    et = (et0_mm or 0.0) * kc_decision * (4 / 24) / zone.root_mm
    return volume_l * zone.application_efficiency / (zone.area_m2 * zone.root_mm) - et
