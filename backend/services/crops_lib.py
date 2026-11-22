"""
أدوات مشتركة لنموذج المحاصيل الأربع بين التدريب (ml/training/train_crops_model.py) والخادم.
وضعت هنا (لا في سكربت التدريب) حتى يُحمَّل النموذج المحفوظ بـ joblib من أي مكان.

المعادلات مرجعها FAO-56 الفصل 8 (المرجع الذي تذكره ورقة ReadMe في الملف):
  TAW = 1000 · (θFC − θWP) · Zr                    [مم]   الماء المتاح الكلي في منطقة الجذور
  RAW = p · TAW                                     [مم]   الماء سهل الإتاحة
  p   = p_جدول22 + 0.04 · (5 − ETc)                 (تعديل p حسب ETc، محدود بين 0.1 و0.8)
  Dr  = 1000 · (θFC − θ) · Zr                       [مم]   الاستنزاف الحالي
  ETc = Kc · ET0                                    [مم/يوم]
  1 مم على 1 م² = 1 لتر ⇒ الحجم الإجمالي = Dr_المطلوب · المساحة ÷ الكفاءة
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone

TARGET = "target_after_6h_VWC_pct"

# نسبة الاستنزاف المسموح p من FAO-56 الجدول 22 — مرجع منشور، وليس من ملف البيانات.
# الخضار في الملف «خضار» دون نوع محدد؛ 0.40 قيمة وسطى لفئات الخضار في الجدول (0.30–0.50) ويمكن تغييرها من الواجهة.
FAO56_P = {
    "نخيل مجدول": (0.50, "FAO-56 الجدول 22: Date palms = 0.50"),
    "برسيم": (0.55, "FAO-56 الجدول 22: Alfalfa (hay) = 0.55"),
    "خضار": (0.40, "FAO-56 الجدول 22: الخضار 0.30–0.50 حسب النوع؛ اختيرت 0.40 لأن النوع غير محدد في الملف"),
    "نجيل": (0.50, "FAO-56 الجدول 22: Turf grass (warm season) = 0.50"),
}


def reference_vwc(d: pd.DataFrame, fallback: float) -> pd.Series:
    """الرطوبة المرجعية الحالية: القراءة، ثم قراءة الأمس، ثم متوسط 7 أيام، ثم قيمة احتياطية من التدريب."""
    return d["before_VWC_pct"].fillna(d["lag1_before_VWC_pct"]).fillna(d["past7_before_mean_pct"]).fillna(fallback)


def water_balance_6h(d: pd.DataFrame, fallback: float, cap: str = "saturation") -> np.ndarray:
    """خط أساس فيزيائي محسوب هنا (ليس معادلة الملف غير الموثقة):
    θ6 = θ + 100 · (ري_صافي + مطر·¼ − ETc·¼) ÷ (1000·Zr)، حيث ري_صافي = الحجم·الكفاءة÷المساحة [مم]،
    و¼ = 6 ساعات من 24. يُقص بين نقطة الذبول والسقف (التشبع = FC+10 كما في الملف، أو السعة الحقلية)."""
    theta = reference_vwc(d, fallback)
    net_mm = d["planned_volume_L"] * d["efficiency"] / d["area_m2"]
    etc6 = d["et0_forecast_24h_mm"] * d["kc_assumed"] * 0.25
    rain6 = d["rain_forecast_24h_mm"] * 0.25
    pred = theta + 100 * (net_mm + rain6 - etc6) / (1000 * d["root_depth_m"])
    top = d["field_capacity_pct"] + 10 if cap == "saturation" else d["field_capacity_pct"]
    return np.clip(pred.to_numpy(float), d["wilting_pct"].to_numpy(float), top.to_numpy(float))


class DeltaRegressor(BaseEstimator, RegressorMixin):
    """يتعلم الفرق بين الهدف وتقدير أساسي محسوب من المدخلات، ثم يعيد القيمة المطلقة = الأساس + الفرق المتعلم.
      base="persistence"   : الأساس هو الرطوبة الحالية (يتعلم التغير).
      base="water_balance" : الأساس معادلة موازنة الماء الفيزيائية (نموذج هجين يتعلم تصحيح المعادلة فقط).
    الأساس يُحسب من مدخلات ما قبل القرار فقط، والقيمة الاحتياطية للرطوبة تُتعلم من التدريب فقط — لا تسرب."""

    def __init__(self, estimator=None, base: str = "persistence", cap: str = "saturation"):
        self.estimator, self.base, self.cap = estimator, base, cap

    def _base(self, X):
        if self.base == "water_balance":
            return water_balance_6h(X, self.fallback_, self.cap)
        return reference_vwc(X, self.fallback_).to_numpy()

    def fit(self, X, y):
        self.fallback_ = float(np.nanmedian(X["before_VWC_pct"]))
        self.estimator_ = clone(self.estimator).fit(X, np.asarray(y, float) - self._base(X))
        return self

    def predict(self, X):
        return self.estimator_.predict(X) + self._base(X)


def fao56(fc_pct: float, wp_pct: float, root_m: float, theta_pct: float | None, et0_mm: float | None, kc: float,
          p_table: float) -> dict:
    """حسابات FAO-56 لمنطقة واحدة. كل القيم بالمليمتر ما لم يُذكر غير ذلك."""
    taw = 1000 * (fc_pct - wp_pct) / 100 * root_m
    etc = (et0_mm or 0.0) * kc
    p = float(np.clip(p_table + 0.04 * (5 - etc), 0.1, 0.8))
    raw = p * taw
    out = {"taw_mm": taw, "raw_mm": raw, "p_table": p_table, "p_adjusted": p, "etc_mm": etc,
           "trigger_vwc_pct": fc_pct - 100 * raw / (1000 * root_m)}
    if theta_pct is not None:
        out["depletion_mm"] = max(0.0, 1000 * (fc_pct - theta_pct) / 100 * root_m)
        out["depletion_frac_taw"] = out["depletion_mm"] / taw if taw else None
    return out
