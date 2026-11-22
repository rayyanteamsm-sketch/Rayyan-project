"""نماذج Pydantic للتحقق من المدخلات. كل قيد هنا يظهر في مخطط OpenAPI تلقائيًا."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ZoneId = Literal["Z01", "Z02"]
DATE_MIN, DATE_MAX = date(2000, 1, 1), date(2100, 12, 31)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("decision_date", check_fields=False)
    @classmethod
    def _date_range(cls, v):
        if v is not None and not (DATE_MIN <= v <= DATE_MAX):
            raise ValueError("التاريخ خارج النطاق المعقول")
        return v


class PredictRequest(_Base):
    """تنبؤ مباشر بتغير الرطوبة لخطة ري معطاة (النموذج فقط، دون محرك القرار)."""
    zone_id: ZoneId = Field("Z02", description="المنطقة؛ تحدد عمق الجذور والمساحة من zone_profiles")
    decision_date: date = Field(..., description="تاريخ القرار (محلي) — يحدد doy_sin/doy_cos")
    pre_vwc: float = Field(..., ge=0, le=0.4, description="رطوبة التربة قبل القرار m³/m³")
    planned_volume_l: float = Field(..., ge=0, le=500, description="حجم الري المخطط باللتر")
    planned_duration_min: Optional[float] = Field(None, gt=0, le=600, description="المدة؛ إن غابت = الحجم ÷ التدفق الاسمي")
    forecast_rain_mm: float = Field(..., ge=0, le=300, description="مطر متوقع خلال 24 ساعة (مم)")
    forecast_et0_mm: float = Field(..., ge=0, le=25, description="تبخر-نتح مرجعي متوقع خلال 24 ساعة (مم)")

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {
        "zone_id": "Z02", "decision_date": "2025-07-15", "pre_vwc": 0.10, "planned_volume_l": 60,
        "forecast_rain_mm": 0, "forecast_et0_mm": 9.5}})


class RecommendRequest(_Base):
    """بيانات المنطقة والحساس والطقس لإصدار قرار ري مفسَّر وكمية مقترحة."""
    zone_id: ZoneId
    decision_date: date = Field(..., description="تاريخ القرار المحلي؛ يحدد Kc الشهري والموسم")
    pre_vwc: Optional[float] = Field(None, ge=-1, le=1, description="آخر قراءة رطوبة؛ null = لا قراءة. القيم غير الفيزيائية تؤدي إلى فحص الحساس")
    sensor_age_min: Optional[float] = Field(0, ge=-1440, le=100000, description="عمر القراءة بالدقائق عند القرار؛ null = غير معروف")
    sensor_quality: Literal["ok", "missing", "invalid_range", "duplicate", "unknown"] = "ok"
    forecast_rain_mm: Optional[float] = Field(None, ge=0, le=300)
    forecast_et0_mm: Optional[float] = Field(None, ge=0, le=25)
    forecast_temperature_c: Optional[float] = Field(None, ge=-20, le=60)
    use_stored_forecast: bool = Field(False, description="املأ قيم الطقس الغائبة من توقع المحاكاة المحفوظ لذلك اليوم إن وُجد")
    daily_budget_l: Optional[float] = Field(None, ge=0, le=100000, description="الماء المتاح للموقع اليوم؛ افتراضيًا 160 لترًا من config.json")
    other_zone_request_l: float = Field(0, ge=0, le=100000, description="طلب المنطقة الأخرى من نفس الميزانية")

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {
        "zone_id": "Z02", "decision_date": "2025-07-15", "pre_vwc": 0.098, "sensor_age_min": 30,
        "sensor_quality": "ok", "forecast_rain_mm": 0, "forecast_et0_mm": 9.4, "forecast_temperature_c": 37,
        "daily_budget_l": 160, "other_zone_request_l": 60}})


class Scenario(_Base):
    zone_id: ZoneId
    decision_date: date
    pre_vwc: float = Field(..., ge=0, le=0.4)
    volume_l: float = Field(..., ge=0, le=200)
    duration_min: Optional[float] = Field(None, gt=0, le=300, description="إن غابت = الحجم ÷ 2 لتر/دقيقة")
    forecast_rain_mm: Optional[float] = Field(None, ge=0, le=300, description="إن غاب يؤخذ من توقع المحاكاة لذلك اليوم")
    forecast_et0_mm: Optional[float] = Field(None, ge=0, le=25)
    forecast_temperature_c: Optional[float] = Field(None, ge=-20, le=60)
    label: Optional[str] = Field(None, max_length=40)


class SimulationRequest(_Base):
    scenarios: list[Scenario] = Field(..., min_length=1, max_length=6)
    sweep: bool = Field(True, description="أضف منحنى الاستجابة 0–80 لترًا للسيناريو الأول")

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"scenarios": [
        {"zone_id": "Z02", "decision_date": "2025-07-15", "pre_vwc": 0.10, "volume_l": 40, "label": "40 لترًا"},
        {"zone_id": "Z02", "decision_date": "2025-07-15", "pre_vwc": 0.10, "volume_l": 70, "label": "70 لترًا"}]}})


class HistoryQuery(_Base):
    source: Literal["all", "simulation", "app"] = "all"
    zone_id: Optional[ZoneId] = None
    action: Optional[Literal["IRRIGATE", "DEFER", "CHECK_SENSOR"]] = None
    status: Optional[Literal["not_executed", "completed", "no_flow", "low_flow", "stuck_open", "label_missing", "app_only"]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    search: Optional[str] = Field(None, max_length=40)
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)

    @model_validator(mode="after")
    def _order(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from بعد date_to")
        return self


class V2PredictRequest(_Base):
    """تنبؤ النموذج الثاني لمنطقة ويوم من مجموعة v2، مع إمكانية تغيير بعض المدخلات (سيناريو)."""
    zone_id: Literal["Z001", "Z002", "Z003", "Z004"]
    decision_date: date = Field(..., description="يوم القرار YYYY-MM-DD ضمن 2024-10-05 — 2026-10-04 (القرار 06:00 UTC)")
    before_VWC_pct: Optional[float] = Field(None, ge=0, le=60, description="الرطوبة الحالية %؛ غيابها = استخدام قيمة الملف")
    before_missing_reading: bool = Field(False, description="محاكاة فقد قراءة الحساس الحالية")
    planned_volume_L: Optional[float] = Field(None, ge=0, le=100000)
    planned_duration_min: Optional[float] = Field(None, ge=0, le=1440)
    et0_forecast_24h_mm: Optional[float] = Field(None, ge=0, le=25)
    rain_forecast_24h_mm: Optional[float] = Field(None, ge=0, le=300)
    air_temp_observed_C: Optional[float] = Field(None, ge=-20, le=60)
    humidity_observed_pct: Optional[float] = Field(None, ge=0, le=100)

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {
        "zone_id": "Z004", "decision_date": "2026-07-01", "planned_volume_L": 1500}})
