"""إنشاء تطبيق ريّان (FastAPI): المسارات، تسجيل الطلبات، معالجة الأخطاء، تحميل النماذج عند التشغيل، وخدمة الواجهة."""
from __future__ import annotations

import html
import json
import logging
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from backend.api import routes as _routes  # noqa: F401  (يسجل النقاط)
from backend.api import routes_crops as _routes_crops  # noqa: F401  (نقاط المحاصيل الأربع ومعالجة الصور)
from backend.api.router import ApiError, api_router, validation_details
from backend.app.config import DATA_NOTICE, FRONTEND_DIST, IMAGES, IMAGE_PROCESSING_OUT
from backend.database.db import ensure_schema, log_request_end, log_request_start
from backend.services import ml_service

log = logging.getLogger("rayyan")
VERSION = "2.0.0"
TAGS = [
    {"name": "system", "description": "حالة الخادم والنماذج وقاعدة البيانات"},
    {"name": "dashboard", "description": "لوحة التحكم واستهلاك المياه"},
    {"name": "decision", "description": "قرار الري لنظام البرمودا (rule_v1)"},
    {"name": "simulation", "description": "محاكاة سيناريوهات الري بالنموذج"},
    {"name": "ml", "description": "نموذج البرمودا: التنبؤ والمقاييس"},
    {"name": "crops", "description": "المحاصيل الأربع: التوصية (FAO-56) ونموذج الرطوبة بعد 6 ساعات"},
    {"name": "history", "description": "سجل القرارات والتنبؤات"},
    {"name": "monitoring", "description": "التدفق والتنبيهات"},
    {"name": "site", "description": "الموقع والمناطق والصور"},
    {"name": "v2", "description": "النموذج الثاني الأصلي (مجموعة v2) — محفوظ كما هو للمقارنة"},
]


class RequestLog(BaseHTTPMiddleware):
    """يسجل كل طلب /api في app_requests مع المدة والحالة ونص الخطأ إن وُجد."""

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api") or request.url.path.startswith(("/api/swagger", "/api/redoc")):
            return await call_next(request)
        t0 = time.perf_counter()
        rid = log_request_start(request.method, request.url.path, request.url.query or "")
        request.state.request_id = rid
        try:
            response = await call_next(request)
        except Exception as e:  # يصل هنا فقط إن فشل معالج الأخطاء نفسه
            log_request_end(rid, 500, (time.perf_counter() - t0) * 1000, repr(e))
            raise
        err = getattr(request.state, "error", None)
        log_request_end(rid, response.status_code, (time.perf_counter() - t0) * 1000, err)
        response.headers["X-Request-ID"] = str(rid)
        return response


def _err(request: Request, status: int, code: str, message: str, details=None) -> JSONResponse:
    request.state.error = f"{code}: {message}"
    return JSONResponse({"error": {"code": code, "message": message, "details": details}}, status_code=status)


async def api_error(request: Request, exc: ApiError):
    return _err(request, exc.status, exc.code, exc.message, exc.details)


async def request_validation(request: Request, exc: RequestValidationError):
    errors = list(exc.errors())
    if any(e["type"] == "json_invalid" for e in errors):
        return _err(request, 400, "invalid_json", "جسم الطلب ليس JSON صالحًا")
    return _err(request, 422, "validation_error", "المدخلات غير صالحة", validation_details(errors))


async def server_error(request: Request, exc: Exception):
    request.state.error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    log.exception("خطأ غير متوقع في %s", request.url.path)
    return JSONResponse({"error": {"code": "internal_error", "message": "خطأ داخلي في الخادم؛ سُجل في app_requests.",
                                   "details": request.state.error}}, status_code=500)


async def not_found(request: Request, exc):
    if request.url.path.startswith("/api"):
        return _err(request, 404, "not_found", f"المسار غير موجود: {request.url.path}")
    return await spa(request)


@asynccontextmanager
async def lifespan(app):
    ensure_schema()
    ml_service.load()  # نموذج البرمودا
    from backend.services import crops_service, v2_service
    v2_service.load()      # النموذج الثاني الأصلي إن وُجد
    crops_service.load()   # نموذج المحاصيل الأربع (المختار على التحقق)
    st = ml_service.status()
    log.info("نموذج البرمودا: %s (%s) — نموذج المحاصيل: %s", st["version"], st["source"], crops_service.status().get("version"))
    yield


def docs_page(request: Request):
    spec = request.app.openapi()
    tag_ar = {t["name"]: t["description"].split("؛")[0].split(":")[0] for t in TAGS}
    parts = []
    for path, ops in spec["paths"].items():
        for m, op in ops.items():
            params = "".join(f"<li><code>{html.escape(p['name'])}</code> ({p['in']}{'، مطلوب' if p.get('required') else ''}) — "
                             f"{html.escape(p.get('description') or '')}</li>" for p in op.get("parameters", []))
            body = ""
            ref = ((op.get("requestBody") or {}).get("content", {}).get("application/json", {}).get("schema", {}).get("$ref", ""))
            if ref:
                name = ref.split("/")[-1]
                sch = spec["components"]["schemas"].get(name, {})
                ex = sch.get("example")
                body = (f"<details><summary>مخطط الطلب {name}</summary><pre>{html.escape(json.dumps(sch, ensure_ascii=False, indent=1))}</pre></details>"
                        + (f"<p>مثال:</p><pre>{html.escape(json.dumps(ex, ensure_ascii=False, indent=1))}</pre>" if ex else ""))
            tag = (op.get("tags") or [""])[0]
            parts.append(f"""<section><h3><span class="m {m}">{m.upper()}</span> <code>{html.escape(path)}</code>
              <small>{html.escape(tag_ar.get(tag, tag))}</small></h3><p><b>{html.escape(op.get('summary', ''))}</b></p>
              <p>{html.escape(op.get('description') or '')}</p>{'<ul>' + params + '</ul>' if params else ''}{body}
              <p class="r">الاستجابات: {'، '.join(f"{k} {html.escape(v.get('description', ''))}" for k, v in op['responses'].items())}</p></section>""")
    page = f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>RAYYAN API</title>
    <style>body{{font-family:Tahoma,system-ui;max-width:980px;margin:2rem auto;padding:0 1rem;color:#16302a;line-height:1.7}}
    section{{border:1px solid #cdd8d1;border-radius:10px;padding:.8rem 1rem;margin:.8rem 0}}
    code,pre{{direction:ltr;unicode-bidi:embed}}pre{{background:#f3f6f4;padding:.6rem;overflow:auto;text-align:left}}
    .m{{font:600 .8rem monospace;padding:.15rem .5rem;border-radius:5px;color:#fff}}.get{{background:#2a7a9e}}.post{{background:#3d7a4f}}
    .note{{border-right:4px solid #c0832e;padding-right:.8rem}}small{{color:#5d6f67}}.r{{font-size:.85rem;color:#5d6f67}}</style></head>
    <body><h1>توثيق واجهة RAYYAN البرمجية (FastAPI)</h1><p class="note">{DATA_NOTICE}</p>
    <p>تجربة تفاعلية: <a href="/api/swagger">Swagger UI</a> · <a href="/api/redoc">ReDoc</a> · المخطط: <a href="/api/openapi.json">/api/openapi.json</a>.
    الأخطاء بصيغة <code>{{"error":{{"code","message","details"}}}}</code>. كل طلب يُسجل في جدول <code>app_requests</code>.</p>
    {''.join(parts)}</body></html>"""
    return HTMLResponse(page)


async def spa(request: Request):
    if request.url.path.startswith("/api"):
        return _err(request, 404, "not_found", f"المسار غير موجود: {request.url.path}")
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<h1>الواجهة غير مبنية</h1><p>شغّل <code>node frontend/build.mjs</code>.</p>", status_code=503)


def create_app() -> FastAPI:
    app = FastAPI(
        title="RAYYAN Smart Irrigation API", version=VERSION, lifespan=lifespan, openapi_tags=TAGS,
        description="واجهة ريّان البرمجية (FastAPI). " + DATA_NOTICE,
        openapi_url="/api/openapi.json", docs_url="/api/swagger", redoc_url="/api/redoc",
    )
    app.add_middleware(RequestLog)
    # للتطوير فقط: واجهة تعمل من خادم آخر محلي (الإنتاج يخدمها نفس الخادم)
    app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(127\.0\.0\.1|localhost)(:\d+)?",
                       allow_methods=["GET", "POST"], allow_headers=["*"], expose_headers=["X-Request-ID"])
    app.add_exception_handler(ApiError, api_error)
    app.add_exception_handler(RequestValidationError, request_validation)
    app.add_exception_handler(Exception, server_error)
    app.add_exception_handler(404, not_found)

    app.include_router(api_router)
    app.add_api_route("/api/docs", docs_page, methods=["GET"], include_in_schema=False)
    app.mount("/media", StaticFiles(directory=str(IMAGES)), name="media")
    if IMAGE_PROCESSING_OUT.exists():  # مخرجات image_processing — قراءة فقط
        app.mount("/media-processing", StaticFiles(directory=str(IMAGE_PROCESSING_OUT)), name="media-processing")
    if (FRONTEND_DIST / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
    app.add_route("/", spa)
    app.add_route("/{path:path}", spa)
    return app
