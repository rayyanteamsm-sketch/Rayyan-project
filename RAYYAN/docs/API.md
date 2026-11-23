# توثيق واجهة RAYYAN البرمجية (API)

> تعتمد نتائج النموذج الحالية على بيانات محاكاة، ولا تمثل دقة مثبتة في بيئة زراعية حقيقية.

هذا الملف مولَّد من مخطط OpenAPI الفعلي بالأمر `python scripts/gen_api_docs.py`. أثناء التشغيل:
- الخادم مبني على **FastAPI**. التجربة التفاعلية: Swagger `http://127.0.0.1:8000/api/swagger` وReDoc `/api/redoc`
- التوثيق العربي: `http://127.0.0.1:8000/api/docs` — المخطط الآلي OpenAPI: `http://127.0.0.1:8000/api/openapi.json`

## قواعد عامة

- كل الطلبات والاستجابات JSON بترميز UTF-8. التواريخ `YYYY-MM-DD` بتوقيت الرياض المحلي.
- الأخطاء بصيغة موحدة: `{"error": {"code", "message", "details"}}` مع رسائل عربية لكل حقل.
  - `422 validation_error`: مدخلات غير صالحة (نوع، نطاق، حقل مطلوب، حقل غير معروف).
  - `404 *_not_found`: معرف غير موجود. `500 internal_error`: خطأ غير متوقع، يُسجل نصه.
- كل طلب `/api/*` يُسجَّل في جدول `app_requests` (المسار، الحالة، المدة، الخطأ)، ويعود رقمه في ترويسة `X-Request-ID`.
- كل حسابات النموذج والقرار تتم في الخادم؛ الواجهة تعرض النتائج فقط.
- لا يوجد أي نقطة تُرسل أوامر لصمام؛ `valve_command` دائمًا `null`.

## النقاط (35 نقطة)

| الطريقة | المسار | الوصف |
|---|---|---|
| `GET` | `/api/health` | حالة الخادم والنموذج وقاعدة البيانات |
| `GET` | `/api/dashboard` | لوحة التحكم ليوم من المحاكاة |
| `GET` | `/api/water/usage` | استهلاك المياه المخطط مقابل المنفذ شهريًا لكل منطقة |
| `GET` | `/api/alerts` | تنبيهات القواعد (تدفق، موازنة، حساس) مع نتيجة الفحص المحاكى |
| `GET` | `/api/events/{event_id}/flow` | سلسلة التدفق لرية وتحليلها: المخطط مقابل المنفذ والتنبيهات |
| `GET` | `/api/zones` | المنطقتان وخصائصهما (zone_profiles) |
| `GET` | `/api/zones/{zone_id}` | منطقة واحدة |
| `GET` | `/api/site` | الموقع والمناطق والأجهزة وأصل البيانات والفجوات الميدانية |
| `GET` | `/api/site/gallery` | الصور الميدانية المرفقة مع مصدر كل مجموعة |
| `POST` | `/api/predict` | تنبؤ النموذج بتغير رطوبة التربة لخطة ري |
| `POST` | `/api/irrigation/recommend` | قرار الري (IRRIGATE / DEFER / CHECK_SENSOR) مع الأسباب والكمية |
| `GET` | `/api/irrigation/replay/{decision_id}` | إعادة تشغيل قرار محفوظ بمدخلاته الأصلية ومقارنته بقرار المحاكي |
| `POST` | `/api/simulation/run` | محاكاة سيناريوهات ري ومقارنتها |
| `GET` | `/api/simulation/defaults` | القيم الافتراضية لسيناريو في تاريخ: التوقع المحفوظ وآخر رطوبة لكل منطقة |
| `GET` | `/api/simulation/history` | آخر سيناريوهات المحاكاة المحفوظة |
| `GET` | `/api/model/metrics` | مقاييس النموذج الفعلية من التدريب (MAE/RMSE/R²) ومقارنة خطوط الأساس |
| `GET` | `/api/model/importance` | أهمية المدخلات: Impurity و Permutation |
| `GET` | `/api/model/predictions` | المتنبأ مقابل الفعلي لكل عملية ري مؤهلة |
| `GET` | `/api/model/decision-engine` | نتيجة التحقق من محرك القرار مقابل قرارات المحاكي |
| `GET` | `/api/history` | سجل العمليات مع البحث والتصفية |
| `GET` | `/api/history/requests` | سجل طلبات الـAPI (app_requests) |
| `GET` | `/api/history/{decision_id}` | تفاصيل عملية: القرار والتنفيذ والنتيجة والتدفق |
| `GET` | `/api/v2/overview` | مجموعة v2: المناطق الأربع، التقسيم، السيناريوهات المحقونة، ملاحظات الملف |
| `GET` | `/api/v2/metrics` | مقاييس النموذج الثاني مقابل خطوط الأساس (المحسوبة والمبلغ عنها في الملف) |
| `GET` | `/api/v2/predictions` | المتنبأ مقابل الفعلي للنموذج الثاني |
| `GET` | `/api/v2/defaults` | مدخلات النموذج الثاني المسجلة لمنطقة ويوم |
| `POST` | `/api/v2/predict` | تنبؤ النموذج الثاني بالرطوبة بعد 6 ساعات، مع تغيير المدخلات كسيناريو |
| `GET` | `/api/crops/zones` | المناطق الأربع والمحاصيل وخصائصها ومعاملات FAO-56 |
| `GET` | `/api/crops/dashboard` | حالة المناطق الأربع ليوم: الرطوبة، القرار، الكمية، التنبؤ، الاستهلاك |
| `POST` | `/api/crops/recommend` | توصية ري لمحصول: FAO-56 + الكمية والمدة + تنبؤ النموذج بالرطوبة بعد 6 ساعات |
| `POST` | `/api/crops/simulate` | محاكاة حتى 6 سيناريوهات ري لمحصول ومنحنى الاستجابة |
| `GET` | `/api/crops/metrics` | أداء نموذج المحاصيل مقابل خطوط الأساس (من التدريب الفعلي) |
| `GET` | `/api/crops/predictions` | المتنبأ مقابل الفعلي لنموذج المحاصيل |
| `GET` | `/api/crops/history` | سجل توصيات ومحاكاة المحاصيل الأربع مع البحث والتصفية |
| `GET` | `/api/site/image-analysis` | نتائج معالجة الصور الميدانية (رمادي، قناع أخضر، حواف، مؤشر الغطاء الأخضر) |

## النظام

### `GET /api/health`

**حالة الخادم والنموذج وقاعدة البيانات**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests


## لوحة التحكم

### `GET /api/dashboard`

**لوحة التحكم ليوم من المحاكاة**

حالة النظام، ولكل منطقة: الرطوبة وقت القرار، العتبة، الهدف، قرار المحرك، الكمية المقترحة، الرطوبة المتوقعة بعد الري من النموذج، آخر رية، استهلاك 30 يومًا، اتجاه الرطوبة، والتنبيهات.

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `date` | query | لا | يوم من المحاكاة YYYY-MM-DD؛ افتراضيًا آخر يوم |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `GET /api/water/usage`

**استهلاك المياه المخطط مقابل المنفذ شهريًا لكل منطقة**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests


## المراقبة

### `GET /api/alerts`

**تنبيهات القواعد (تدفق، موازنة، حساس) مع نتيجة الفحص المحاكى**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `limit` | query | لا |  |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `GET /api/events/{event_id}/flow`

**سلسلة التدفق لرية وتحليلها: المخطط مقابل المنفذ والتنبيهات**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `event_id` | path | نعم |  |

الاستجابات: `200` Successful Response، `404` غير موجود، `500` خطأ داخلي مسجل في app_requests، `422` Validation Error


## الموقع

### `GET /api/zones`

**المنطقتان وخصائصهما (zone_profiles)**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests

### `GET /api/zones/{zone_id}`

**منطقة واحدة**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `zone_id` | path | نعم |  |

الاستجابات: `200` Successful Response، `404` غير موجود، `500` خطأ داخلي مسجل في app_requests، `422` Validation Error

### `GET /api/site`

**الموقع والمناطق والأجهزة وأصل البيانات والفجوات الميدانية**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests

### `GET /api/site/gallery`

**الصور الميدانية المرفقة مع مصدر كل مجموعة**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests


## التعلم الآلي

### `POST /api/predict`

**تنبؤ النموذج بتغير رطوبة التربة لخطة ري**

يعيد delta_vwc المتوقع والرطوبة بعد الري، مع تحذير إذا خرجت المدخلات عن نطاق التدريب.

جسم الطلب `PredictRequest`:

| الحقل | النوع | مطلوب | القيود | الوصف |
|---|---|---|---|---|
| `zone_id` | string | لا | Z01، Z02 (افتراضي Z02) | المنطقة؛ تحدد عمق الجذور والمساحة من zone_profiles |
| `decision_date` | string | نعم |  | تاريخ القرار (محلي) — يحدد doy_sin/doy_cos |
| `pre_vwc` | number | نعم | minimum=0, maximum=0.4 | رطوبة التربة قبل القرار m³/m³ |
| `planned_volume_l` | number | نعم | minimum=0, maximum=500 | حجم الري المخطط باللتر |
| `planned_duration_min` | number/null | لا |  (افتراضي None) | المدة؛ إن غابت = الحجم ÷ التدفق الاسمي |
| `forecast_rain_mm` | number | نعم | minimum=0, maximum=300 | مطر متوقع خلال 24 ساعة (مم) |
| `forecast_et0_mm` | number | نعم | minimum=0, maximum=25 | تبخر-نتح مرجعي متوقع خلال 24 ساعة (مم) |

مثال:
```json
{
  "decision_date": "2025-07-15",
  "forecast_et0_mm": 9.5,
  "forecast_rain_mm": 0,
  "planned_volume_l": 60,
  "pre_vwc": 0.1,
  "zone_id": "Z02"
}
```

```bash
curl -X POST http://127.0.0.1:8000/api/predict -H "Content-Type: application/json" \
  -d '{"zone_id":"Z02","decision_date":"2025-07-15","pre_vwc":0.10,"planned_volume_l":60,"forecast_rain_mm":0,"forecast_et0_mm":9.5}'
```
الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests


## قرار الري

### `POST /api/irrigation/recommend`

**قرار الري (IRRIGATE / DEFER / CHECK_SENSOR) مع الأسباب والكمية**

يشغّل فحص الحساس (قاعدة أمان مستقلة) ثم قواعد ريّان rule_v1، ويحسب الكمية والمدة ضمن حد الرية والميزانية، ثم يتنبأ النموذج بالرطوبة بعد الري. تُحفظ التوصية في app_recommendations. لا يُرسل أي أمر لصمام.

جسم الطلب `RecommendRequest`:

| الحقل | النوع | مطلوب | القيود | الوصف |
|---|---|---|---|---|
| `zone_id` | string | نعم | Z01، Z02 |  |
| `decision_date` | string | نعم |  | تاريخ القرار المحلي؛ يحدد Kc الشهري والموسم |
| `pre_vwc` | number/null | لا |  (افتراضي None) | آخر قراءة رطوبة؛ null = لا قراءة. القيم غير الفيزيائية تؤدي إلى فحص الحساس |
| `sensor_age_min` | number/null | لا |  (افتراضي 0) | عمر القراءة بالدقائق عند القرار؛ null = غير معروف |
| `sensor_quality` | string | لا | ok، missing، invalid_range، duplicate، unknown (افتراضي ok) |  |
| `forecast_rain_mm` | number/null | لا |  (افتراضي None) |  |
| `forecast_et0_mm` | number/null | لا |  (افتراضي None) |  |
| `forecast_temperature_c` | number/null | لا |  (افتراضي None) |  |
| `use_stored_forecast` | boolean | لا |  (افتراضي False) | املأ قيم الطقس الغائبة من توقع المحاكاة المحفوظ لذلك اليوم إن وُجد |
| `daily_budget_l` | number/null | لا |  (افتراضي None) | الماء المتاح للموقع اليوم؛ افتراضيًا 160 لترًا من config.json |
| `other_zone_request_l` | number | لا | minimum=0, maximum=100000 (افتراضي 0) | طلب المنطقة الأخرى من نفس الميزانية |

مثال:
```json
{
  "daily_budget_l": 160,
  "decision_date": "2025-07-15",
  "forecast_et0_mm": 9.4,
  "forecast_rain_mm": 0,
  "forecast_temperature_c": 37,
  "other_zone_request_l": 60,
  "pre_vwc": 0.098,
  "sensor_age_min": 30,
  "sensor_quality": "ok",
  "zone_id": "Z02"
}
```

```bash
curl -X POST http://127.0.0.1:8000/api/irrigation/recommend \
  -H "Content-Type: application/json" \
  -d '{"zone_id":"Z02","decision_date":"2025-07-15","pre_vwc":0.098,"sensor_age_min":30,
       "forecast_rain_mm":0,"forecast_et0_mm":9.4,"forecast_temperature_c":37,
       "daily_budget_l":160,"other_zone_request_l":60}'
```
استجابة (مختصرة):
```json
{
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
}
```
الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `GET /api/irrigation/replay/{decision_id}`

**إعادة تشغيل قرار محفوظ بمدخلاته الأصلية ومقارنته بقرار المحاكي**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `decision_id` | path | نعم |  |
| `save` | query | لا | احفظ نتيجة إعادة التشغيل في app_recommendations |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `404` غير موجود، `500` خطأ داخلي مسجل في app_requests


## المحاكاة

### `POST /api/simulation/run`

**محاكاة سيناريوهات ري ومقارنتها**

لكل سيناريو: الرطوبة المتوقعة من النموذج، والفرق، والماء المستخدم، والتقريب الخطي للمقارنة. تُحفظ السيناريوهات في app_simulations. النتائج ليست قياسات ميدانية.

جسم الطلب `SimulationRequest`:

| الحقل | النوع | مطلوب | القيود | الوصف |
|---|---|---|---|---|
| `scenarios` | array | نعم | minItems=1, maxItems=6 |  |
| `sweep` | boolean | لا |  (افتراضي True) | أضف منحنى الاستجابة 0–80 لترًا للسيناريو الأول |

مثال:
```json
{
  "scenarios": [
    {
      "decision_date": "2025-07-15",
      "label": "40 لترًا",
      "pre_vwc": 0.1,
      "volume_l": 40,
      "zone_id": "Z02"
    },
    {
      "decision_date": "2025-07-15",
      "label": "70 لترًا",
      "pre_vwc": 0.1,
      "volume_l": 70,
      "zone_id": "Z02"
    }
  ]
}
```

```bash
curl -X POST http://127.0.0.1:8000/api/simulation/run -H "Content-Type: application/json" \
  -d '{"scenarios":[{"zone_id":"Z02","decision_date":"2025-07-15","pre_vwc":0.10,"volume_l":40},
                    {"zone_id":"Z02","decision_date":"2025-07-15","pre_vwc":0.10,"volume_l":80}]}'
```
الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `GET /api/simulation/defaults`

**القيم الافتراضية لسيناريو في تاريخ: التوقع المحفوظ وآخر رطوبة لكل منطقة**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `date` | query | نعم | YYYY-MM-DD |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `GET /api/simulation/history`

**آخر سيناريوهات المحاكاة المحفوظة**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `limit` | query | لا |  |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests


## التعلم الآلي

### `GET /api/model/metrics`

**مقاييس النموذج الفعلية من التدريب (MAE/RMSE/R²) ومقارنة خطوط الأساس**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests

### `GET /api/model/importance`

**أهمية المدخلات: Impurity و Permutation**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests

### `GET /api/model/predictions`

**المتنبأ مقابل الفعلي لكل عملية ري مؤهلة**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `split` | query | لا |  |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests


## قرار الري

### `GET /api/model/decision-engine`

**نتيجة التحقق من محرك القرار مقابل قرارات المحاكي**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests


## السجل

### `GET /api/history`

**سجل العمليات مع البحث والتصفية**

يجمع قرارات المحاكاة ونتائجها (decisions ← irrigation_events ← event_outcomes) وتوصيات التطبيق المحفوظة.

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `source` | query | لا |  القيم: `all`، `simulation`، `app` |
| `zone_id` | query | لا |  القيم: `Z01`، `Z02` |
| `action` | query | لا |  القيم: `IRRIGATE`، `DEFER`، `CHECK_SENSOR` |
| `status` | query | لا |  القيم: `not_executed`، `completed`، `no_flow`، `low_flow`، `stuck_open`، `label_missing`، `app_only` |
| `date_from` | query | لا |  |
| `date_to` | query | لا |  |
| `search` | query | لا |  |
| `limit` | query | لا |  |
| `offset` | query | لا |  |

```bash
curl 'http://127.0.0.1:8000/api/history?zone_id=Z02&action=IRRIGATE&date_from=2025-07-01&limit=20'
```
الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `GET /api/history/requests`

**سجل طلبات الـAPI (app_requests)**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `limit` | query | لا |  |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `GET /api/history/{decision_id}`

**تفاصيل عملية: القرار والتنفيذ والنتيجة والتدفق**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `decision_id` | path | نعم |  |

الاستجابات: `200` Successful Response، `404` غير موجود، `500` خطأ داخلي مسجل في app_requests، `422` Validation Error


## النموذج الثاني الأصلي (v2)

### `GET /api/v2/overview`

**مجموعة v2: المناطق الأربع، التقسيم، السيناريوهات المحقونة، ملاحظات الملف**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests

### `GET /api/v2/metrics`

**مقاييس النموذج الثاني مقابل خطوط الأساس (المحسوبة والمبلغ عنها في الملف)**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests

### `GET /api/v2/predictions`

**المتنبأ مقابل الفعلي للنموذج الثاني**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `split` | query | لا |  |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `GET /api/v2/defaults`

**مدخلات النموذج الثاني المسجلة لمنطقة ويوم**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `zone_id` | query | نعم |  |
| `date` | query | نعم |  |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `POST /api/v2/predict`

**تنبؤ النموذج الثاني بالرطوبة بعد 6 ساعات، مع تغيير المدخلات كسيناريو**

يبدأ من مدخلات اليوم المسجلة ويطبق التغييرات المرسلة فقط. يُحفظ كل تشغيل في app_v2_runs.

جسم الطلب `V2PredictRequest`:

| الحقل | النوع | مطلوب | القيود | الوصف |
|---|---|---|---|---|
| `zone_id` | string | نعم | Z001، Z002، Z003، Z004 |  |
| `decision_date` | string | نعم |  | يوم القرار YYYY-MM-DD ضمن 2024-10-05 — 2026-10-04 (القرار 06:00 UTC) |
| `before_VWC_pct` | number/null | لا |  (افتراضي None) | الرطوبة الحالية %؛ غيابها = استخدام قيمة الملف |
| `before_missing_reading` | boolean | لا |  (افتراضي False) | محاكاة فقد قراءة الحساس الحالية |
| `planned_volume_L` | number/null | لا |  (افتراضي None) |  |
| `planned_duration_min` | number/null | لا |  (افتراضي None) |  |
| `et0_forecast_24h_mm` | number/null | لا |  (افتراضي None) |  |
| `rain_forecast_24h_mm` | number/null | لا |  (افتراضي None) |  |
| `air_temp_observed_C` | number/null | لا |  (افتراضي None) |  |
| `humidity_observed_pct` | number/null | لا |  (افتراضي None) |  |

مثال:
```json
{
  "decision_date": "2026-07-01",
  "planned_volume_L": 1500,
  "zone_id": "Z004"
}
```

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests


## المحاصيل الأربع (FAO-56 + نموذج المحاصيل)

### `GET /api/crops/zones`

**المناطق الأربع والمحاصيل وخصائصها ومعاملات FAO-56**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests

### `GET /api/crops/dashboard`

**حالة المناطق الأربع ليوم: الرطوبة، القرار، الكمية، التنبؤ، الاستهلاك**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `date` | query | لا | YYYY-MM-DD؛ افتراضيًا آخر يوم في البيانات |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `POST /api/crops/recommend`

**توصية ري لمحصول: FAO-56 + الكمية والمدة + تنبؤ النموذج بالرطوبة بعد 6 ساعات**

يحسب الاستنزاف وحد الإجهاد RAW بقيم المنطقة من الملف، ويقرر IRRIGATE/DEFER/CHECK_SENSOR، ويحسب كمية إعادة الملء ومدتها، ثم يتنبأ نموذج المحاصيل بالرطوبة بعد 6 ساعات دون ري وبالكمية المقترحة. تُحفظ في app_crop_recommendations.

جسم الطلب `CropRecommendRequest`:

| الحقل | النوع | مطلوب | القيود | الوصف |
|---|---|---|---|---|
| `before_VWC_pct` | number/null | لا |  (افتراضي None) | الرطوبة الحالية %؛ غيابها = قراءة الملف لذلك اليوم |
| `sensor_missing` | boolean | لا |  (افتراضي False) | محاكاة فقد قراءة الحساس |
| `et0_forecast_24h_mm` | number/null | لا |  (افتراضي None) |  |
| `rain_forecast_24h_mm` | number/null | لا |  (افتراضي None) |  |
| `air_temp_observed_C` | number/null | لا |  (افتراضي None) |  |
| `humidity_observed_pct` | number/null | لا |  (افتراضي None) |  |
| `zone_id` | string | نعم | Z001، Z002، Z003، Z004 |  |
| `decision_date` | string | نعم |  | يوم ضمن 2024-10-05 — 2026-10-04 (القرار 06:00 UTC) |
| `p_override` | number/null | لا |  (افتراضي None) | نسبة الاستنزاف المسموح p؛ افتراضيًا من FAO-56 الجدول 22 |
| `target_vwc_pct` | number/null | لا |  (افتراضي None) | الرطوبة المستهدفة %؛ افتراضيًا السعة الحقلية |
| `daily_budget_l` | number/null | لا |  (افتراضي None) | حد أعلى للماء المتاح لهذه المنطقة اليوم (لتر) |
| `save` | boolean | لا |  (افتراضي True) | احفظ التوصية في app_crop_recommendations |

مثال:
```json
{
  "decision_date": "2026-07-01",
  "zone_id": "Z004"
}
```

```bash
curl -X POST http://127.0.0.1:8000/api/crops/recommend -H "Content-Type: application/json" \
  -d '{"zone_id":"Z002","decision_date":"2026-07-01"}'
```
استجابة (مختصرة):
```json
{
  "decision": {"action": "IRRIGATE", "rule_code": "will_cross_raw_24h", "reasons": ["الاستنزاف الحالي Dr = … = 28.8 مم …", "…"]},
  "fao56": {"taw_mm": 72.0, "raw_mm": 32.8, "p_adjusted": 0.456, "etc_mm": 7.35, "depletion_mm": 28.8, "trigger_vwc_pct": 25.8},
  "water_plan": {"volume_l": 28783.2, "duration_min": 89.9, "target_vwc_pct": 34, "formula": "…"},
  "model": {"predicted_vwc_no_irrigation_pct": 26.24, "predicted_vwc_with_plan_pct": 32.83, "curve": ["…25 نقطة…"]},
  "saved_id": 1, "valve_command": null
}
```
الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `POST /api/crops/simulate`

**محاكاة حتى 6 سيناريوهات ري لمحصول ومنحنى الاستجابة**

كل سيناريو يُتنبأ له بالنموذج وبمعادلة موازنة الماء، ويُحفظ في app_crop_recommendations (source=simulation).

جسم الطلب `CropSimulationRequest`:

| الحقل | النوع | مطلوب | القيود | الوصف |
|---|---|---|---|---|
| `zone_id` | string | نعم | Z001، Z002، Z003، Z004 |  |
| `decision_date` | string | نعم |  |  |
| `scenarios` | array | نعم | minItems=1, maxItems=6 |  |

مثال:
```json
{
  "decision_date": "2026-08-01",
  "scenarios": [
    {
      "label": "دون ري",
      "volume_l": 0
    },
    {
      "volume_l": 6000
    },
    {
      "volume_l": 15000
    }
  ],
  "zone_id": "Z002"
}
```

```bash
curl -X POST http://127.0.0.1:8000/api/crops/simulate -H "Content-Type: application/json" \
  -d '{"zone_id":"Z002","decision_date":"2026-08-01","scenarios":[{"volume_l":0},{"volume_l":6000},{"volume_l":20000}]}'
```
الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests

### `GET /api/crops/metrics`

**أداء نموذج المحاصيل مقابل خطوط الأساس (من التدريب الفعلي)**

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests

### `GET /api/crops/predictions`

**المتنبأ مقابل الفعلي لنموذج المحاصيل**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `split` | query | لا |  القيم: `train`، `validation`، `test` |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests


## السجل

### `GET /api/crops/history`

**سجل توصيات ومحاكاة المحاصيل الأربع مع البحث والتصفية**

| المعامل | الموضع | مطلوب | الوصف |
|---|---|---|---|
| `zone_id` | query | لا |  القيم: `Z001`، `Z002`، `Z003`، `Z004` |
| `action` | query | لا |  القيم: `IRRIGATE`، `DEFER`، `CHECK_SENSOR` |
| `source` | query | لا |  القيم: `recommend`، `simulation` |
| `date_from` | query | لا |  |
| `date_to` | query | لا |  |
| `search` | query | لا |  |
| `limit` | query | لا |  |
| `offset` | query | لا |  |

الاستجابات: `200` Successful Response، `422` مدخلات غير صالحة: {error:{code,message,details[]}}، `500` خطأ داخلي مسجل في app_requests


## الموقع

### `GET /api/site/image-analysis`

**نتائج معالجة الصور الميدانية (رمادي، قناع أخضر، حواف، مؤشر الغطاء الأخضر)**

يقرأ image_processing/output/report.csv و summary.json كما هي. مؤشر الأخضر لوني تقريبي (ExG > 0.10)، ليس قياسًا زراعيًا.

الاستجابات: `200` Successful Response، `500` خطأ داخلي مسجل في app_requests
