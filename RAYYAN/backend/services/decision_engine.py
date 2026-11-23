"""
محرك قرار الري — قواعد ريّان (rule_v1) كما وردت في code/build_dataset.py بالحزمة.

ليس نموذج تصنيف ولا يتعلم من البيانات. ترتيب القواعد:
  1) فحص الحساس (قاعدة أمان مستقلة): لا قراءة صالحة حديثة ≤ 120 دقيقة  → CHECK_SENSOR
  2) توقع مطر ≥ 4 مم                                                      → DEFER
  3) الرطوبة ≤ العتبة = FC − p·(FC−WP) + ET0·Kc_dec / (root_mm·2)          → IRRIGATE
  4) غير ذلك                                                               → DEFER
حيث Kc_dec = Kc_شهر_الدراسة × (0.35 + 0.65·clip((T_توقع − 8)/20, 0, 1)).

كل قرار يعيد أسبابه بالأرقام والعتبات المستخدمة.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Optional

from backend.app.config import RAIN_DEFER_MM, SENSOR_MAX_AGE_MIN
from backend.services.reference import ZoneProfile, monthly_kc

RULE_VERSION = "rule_v1 (build_dataset.py)"
ACTION_AR = {"IRRIGATE": "ري", "DEFER": "تأجيل", "CHECK_SENSOR": "فحص الحساس"}


@dataclass
class SensorReading:
    vwc: Optional[float]
    age_min: Optional[float] = 0.0
    quality_flag: str = "ok"          # ok | missing | invalid_range | <أي قيمة أخرى تعني غير صالح>


@dataclass
class Forecast:
    rain_mm: Optional[float] = None
    et0_mm: Optional[float] = None
    temperature_c: Optional[float] = None


@dataclass
class Reason:
    code: str
    text_ar: str
    value: Optional[float] = None
    threshold: Optional[float] = None
    kind: str = "info"                # decisive | info | warning


@dataclass
class SensorCheck:
    ok: bool
    status: str
    issues: list[Reason] = field(default_factory=list)


@dataclass
class Thresholds:
    field_capacity_vwc: float
    wilting_point_vwc: float
    depletion_fraction: float
    taw_mm: float
    raw_mm: float
    base_trigger_vwc: float
    kc_month: float
    temperature_factor: Optional[float]
    kc_decision: float
    et_adjustment_vwc: float
    trigger_vwc: float
    target_vwc: float


@dataclass
class Decision:
    action: str
    action_ar: str
    rule_code: str
    sensor: SensorCheck
    thresholds: Thresholds
    reasons: list[Reason]
    warnings: list[str]
    rule_version: str = RULE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_sensor(r: SensorReading, zone: ZoneProfile) -> SensorCheck:
    """قاعدة الأمان: تُقيَّم قبل أي حساب زراعي، ونتيجتها لا تتجاوزها أي قاعدة أخرى."""
    issues: list[Reason] = []
    if r.vwc is None or r.quality_flag == "missing":
        issues.append(Reason("sensor_missing", "لا توجد قراءة رطوبة صالحة من الحساس.", kind="decisive"))
    elif r.quality_flag != "ok":
        issues.append(Reason("sensor_flagged", f"علامة جودة القراءة «{r.quality_flag}» وليست ok.", kind="decisive"))
    elif not (0.0 <= r.vwc <= zone.saturation_vwc):
        issues.append(Reason("sensor_out_of_range",
                             f"القراءة {r.vwc:.3f} خارج المدى الفيزيائي [0، {zone.saturation_vwc}].",
                             value=r.vwc, threshold=zone.saturation_vwc, kind="decisive"))
    if r.age_min is None:
        issues.append(Reason("sensor_age_unknown", "عمر القراءة غير معروف؛ لا يمكن التأكد من حداثتها.", kind="decisive"))
    elif r.age_min < 0:
        issues.append(Reason("sensor_future_timestamp", "وقت القراءة بعد وقت القرار.", value=r.age_min, kind="decisive"))
    elif r.age_min > SENSOR_MAX_AGE_MIN:
        issues.append(Reason("sensor_stale", f"آخر قراءة عمرها {r.age_min:.0f} دقيقة، أكثر من {SENSOR_MAX_AGE_MIN}.",
                             value=r.age_min, threshold=SENSOR_MAX_AGE_MIN, kind="decisive"))
    status = "ok" if not issues else issues[0].code
    return SensorCheck(ok=not issues, status=status, issues=issues)


def thresholds(zone: ZoneProfile, decision_date: date, fc: Forecast) -> tuple[Thresholds, list[str]]:
    warnings: list[str] = []
    fcap, wp, p = zone.field_capacity_vwc, zone.wilting_point_vwc, zone.depletion_fraction
    taw = (fcap - wp) * zone.root_mm
    base = fcap - p * (fcap - wp)
    kc = monthly_kc()[decision_date.month]
    if fc.temperature_c is None:
        tf = None
        kc_dec = kc
        warnings.append("درجة الحرارة المتوقعة غير متاحة؛ استُخدم Kc الشهري دون معامل الحرارة.")
    else:
        tf = 0.35 + 0.65 * max(0.0, min(1.0, (fc.temperature_c - 8.0) / 20.0))
        kc_dec = kc * tf
    if fc.et0_mm is None:
        et_adj = 0.0
        warnings.append("توقع التبخر-النتح غير متاح؛ العتبة دون تعديل الطلب الجوي.")
    else:
        et_adj = fc.et0_mm * kc_dec / (zone.root_mm * 2.0)
    return Thresholds(fcap, wp, p, taw, p * taw, base, kc, tf, kc_dec, et_adj, base + et_adj, fcap), warnings


def decide(zone: ZoneProfile, reading: SensorReading, fc: Forecast, decision_date: date) -> Decision:
    th, warnings = thresholds(zone, decision_date, fc)
    sensor = check_sensor(reading, zone)
    reasons: list[Reason] = []

    if not sensor.ok:
        reasons.extend(sensor.issues)
        reasons.append(Reason("no_agronomic_decision", "لا يُتخذ قرار ري أو تأجيل قبل التحقق من الحساس ميدانيًا."))
        return Decision("CHECK_SENSOR", ACTION_AR["CHECK_SENSOR"], sensor.status, sensor, th, reasons, warnings)

    vwc = float(reading.vwc)  # type: ignore[arg-type]
    if fc.rain_mm is None:
        warnings.append("توقع المطر غير متاح؛ لم تُطبق قاعدة التأجيل بسبب المطر.")
    elif fc.rain_mm >= RAIN_DEFER_MM:
        reasons.append(Reason("rain_forecast", f"يتوقع هطول {fc.rain_mm:.1f} مم خلال 24 ساعة (الحد {RAIN_DEFER_MM:g} مم).",
                              value=fc.rain_mm, threshold=RAIN_DEFER_MM, kind="decisive"))
        reasons.append(Reason("moisture_context", f"الرطوبة الحالية {vwc:.3f} والعتبة {th.trigger_vwc:.3f}.",
                              value=vwc, threshold=th.trigger_vwc))
        return Decision("DEFER", ACTION_AR["DEFER"], "defer_rain_forecast", sensor, th, reasons, warnings)
    else:
        reasons.append(Reason("rain_below_limit", f"المطر المتوقع {fc.rain_mm:.1f} مم أقل من حد التأجيل {RAIN_DEFER_MM:g} مم.",
                              value=fc.rain_mm, threshold=RAIN_DEFER_MM))

    depletion_mm = (th.field_capacity_vwc - vwc) * zone.root_mm
    if vwc <= th.trigger_vwc:
        reasons.insert(0, Reason("below_trigger",
                                 f"الرطوبة {vwc:.3f} عند العتبة {th.trigger_vwc:.3f} أو أقل منها؛ "
                                 f"الاستنزاف {depletion_mm:.1f} مم من أصل {th.raw_mm:.1f} مم سهل الإتاحة.",
                                 value=vwc, threshold=th.trigger_vwc, kind="decisive"))
        action, code = "IRRIGATE", "refill_root_zone"
    else:
        reasons.insert(0, Reason("above_trigger",
                                 f"الرطوبة {vwc:.3f} أعلى من العتبة {th.trigger_vwc:.3f}؛ الماء المتاح للجذور كافٍ الآن.",
                                 value=vwc, threshold=th.trigger_vwc, kind="decisive"))
        action, code = "DEFER", "defer_above_trigger"
    reasons.append(Reason("trigger_composition",
                          f"العتبة = {th.base_trigger_vwc:.3f} (FC − p·(FC−WP)) + {th.et_adjustment_vwc:.4f} تعديل الطلب الجوي "
                          f"(ET0 {fc.et0_mm if fc.et0_mm is not None else '—'} مم × Kc {th.kc_decision:.3f})."))
    return Decision(action, ACTION_AR[action], code, sensor, th, reasons, warnings)
