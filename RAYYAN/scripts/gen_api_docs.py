"""يولّد docs/API.md من مخطط OpenAPI الفعلي للخادم، مع أمثلة طلبات واستجابات حقيقية."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.api.router import REGISTRY, openapi  # noqa: E402
import backend.api.routes  # noqa: E402,F401

TAG_AR = {"system": "النظام", "dashboard": "لوحة التحكم", "monitoring": "المراقبة", "site": "الموقع", "ml": "التعلم الآلي",
          "decision": "قرار الري", "simulation": "المحاكاة", "history": "السجل", "v2": "النموذج الثاني الأصلي (v2)",
          "crops": "المحاصيل الأربع (FAO-56 + نموذج المحاصيل)"}

EXAMPLES = {
    "/api/irrigation/recommend": ("""curl -X POST http://127.0.0.1:8000/api/irrigation/recommend \\
  -H "Content-Type: application/json" \\
  -d '{"zone_id":"Z02","decision_date":"2025-07-15","pre_vwc":0.098,"sensor_age_min":30,
       "forecast_rain_mm":0,"forecast_et0_mm":9.4,"forecast_temperature_c":37,
       "daily_budget_l":160,"other_zone_request_l":60}'""",
        """{
  "decision": {"action": "IRRIGATE", "action_ar": "ري", "rule_code": "refill_root_zone",
    "sensor": {"ok": true, "status": "ok", "issues": []},
    "thresholds": {"trigger_vwc": 0.120, "target_vwc": 0.15, "kc_decision": 0.8, "raw_mm": 11.25, "...": "..."},
    "reasons": [{"code": "below_trigger", "text_ar": "الرطوبة 0.098 عند العتبة 0.120 أو أقل منها؛ …", "kind": "decisive"}, "..."]},
  "water_plan": {"requested_l": 81.25, "capped_l": 80, "allocation_factor": 1.0, "volume_l": 80, "duration_min": 40,
    "limits_applied": ["max_event_l"], "explanation": ["…"]},
  "prediction": {"available": true, "delta_vwc": 0.0358, "post_vwc": 0.1338, "linear_delta_vwc": 0.0462,
    "model_version": "rf-delta-vwc-…", "warnings": []},
  "recommendation_id": 1, "valve_command": null,
  "data_notice": "تعتمد نتائج النموذج الحالية على بيانات محاكاة، ولا تمثل دقة مثبتة في بيئة زراعية حقيقية."
}"""),
    "/api/simulation/run": ("""curl -X POST http://127.0.0.1:8000/api/simulation/run -H "Content-Type: application/json" \\
  -d '{"scenarios":[{"zone_id":"Z02","decision_date":"2025-07-15","pre_vwc":0.10,"volume_l":40},
                    {"zone_id":"Z02","decision_date":"2025-07-15","pre_vwc":0.10,"volume_l":80}]}'""", None),
    "/api/history": ("curl 'http://127.0.0.1:8000/api/history?zone_id=Z02&action=IRRIGATE&date_from=2025-07-01&limit=20'", None),
    "/api/crops/recommend": ("""curl -X POST http://127.0.0.1:8000/api/crops/recommend -H "Content-Type: application/json" \\
  -d '{"zone_id":"Z002","decision_date":"2026-07-01"}'""",
        """{
  "decision": {"action": "IRRIGATE", "rule_code": "will_cross_raw_24h", "reasons": ["الاستنزاف الحالي Dr = … = 28.8 مم …", "…"]},
  "fao56": {"taw_mm": 72.0, "raw_mm": 32.8, "p_adjusted": 0.456, "etc_mm": 7.35, "depletion_mm": 28.8, "trigger_vwc_pct": 25.8},
  "water_plan": {"volume_l": 28783.2, "duration_min": 89.9, "target_vwc_pct": 34, "formula": "…"},
  "model": {"predicted_vwc_no_irrigation_pct": 26.24, "predicted_vwc_with_plan_pct": 32.83, "curve": ["…25 نقطة…"]},
  "saved_id": 1, "valve_command": null
}"""),
    "/api/crops/simulate": ("""curl -X POST http://127.0.0.1:8000/api/crops/simulate -H "Content-Type: application/json" \\
  -d '{"zone_id":"Z002","decision_date":"2026-08-01","scenarios":[{"volume_l":0},{"volume_l":6000},{"volume_l":20000}]}'""", None),
    "/api/predict": ("""curl -X POST http://127.0.0.1:8000/api/predict -H "Content-Type: application/json" \\
  -d '{"zone_id":"Z02","decision_date":"2025-07-15","pre_vwc":0.10,"planned_volume_l":60,"forecast_rain_mm":0,"forecast_et0_mm":9.5}'""", None),
}


def main():
    spec = openapi("1.0.0")
    L = ["# توثيق واجهة RAYYAN البرمجية (API)\n",
         "> تعتمد نتائج النموذج الحالية على بيانات محاكاة، ولا تمثل دقة مثبتة في بيئة زراعية حقيقية.\n",
         "هذا الملف مولَّد من مخطط OpenAPI الفعلي بالأمر `python scripts/gen_api_docs.py`. أثناء التشغيل:",
         "- الخادم مبني على **FastAPI**. التجربة التفاعلية: Swagger `http://127.0.0.1:8000/api/swagger` وReDoc `/api/redoc`",
         "- التوثيق العربي: `http://127.0.0.1:8000/api/docs` — المخطط الآلي OpenAPI: `http://127.0.0.1:8000/api/openapi.json`\n",
         "## قواعد عامة\n",
         "- كل الطلبات والاستجابات JSON بترميز UTF-8. التواريخ `YYYY-MM-DD` بتوقيت الرياض المحلي.",
         "- الأخطاء بصيغة موحدة: `{\"error\": {\"code\", \"message\", \"details\"}}` مع رسائل عربية لكل حقل.",
         "  - `422 validation_error`: مدخلات غير صالحة (نوع، نطاق، حقل مطلوب، حقل غير معروف).",
         "  - `404 *_not_found`: معرف غير موجود. `500 internal_error`: خطأ غير متوقع، يُسجل نصه.",
         "- كل طلب `/api/*` يُسجَّل في جدول `app_requests` (المسار، الحالة، المدة، الخطأ)، ويعود رقمه في ترويسة `X-Request-ID`.",
         "- كل حسابات النموذج والقرار تتم في الخادم؛ الواجهة تعرض النتائج فقط.",
         "- لا يوجد أي نقطة تُرسل أوامر لصمام؛ `valve_command` دائمًا `null`.\n",
         f"## النقاط ({len(REGISTRY)} نقطة)\n",
         "| الطريقة | المسار | الوصف |", "|---|---|---|"]
    for e in REGISTRY:
        L.append(f"| `{e.method}` | `{e.path}` | {e.summary} |")
    cur = None
    for e in REGISTRY:
        op = spec["paths"][e.path][e.method.lower()]
        if e.tag != cur:
            cur = e.tag; L.append(f"\n## {TAG_AR.get(cur, cur)}\n")
        L.append(f"### `{e.method} {e.path}`\n\n**{op['summary']}**\n")
        if op.get("description") and op["description"] != op["summary"]:
            L.append(op["description"] + "\n")
        if op.get("parameters"):
            L.append("| المعامل | الموضع | مطلوب | الوصف |\n|---|---|---|---|")
            for p in op["parameters"]:
                desc = (p.get("description") or "").replace("|", "/")
                sch = p.get("schema", {})
                extra = ""
                if "enum" in sch: extra = " القيم: " + "، ".join(f"`{v}`" for v in sch["enum"])
                for opt in sch.get("anyOf", []):
                    if "enum" in opt: extra = " القيم: " + "، ".join(f"`{v}`" for v in opt["enum"])
                L.append(f"| `{p['name']}` | {p['in']} | {'نعم' if p.get('required') else 'لا'} | {desc}{extra} |")
            L.append("")
        if e.body is not None:
            sch = e.body.model_json_schema()
            L.append(f"جسم الطلب `{e.body.__name__}`:\n")
            L.append("| الحقل | النوع | مطلوب | القيود | الوصف |\n|---|---|---|---|---|")
            for name, prop in sch["properties"].items():
                types = prop.get("type") or "/".join(x.get("type", x.get("$ref", "").split("/")[-1]) for x in prop.get("anyOf", []))
                cons = ", ".join(f"{k}={prop[k]}" for k in ("minimum", "maximum", "exclusiveMinimum", "maxLength", "minItems", "maxItems") if k in prop)
                if "enum" in prop: cons = "، ".join(prop["enum"])
                if "default" in prop: cons += f" (افتراضي {prop['default']})"
                L.append(f"| `{name}` | {types} | {'نعم' if name in sch.get('required', []) else 'لا'} | {cons} | {(prop.get('description') or '').replace('|', '/')} |")
            if "example" in sch:
                L.append(f"\nمثال:\n```json\n{json.dumps(sch['example'], ensure_ascii=False, indent=2)}\n```")
            L.append("")
        if e.path in EXAMPLES:
            cmd, resp = EXAMPLES[e.path]
            L.append(f"```bash\n{cmd}\n```")
            if resp:
                L.append(f"استجابة (مختصرة):\n```json\n{resp}\n```")
        L.append("الاستجابات: " + "، ".join(f"`{k}` {v['description']}" for k, v in op["responses"].items()) + "\n")
    (ROOT / "docs/API.md").write_text("\n".join(L), encoding="utf-8")
    print("✓ docs/API.md —", len(REGISTRY), "نقطة")


if __name__ == "__main__":
    main()
