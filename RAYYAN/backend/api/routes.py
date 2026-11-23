"""نقاط API لريّان. كل حسابات ML والقرار تتم هنا في الخادم؛ الواجهة تعرض النتائج فقط."""
from __future__ import annotations

import datetime as dt
import json
from typing import Any, Optional

from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request

from backend.api.router import ApiError, endpoint
from backend.app.config import DATA_NOTICE, METRICS_PATH, MODEL_DIR
from backend.database.db import connect, one, rows
from backend.models.schemas import HistoryQuery, PredictRequest, RecommendRequest, SimulationRequest, V2PredictRequest
from backend.services import dashboard, history, ml_service, simulation, site, v2_service
from backend.services.decision_engine import Forecast, SensorReading
from backend.services.flow_monitor import all_alerts, analyse_event
from backend.services.recommendation import Inputs, build, replay, save
from backend.services.reference import zone, zone_profiles


def _rid(request: Request) -> Optional[int]:
    return getattr(request.state, "request_id", None)


def _metrics() -> dict[str, Any]:
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ النظام
@endpoint("/api/health", "GET", summary="حالة الخادم والنموذج وقاعدة البيانات", tag="system")
async def health():
    con = connect()
    try:
        n = one(con, "select count(*) n from decisions")["n"]
    finally:
        con.close()
    return {"status": "ok", "model": ml_service.status(), "v2_model": v2_service.status(), "database": {"ok": True, "decisions": n},
            "data_notice": DATA_NOTICE}


class DateQuery(BaseModel):
    date: Optional[dt.date] = Field(None, description="يوم من المحاكاة YYYY-MM-DD؛ افتراضيًا آخر يوم")


@endpoint("/api/dashboard", "GET", summary="لوحة التحكم ليوم من المحاكاة", tag="dashboard", query=DateQuery,
          description="حالة النظام، ولكل منطقة: الرطوبة وقت القرار، العتبة، الهدف، قرار المحرك، الكمية المقترحة، "
                      "الرطوبة المتوقعة بعد الري من النموذج، آخر رية، استهلاك 30 يومًا، اتجاه الرطوبة، والتنبيهات.")
async def get_dashboard(q: DateQuery):
    try:
        return await run_in_threadpool(dashboard.build, q.date)
    except ValueError as e:
        raise ApiError(422, "date_out_of_range", str(e))


@endpoint("/api/water/usage", "GET", summary="استهلاك المياه المخطط مقابل المنفذ شهريًا لكل منطقة", tag="dashboard")
async def water_usage():
    return await run_in_threadpool(dashboard.water_usage)


class AlertQuery(BaseModel):
    limit: int = Field(50, ge=1, le=500)


@endpoint("/api/alerts", "GET", summary="تنبيهات القواعد (تدفق، موازنة، حساس) مع نتيجة الفحص المحاكى", tag="monitoring", query=AlertQuery)
async def alerts(q: AlertQuery):
    return {"items": await run_in_threadpool(all_alerts, q.limit), "data_notice": DATA_NOTICE}


@endpoint("/api/events/{event_id}/flow", "GET", summary="سلسلة التدفق لرية وتحليلها: المخطط مقابل المنفذ والتنبيهات", tag="monitoring",
          params=[{"name": "event_id", "description": "مثل E20240415Z02"}])
async def event_flow(event_id: str):
    try:
        return await run_in_threadpool(analyse_event, event_id)
    except KeyError:
        raise ApiError(404, "event_not_found", f"لا توجد رية بالمعرف {event_id}")


# ------------------------------------------------------------------ المناطق والموقع
@endpoint("/api/zones", "GET", summary="المنطقتان وخصائصهما (zone_profiles)", tag="site")
async def zones():
    return {"items": [z.__dict__ | {"root_mm": z.root_mm} for z in zone_profiles().values()], "data_notice": DATA_NOTICE}


@endpoint("/api/zones/{zone_id}", "GET", summary="منطقة واحدة", tag="site", params=[{"name": "zone_id", "description": "Z01 أو Z02"}])
async def zone_one(zone_id: str):
    try:
        z = zone(zone_id)
    except KeyError:
        raise ApiError(404, "zone_not_found", f"لا توجد منطقة {zone_id}")
    return z.__dict__ | {"root_mm": z.root_mm}


@endpoint("/api/site", "GET", summary="الموقع والمناطق والأجهزة وأصل البيانات والفجوات الميدانية", tag="site")
async def site_info():
    return await run_in_threadpool(site.site_info)


@endpoint("/api/site/gallery", "GET", summary="الصور الميدانية المرفقة مع مصدر كل مجموعة", tag="site")
async def gallery():
    return {"items": site.gallery(), "media_base": "/media/"}


# ------------------------------------------------------------------ ML والقرار
@endpoint("/api/predict", "POST", summary="تنبؤ النموذج بتغير رطوبة التربة لخطة ري", tag="ml", body=PredictRequest,
          description="يعيد delta_vwc المتوقع والرطوبة بعد الري، مع تحذير إذا خرجت المدخلات عن نطاق التدريب.")
async def predict(body: PredictRequest):
    z = zone(body.zone_id)
    dur = body.planned_duration_min or body.planned_volume_l / z.nominal_flow_l_min
    x = ml_service.build_features(body.pre_vwc, body.planned_volume_l, dur, z.root_depth_m, z.area_m2,
                                  body.forecast_rain_mm, body.forecast_et0_mm, body.decision_date)
    p = await run_in_threadpool(ml_service.predict_one, x)
    return {**p, "features": x, "target_vwc": z.field_capacity_vwc, "data_notice": DATA_NOTICE}


@endpoint("/api/irrigation/recommend", "POST", summary="قرار الري (IRRIGATE / DEFER / CHECK_SENSOR) مع الأسباب والكمية", tag="decision",
          body=RecommendRequest,
          description="يشغّل فحص الحساس (قاعدة أمان مستقلة) ثم قواعد ريّان rule_v1، ويحسب الكمية والمدة ضمن حد الرية والميزانية، "
                      "ثم يتنبأ النموذج بالرطوبة بعد الري. تُحفظ التوصية في app_recommendations. لا يُرسل أي أمر لصمام.")
async def recommend(body: RecommendRequest, request: Request):
    rain, et0, temp = body.forecast_rain_mm, body.forecast_et0_mm, body.forecast_temperature_c
    filled = []
    if body.use_stored_forecast:
        fc = simulation.forecast_for(body.decision_date)
        if rain is None and fc["rain_mm"] is not None: rain = fc["rain_mm"]; filled.append("forecast_rain_mm")
        if et0 is None and fc["et0_mm"] is not None: et0 = fc["et0_mm"]; filled.append("forecast_et0_mm")
        if temp is None and fc["temperature_c"] is not None: temp = fc["temperature_c"]; filled.append("forecast_temperature_c")
    quality = "ok" if body.sensor_quality == "ok" else body.sensor_quality
    inp = Inputs(body.zone_id, body.decision_date, SensorReading(body.pre_vwc, body.sensor_age_min, quality),
                 Forecast(rain, et0, temp), body.daily_budget_l, body.other_zone_request_l)
    res = await run_in_threadpool(build, inp)
    if filled:
        res["warnings"].append("مُلئت من توقع المحاكاة المحفوظ: " + "، ".join(filled))
    res["inputs"] = {"decision_date": body.decision_date.isoformat(), "pre_vwc": body.pre_vwc, "sensor_age_min": body.sensor_age_min,
                     "sensor_quality": body.sensor_quality, "forecast_rain_mm": rain, "forecast_et0_mm": et0,
                     "forecast_temperature_c": temp, "daily_budget_l": body.daily_budget_l, "other_zone_request_l": body.other_zone_request_l}
    res["recommendation_id"] = await run_in_threadpool(save, res, inp, "user_input", _rid(request))
    res["valve_command"] = None
    res["valve_note"] = "لا يوجد صمام أو متحكم متصل؛ التوصية للعرض فقط ولا يُنفذ أي تشغيل."
    return res


class ReplayQuery(BaseModel):
    save: bool = Field(False, description="احفظ نتيجة إعادة التشغيل في app_recommendations")


@endpoint("/api/irrigation/replay/{decision_id}", "GET", summary="إعادة تشغيل قرار محفوظ بمدخلاته الأصلية ومقارنته بقرار المحاكي",
          tag="decision", query=ReplayQuery, params=[{"name": "decision_id", "description": "مثل D20250715Z02"}])
async def replay_decision(decision_id: str, q: ReplayQuery, request: Request):
    try:
        res = await run_in_threadpool(replay, decision_id)
    except KeyError:
        raise ApiError(404, "decision_not_found", f"لا يوجد قرار {decision_id}")
    if q.save:
        from backend.services.recommendation import stored_inputs
        inp, _ = stored_inputs(decision_id)
        res["recommendation_id"] = await run_in_threadpool(save, res, inp, "replay_decision", _rid(request), decision_id)
    return res


@endpoint("/api/simulation/run", "POST", summary="محاكاة سيناريوهات ري ومقارنتها", tag="simulation", body=SimulationRequest,
          description="لكل سيناريو: الرطوبة المتوقعة من النموذج، والفرق، والماء المستخدم، والتقريب الخطي للمقارنة. "
                      "تُحفظ السيناريوهات في app_simulations. النتائج ليست قياسات ميدانية.")
async def simulation_run(body: SimulationRequest, request: Request):
    try:
        return await run_in_threadpool(simulation.run, [s.model_dump() for s in body.scenarios], body.sweep, _rid(request))
    except ValueError as e:
        raise ApiError(422, "simulation_input", str(e))


class ForecastQuery(BaseModel):
    date: dt.date = Field(..., description="YYYY-MM-DD")


@endpoint("/api/simulation/defaults", "GET", summary="القيم الافتراضية لسيناريو في تاريخ: التوقع المحفوظ وآخر رطوبة لكل منطقة",
          tag="simulation", query=ForecastQuery)
async def simulation_defaults(q: ForecastQuery):
    fc = simulation.forecast_for(q.date)
    con = connect()
    try:
        tag = q.date.strftime("%Y%m%d")
        pre = {r["zone_id"]: r["usable_vwc"] for r in rows(con, """select d.zone_id, m.usable_vwc from decisions d
            left join measurements_clean m on m.sample_id = d.input_sample_id where d.decision_id like ?""", (f"D{tag}%",))}
    finally:
        con.close()
    return {"date": q.date.isoformat(), "forecast": fc, "pre_vwc_by_zone": pre,
            "forecast_available": fc["rain_mm"] is not None, "source": "weather_forecasts + decisions (simulation)"}


class LimitQuery(BaseModel):
    limit: int = Field(30, ge=1, le=500)


@endpoint("/api/simulation/history", "GET", summary="آخر سيناريوهات المحاكاة المحفوظة", tag="simulation", query=LimitQuery)
async def simulation_history(q: LimitQuery):
    con = connect()
    try:
        return {"items": rows(con, "select * from app_simulations order by simulation_id desc limit ?", (q.limit,))}
    finally:
        con.close()


# ------------------------------------------------------------------ أداء النموذج
@endpoint("/api/model/metrics", "GET", summary="مقاييس النموذج الفعلية من التدريب (MAE/RMSE/R²) ومقارنة خطوط الأساس", tag="ml")
async def model_metrics():
    m = _metrics()
    m.pop("feature_ranges", None)
    m["runtime"] = ml_service.status()
    wb = MODEL_DIR / "workbook_experiment.json"
    m["workbook_experiment"] = json.loads(wb.read_text(encoding="utf-8")) if wb.exists() else None
    m["data_notice"] = DATA_NOTICE
    return m


@endpoint("/api/model/importance", "GET", summary="أهمية المدخلات: Impurity و Permutation", tag="ml")
async def model_importance():
    m = _metrics()
    return {**m["importance"], "feature_labels_ar": ml_service.FEATURE_AR}


class PredQuery(BaseModel):
    split: Optional[str] = Field("test", pattern="^(train|validation|test)$")


@endpoint("/api/model/predictions", "GET", summary="المتنبأ مقابل الفعلي لكل عملية ري مؤهلة", tag="ml", query=PredQuery)
async def model_predictions(q: PredQuery):
    con = connect()
    try:
        items = rows(con, """select p.*, d.issued_at, o.confounding_flags from app_model_predictions p
            join decisions d using(decision_id) left join event_outcomes o on o.decision_id = p.decision_id
            where p.split = ? order by d.issued_at""", (q.split,))
    finally:
        con.close()
    return {"split": q.split, "items": items,
            "note": "out_of_sample=1 للتحقق (نموذج 2024) والاختبار (النموذج المستخدم)؛ التدريب داخل العينة."}


@endpoint("/api/model/decision-engine", "GET", summary="نتيجة التحقق من محرك القرار مقابل قرارات المحاكي", tag="decision")
async def decision_engine_validation():
    p = MODEL_DIR / "decision_engine_validation.json"
    if not p.exists():
        raise ApiError(404, "not_generated", "شغّل ml/evaluation/validate_decision_engine.py أولًا")
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ السجل
@endpoint("/api/history", "GET", summary="سجل العمليات مع البحث والتصفية", tag="history", query=HistoryQuery,
          description="يجمع قرارات المحاكاة ونتائجها (decisions ← irrigation_events ← event_outcomes) وتوصيات التطبيق المحفوظة.")
async def history_list(q: HistoryQuery):
    return await run_in_threadpool(history.query, q.source, q.zone_id, q.action, q.date_from, q.date_to, q.status,
                                   q.search, q.limit, q.offset)


@endpoint("/api/history/requests", "GET", summary="سجل طلبات الـAPI (app_requests)", tag="history", query=LimitQuery)
async def request_log(q: LimitQuery):
    return {"items": await run_in_threadpool(history.operations_log, q.limit)}


@endpoint("/api/history/{decision_id}", "GET", summary="تفاصيل عملية: القرار والتنفيذ والنتيجة والتدفق", tag="history",
          params=[{"name": "decision_id", "description": "مثل D20240415Z02"}])
async def history_detail(decision_id: str):
    try:
        return await run_in_threadpool(history.detail, decision_id)
    except KeyError:
        raise ApiError(404, "decision_not_found", f"لا يوجد قرار {decision_id}")


# ------------------------------------------------------------------ النموذج الثاني (مجموعة v2، أربع مناطق)
def _v2_required():
    if not v2_service.available():
        raise ApiError(404, "v2_not_available", "مجموعة v2 أو نموذجها غير متاحين؛ شغّلي scripts/run.py --rebuild")


@endpoint("/api/v2/overview", "GET", summary="مجموعة v2: المناطق الأربع، التقسيم، السيناريوهات المحقونة، ملاحظات الملف", tag="v2")
async def v2_overview():
    _v2_required()
    return await run_in_threadpool(v2_service.overview)


@endpoint("/api/v2/metrics", "GET", summary="مقاييس النموذج الثاني مقابل خطوط الأساس (المحسوبة والمبلغ عنها في الملف)", tag="v2")
async def v2_metrics():
    _v2_required()
    return v2_service.metrics()


class V2PredQuery(BaseModel):
    split: str = Field("test", pattern="^(train|validation|test)$")


@endpoint("/api/v2/predictions", "GET", summary="المتنبأ مقابل الفعلي للنموذج الثاني", tag="v2", query=V2PredQuery)
async def v2_predictions(q: V2PredQuery):
    _v2_required()
    return {"split": q.split, "items": await run_in_threadpool(v2_service.predictions, q.split)}


class V2DefaultsQuery(BaseModel):
    zone_id: str = Field(..., pattern="^Z00[1-4]$")
    date: dt.date


@endpoint("/api/v2/defaults", "GET", summary="مدخلات النموذج الثاني المسجلة لمنطقة ويوم", tag="v2", query=V2DefaultsQuery)
async def v2_defaults(q: V2DefaultsQuery):
    _v2_required()
    try:
        return await run_in_threadpool(v2_service.defaults, q.zone_id, q.date.isoformat())
    except KeyError as e:
        raise ApiError(404, "v2_record_not_found", str(e.args[0]))


@endpoint("/api/v2/predict", "POST", summary="تنبؤ النموذج الثاني بالرطوبة بعد 6 ساعات، مع تغيير المدخلات كسيناريو", tag="v2",
          body=V2PredictRequest, description="يبدأ من مدخلات اليوم المسجلة ويطبق التغييرات المرسلة فقط. يُحفظ كل تشغيل في app_v2_runs.")
async def v2_predict(body: V2PredictRequest, request: Request):
    _v2_required()
    ov = {k: v for k, v in body.model_dump(exclude={"zone_id", "decision_date", "before_missing_reading"}).items() if v is not None}
    if body.before_missing_reading:
        ov["before_VWC_pct"] = None
    try:
        res = await run_in_threadpool(v2_service.predict, body.zone_id, body.decision_date.isoformat(), ov)
    except KeyError as e:
        raise ApiError(404, "v2_record_not_found", str(e.args[0]))
    from backend.database.db import dumps, session, utcnow
    with session() as con:
        cur = con.execute("""INSERT INTO app_v2_runs(created_at, request_id, zone_id, base_event_id, changed_inputs_json,
            predicted_vwc_pct, model_version, warnings_json) VALUES (?,?,?,?,?,?,?,?)""",
            (utcnow(), _rid(request), body.zone_id, res["event_id"], dumps(res["changed_inputs"]), res["predicted_vwc_pct"],
             res["model_version"], dumps(res["warnings"])))
        res["run_id"] = cur.lastrowid
    return res
