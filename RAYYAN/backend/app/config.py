"""إعدادات ريّان المركزية: المسارات والثوابت ونص تنبيه البيانات الإلزامي."""
from __future__ import annotations

import os
from datetime import timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DB_PATH = Path(os.environ.get("RAYYAN_DB", DATA / "database/rayyan.sqlite"))
PACKAGE = DATA / "processed/package"
IMAGES = DATA / "processed/images"
IMAGE_PROCESSING_OUT = ROOT / "image_processing/output"   # مخرجات معالجة الصور (قراءة فقط)
MODEL_DIR = ROOT / "ml/saved_models"
CROPS_MODEL_DIR = MODEL_DIR / "crops"                   # نموذج المحاصيل الأربع (train_crops_model.py)
MODEL_PATH = MODEL_DIR / "response_model.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"
FRONTEND_DIST = ROOT / "frontend/dist"
DOCS_DIR = ROOT / "docs"

LOCAL_TZ = timezone(timedelta(hours=3), name="Asia/Riyadh")

# النص الإلزامي الذي يظهر في كل شاشة وكل استجابة API ذات صلة
DATA_NOTICE = "تعتمد نتائج النموذج الحالية على بيانات محاكاة، ولا تمثل دقة مثبتة في بيئة زراعية حقيقية."

# تصنيف أصل البيانات — مأخوذ من table_catalog.data_type في الحزمة
PROVENANCE = {
    "observed_aggregate": ("observed", "بيانات مرصودة", "متوسطات مناخية منشورة في دراسة؛ ليست قراءات من الموقع"),
    "reference": ("reference", "بيانات مرجعية", "إعادة تحليل ERA5 وجداول دراسة منشورة"),
    "simulation": ("simulated", "بيانات محاكاة", "مولدة بمحاكي الحزمة؛ ليست قراءات حساسات مركبة"),
    "derived_from_simulation": ("derived", "بيانات مشتقة", "محسوبة من المحاكاة: مدخلات ML وتنبيهات وتكلفة"),
    "missing_field_data": ("missing_field", "بيانات ميدانية ناقصة", "مطلوب جمعها؛ غير موجودة حاليًا"),
    "documentation": ("documentation", "توثيق", "مصادر وافتراضات وجاهزية الوظائف"),
}

SENSOR_MAX_AGE_MIN = 120          # rule_v1: القراءة صالحة إن كان عمرها ≤ ساعتين
RAIN_DEFER_MM = 4.0               # rule_v1: تأجيل عند توقع مطر ≥ 4 مم
FLOW_LOW_FRACTION = 0.7           # flow_first5min_rule_v1
SITE_RESIDUAL_ALERT_L = 5.0       # site_residual_gt5L_v1
