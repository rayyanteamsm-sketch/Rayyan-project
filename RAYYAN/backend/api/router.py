"""
تسجيل نقاط API في FastAPI.

المزخرف ‎@endpoint‎ يحوّل كل دالة خدمة إلى مسار FastAPI حقيقي بتوقيع مكتوب:
  - body  ← ‎Annotated[Model, Body()]‎ (يُتحقق منه بـ Pydantic ويظهر في OpenAPI كمخطط مكوّن)
  - query ← ‎Annotated[Model, Query()]‎ (نموذج معاملات استعلام، FastAPI ≥ 0.115)
  - {param} في المسار ← ‎Annotated[str, Path()]‎
FastAPI تولّد مخطط OpenAPI وصفحات Swagger/ReDoc، وتتحقق من المدخلات قبل استدعاء الدالة.
"""
from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from typing import Annotated, Any, Awaitable, Callable, Optional

from fastapi import APIRouter, Body, Path, Query, Request
from pydantic import BaseModel
from starlette.responses import JSONResponse, Response


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        self.status, self.code, self.message, self.details = status, code, message, details


@dataclass
class Endpoint:
    path: str
    method: str
    handler: Callable[..., Awaitable[Any]]
    summary: str
    description: str
    tag: str
    body: Optional[type[BaseModel]] = None
    query: Optional[type[BaseModel]] = None
    params: list[dict[str, Any]] = field(default_factory=list)
    responses: dict[str, str] = field(default_factory=dict)


REGISTRY: list[Endpoint] = []
api_router = APIRouter()

MSG_AR = {
    "missing": "حقل مطلوب", "literal_error": "قيمة غير مسموحة", "float_parsing": "يجب أن تكون رقمًا",
    "float_type": "يجب أن تكون رقمًا", "int_parsing": "يجب أن يكون عددًا صحيحًا", "bool_parsing": "يجب أن تكون true أو false",
    "greater_than_equal": "أصغر من الحد الأدنى", "greater_than": "يجب أن تكون أكبر من الحد الأدنى",
    "less_than_equal": "أكبر من الحد الأعلى", "less_than": "يجب أن تكون أصغر من الحد الأعلى",
    "date_parsing": "صيغة التاريخ يجب أن تكون YYYY-MM-DD", "date_from_datetime_parsing": "صيغة التاريخ يجب أن تكون YYYY-MM-DD",
    "extra_forbidden": "حقل غير معروف", "string_too_long": "النص أطول من المسموح", "too_short": "عدد العناصر أقل من المطلوب",
    "too_long": "عدد العناصر أكثر من المسموح", "string_pattern_mismatch": "قيمة غير مسموحة", "value_error": "قيمة غير صالحة",
    "model_attributes_type": "جسم الطلب يجب أن يكون كائن JSON", "dict_type": "جسم الطلب يجب أن يكون كائن JSON",
}
_SKIP_LOC = {"body", "query", "path", "q"}


def validation_details(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """يحوّل أخطاء Pydantic/FastAPI إلى قائمة عربية: الحقل، الرسالة، النص الإنجليزي، النوع، والقيمة."""
    out = []
    for err in errors:
        loc = ".".join(str(x) for x in err.get("loc", ()) if x not in _SKIP_LOC)
        ctx = err.get("ctx") or {}
        ar = MSG_AR.get(err["type"], err["msg"])
        if err["type"] == "value_error":
            ar = str(ctx.get("error", err["msg"])).removeprefix("Value error, ")
        bound = ctx.get("ge", ctx.get("gt", ctx.get("le", ctx.get("lt"))))
        if bound is not None:
            ar += f" ({bound})"
        if err["type"] == "literal_error" and "expected" in ctx:
            ar += f": {ctx['expected']}"
        inp = err.get("input")
        out.append({"field": loc or "body", "message": ar, "message_en": err["msg"], "type": err["type"],
                    "input": inp if not isinstance(inp, (dict, list, bytes)) else None})
    return out


def _fastapi_handler(fn: Callable[..., Awaitable[Any]], path: str, body, query):
    """يبني دالة بتوقيع تفهمه FastAPI ثم يستدعي دالة الخدمة بالمعاملات التي تطلبها فقط."""
    wanted = inspect.signature(fn).parameters
    P = inspect.Parameter
    params = [P("request", P.KEYWORD_ONLY, annotation=Request)]
    if body is not None:
        params.append(P("body", P.KEYWORD_ONLY, annotation=Annotated[body, Body()]))
    if query is not None:
        params.append(P("q", P.KEYWORD_ONLY, annotation=Annotated[query, Query()]))
    for name in re.findall(r"{(\w+)}", path):
        params.append(P(name, P.KEYWORD_ONLY, annotation=Annotated[str, Path()]))

    async def handler(**kw):
        args = {k: v for k, v in kw.items() if k in wanted}
        result = await fn(**args)
        # نعيد JSONResponse مباشرة: نفس الإخراج دون كلفة jsonable_encoder على القوائم الكبيرة
        return result if isinstance(result, Response) else JSONResponse(result)

    handler.__signature__ = inspect.Signature(params)
    handler.__name__ = fn.__name__
    handler.__doc__ = fn.__doc__
    return handler


def endpoint(path: str, method: str, *, summary: str, description: str = "", tag: str,
             body: Optional[type[BaseModel]] = None, query: Optional[type[BaseModel]] = None,
             params: Optional[list[dict[str, Any]]] = None, responses: Optional[dict[str, str]] = None):
    def deco(fn: Callable[..., Awaitable[Any]]):
        h = _fastapi_handler(fn, path, body, query)
        desc = description or (fn.__doc__ or "").strip()
        resp: dict[int | str, dict[str, Any]] = {}
        if body is not None or query is not None:
            resp[422] = {"description": "مدخلات غير صالحة: {error:{code,message,details[]}}"}
        if params:
            resp[404] = {"description": "غير موجود"}
        resp[500] = {"description": "خطأ داخلي مسجل في app_requests"}
        api_router.add_api_route(path, h, methods=[method.upper()], summary=summary, description=desc, tags=[tag],
                                 responses=resp, operation_id=f"{method.lower()}_{re.sub(r'[^a-z0-9]+', '_', path.lower()).strip('_')}")
        REGISTRY.append(Endpoint(path, method.upper(), h, summary, desc, tag, body, query, params or [], responses or {}))
        return fn
    return deco


def openapi(version: str = "2.0.0") -> dict[str, Any]:
    """مخطط OpenAPI كما تولده FastAPI (يُستخدم في scripts/gen_api_docs.py)."""
    from backend.app.factory import create_app
    return create_app().openapi()
