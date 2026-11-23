"""نقاط API للمحاصيل الأربع (نموذج مستقل) ولنتائج معالجة الصور (image_processing — قراءة فقط)."""
from __future__ import annotations

import csv
import datetime as dt
import json
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from backend.api.router import ApiError, endpoint
from backend.app.config import DATA_NOTICE, IMAGE_PROCESSING_OUT
from backend.services import crops_service

CropZone = Literal["Z001", "Z002", "Z003", "Z004"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CropOverrides(_M):
    before_VWC_pct: Optional[float] = Field(None, ge=0, le=60, description="الرطوبة الحالية %؛ غيابها = قراءة الملف لذلك اليوم")
    sensor_missing: bool = Field(False, description="محاكاة فقد قراءة الحساس")
    et0_forecast_24h_mm: Optional[float] = Field(None, ge=0, le=25)
    rain_forecast_24h_mm: Optional[float] = Field(None, ge=0, le=300)
    air_temp_observed_C: Optional[float] = Field(None, ge=-20, le=60)
    humidity_observed_pct: Optional[float] = Field(None, ge=0, le=100)


class CropRecommendRequest(CropOverrides):
    """طلب توصية ري لمنطقة من المحاصيل الأربع في يوم من بيانات الملف، مع تعديل المدخلات اختياريًا."""
    zone_id: CropZone
    decision_date: dt.date = Field(..., description="يوم ضمن 2024-10-05 — 2026-10-04 (القرار 06:00 UTC)")
    p_override: Optional[float] = Field(None, ge=0.1, le=0.8, description="نسبة الاستنزاف المسموح p؛ افتراضيًا من FAO-56 الجدول 22")
    target_vwc_pct: Optional[float] = Field(None, ge=0, le=60, description="الرطوبة المستهدفة %؛ افتراضيًا السعة الحقلية")
    daily_budget_l: Optional[float] = Field(None, ge=0, le=1_000_000, description="حد أعلى للماء المتاح لهذه المنطقة اليوم (لتر)")
    save: bool = Field(True, description="احفظ التوصية في app_crop_recommendations")

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"zone_id": "Z004", "decision_date": "2026-07-01"}})


class CropScenario(CropOverrides):
    volume_l: float = Field(..., ge=0, le=200_000)
    label: Optional[str] = Field(None, max_length=40)


class CropSimulationRequest(_M):
    zone_id: CropZone
    decision_date: dt.date
    scenarios: list[CropScenario] = Field(..., min_length=1, max_length=6)

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {"zone_id": "Z002", "decision_date": "2026-08-01",
        "scenarios": [{"volume_l": 0, "label": "دون ري"}, {"volume_l": 6000}, {"volume_l": 15000}]}})


class DateQ(_M):
    date: Optional[dt.date] = Field(None, description="YYYY-MM-DD؛ افتراضيًا آخر يوم في البيانات")


class SplitQ(_M):
    split: Literal["train", "validation", "test"] = "test"


class CropHistoryQ(_M):
    zone_id: Optional[CropZone] = None
    action: Optional[Literal["IRRIGATE", "DEFER", "CHECK_SENSOR"]] = None
    source: Optional[Literal["recommend", "simulation"]] = None
    date_from: Optional[dt.date] = None
    date_to: Optional[dt.date] = None
    search: Optional[str] = Field(None, max_length=40)
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)

    @model_validator(mode="after")
    def _order(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from بعد date_to")
        return self


def _rid(request: Request):
    return getattr(request.state, "request_id", None)


def _need_model():
    if not crops_service.available():
        raise ApiError(503, "crops_model_not_available", "نموذج المحاصيل غير متاح؛ شغّلي: python ml/training/train_crops_model.py")


@endpoint("/api/crops/zones", "GET", summary="المناطق الأربع والمحاصيل وخصائصها ومعاملات FAO-56", tag="crops")
async def crop_zones():
    return {"items": await run_in_threadpool(crops_service.zones), "range": await run_in_threadpool(crops_service.date_range),
            "model": crops_service.status(), "data_notice": DATA_NOTICE}


@endpoint("/api/crops/dashboard", "GET", summary="حالة المناطق الأربع ليوم: الرطوبة، القرار، الكمية، التنبؤ، الاستهلاك", tag="crops", query=DateQ)
async def crop_dashboard(q: DateQ):
    _need_model()
    try:
        return await run_in_threadpool(crops_service.dashboard, q.date.isoformat() if q.date else None)
    except ValueError as e:
        raise ApiError(422, "date_out_of_range", str(e))


@endpoint("/api/crops/recommend", "POST", summary="توصية ري لمحصول: FAO-56 + الكمية والمدة + تنبؤ النموذج بالرطوبة بعد 6 ساعات",
          tag="crops", body=CropRecommendRequest,
          description="يحسب الاستنزاف وحد الإجهاد RAW بقيم المنطقة من الملف، ويقرر IRRIGATE/DEFER/CHECK_SENSOR، ويحسب كمية إعادة الملء "
                      "ومدتها، ثم يتنبأ نموذج المحاصيل بالرطوبة بعد 6 ساعات دون ري وبالكمية المقترحة. تُحفظ في app_crop_recommendations.")
async def crop_recommend(body: CropRecommendRequest, request: Request):
    _need_model()
    ov = body.model_dump(include={"before_VWC_pct", "sensor_missing", "et0_forecast_24h_mm", "rain_forecast_24h_mm",
                                  "air_temp_observed_C", "humidity_observed_pct"})
    try:
        res = await run_in_threadpool(crops_service.recommend, body.zone_id, body.decision_date.isoformat(), ov,
                                      body.p_override, body.target_vwc_pct, body.daily_budget_l)
    except KeyError as e:
        raise ApiError(404, "crop_record_not_found", str(e.args[0]))
    if body.save:
        res["saved_id"] = await run_in_threadpool(crops_service.save, res, "recommend", _rid(request))
    return res


@endpoint("/api/crops/simulate", "POST", summary="محاكاة حتى 6 سيناريوهات ري لمحصول ومنحنى الاستجابة", tag="crops",
          body=CropSimulationRequest, description="كل سيناريو يُتنبأ له بالنموذج وبمعادلة موازنة الماء، ويُحفظ في app_crop_recommendations (source=simulation).")
async def crop_simulate(body: CropSimulationRequest, request: Request):
    _need_model()
    try:
        return await run_in_threadpool(crops_service.simulate, body.zone_id, body.decision_date.isoformat(),
                                       [s.model_dump() for s in body.scenarios], _rid(request))
    except KeyError as e:
        raise ApiError(404, "crop_record_not_found", str(e.args[0]))


@endpoint("/api/crops/metrics", "GET", summary="أداء نموذج المحاصيل مقابل خطوط الأساس (من التدريب الفعلي)", tag="crops")
async def crop_metrics():
    _need_model()
    return await run_in_threadpool(crops_service.metrics)


@endpoint("/api/crops/predictions", "GET", summary="المتنبأ مقابل الفعلي لنموذج المحاصيل", tag="crops", query=SplitQ)
async def crop_predictions(q: SplitQ):
    _need_model()
    return {"split": q.split, "items": await run_in_threadpool(crops_service.predictions, q.split)}


@endpoint("/api/crops/history", "GET", summary="سجل توصيات ومحاكاة المحاصيل الأربع مع البحث والتصفية", tag="history", query=CropHistoryQ)
async def crop_history(q: CropHistoryQ):
    return await run_in_threadpool(crops_service.history, q.zone_id, q.action, q.source,
                                   q.date_from.isoformat() if q.date_from else None, q.date_to.isoformat() if q.date_to else None,
                                   q.search, q.limit, q.offset)


# ------------------------------------------------------------------ معالجة الصور (مخرجات image_processing)
@endpoint("/api/site/image-analysis", "GET", summary="نتائج معالجة الصور الميدانية (رمادي، قناع أخضر، حواف، مؤشر الغطاء الأخضر)", tag="site",
          description="يقرأ image_processing/output/report.csv و summary.json كما هي. مؤشر الأخضر لوني تقريبي (ExG > 0.10)، ليس قياسًا زراعيًا.")
async def image_analysis():
    rep, summ = IMAGE_PROCESSING_OUT / "report.csv", IMAGE_PROCESSING_OUT / "summary.json"
    if not rep.exists():
        raise ApiError(404, "image_processing_not_run", "شغّلي: py image_processing/main.py لإنتاج المخرجات")
    with open(rep, encoding="utf-8-sig", newline="") as f:
        items = []
        for r in csv.DictReader(f):
            rel = r["file"].replace("\\", "/")
            folder, stem = rel.rsplit("/", 1)[0] if "/" in rel else "", rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            base = f"/media-processing/processed/{folder + '/' if folder else ''}{stem}/"
            num = {k: float(v) for k, v in r.items() if k not in ("file", "group", "format", "read_with") and v not in ("", None)}
            items.append({"file": rel, "id": stem, "group": r.get("group"), "format": r.get("format"), "read_with": r.get("read_with"),
                          **num, "images": {k: base + f"{k}.png" for k in ("gray", "green_mask", "edges")} | {"resized": base + "resized_512.png"}})
    summary = json.loads(summ.read_text(encoding="utf-8")) if summ.exists() else {}
    return {"items": items, "summary": {k: summary.get(k) for k in ("processed", "images_found", "failed", "heic_backend",
                                                                      "originals_unchanged", "batch_shape")},
            "method_ar": "Excess Green: ExG = 2g − r − b على الإحداثيات اللونية المطبّعة، والبكسل نباتي إن ExG > 0.10. "
                         "مؤشر لوني تقريبي؛ يحسب الأجسام الخضراء غير النباتية ويخطئ في الظلال.",
            "source": "image_processing/output (مولدة من الصور الأصلية دون تعديلها)"}
