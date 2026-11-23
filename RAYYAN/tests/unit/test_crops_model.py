"""اختبارات نموذج المحاصيل الأربع: معادلات FAO-56، خط الأساس الفيزيائي، منع التسرب، والنموذج المحفوظ."""
import json
import sqlite3
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from backend.services.crops_lib import FAO56_P, DeltaRegressor, fao56, reference_vwc, water_balance_6h

ROOT = Path(__file__).resolve().parents[2]
CROPS = ROOT / "ml/saved_models/crops"


def test_fao56_equations_by_hand():
    # برسيم: FC 34، WP 16، جذور 0.4 م ⇒ TAW = 1000 × 0.18 × 0.4 = 72 مم
    f = fao56(34, 16, 0.4, 26.8, 7.0, 1.05, 0.55)
    assert f["taw_mm"] == pytest.approx(72.0)
    assert f["etc_mm"] == pytest.approx(7.35)
    assert f["p_adjusted"] == pytest.approx(0.55 + 0.04 * (5 - 7.35))     # تعديل p حسب ETc
    assert f["raw_mm"] == pytest.approx(f["p_adjusted"] * 72)
    assert f["depletion_mm"] == pytest.approx(1000 * 0.072 * 0.4)        # (34 − 26.8)% × 0.4 م
    assert f["trigger_vwc_pct"] == pytest.approx(34 - 100 * f["raw_mm"] / 400)
    assert fao56(30, 14, 0.3, 31, 0, 0.9, 0.4)["depletion_mm"] == 0       # فوق السعة الحقلية ⇒ لا استنزاف
    assert 0.1 <= fao56(30, 14, 0.3, 20, 25, 1.2, 0.8)["p_adjusted"] <= 0.8


def test_p_values_are_the_published_fao56_table22_values():
    assert {k: v[0] for k, v in FAO56_P.items()} == {"نخيل مجدول": 0.50, "برسيم": 0.55, "خضار": 0.40, "نجيل": 0.50}


def _rows(**kw):
    base = dict(before_VWC_pct=20.0, lag1_before_VWC_pct=21.0, past7_before_mean_pct=22.0, planned_volume_L=0.0, efficiency=0.8,
                area_m2=100.0, et0_forecast_24h_mm=8.0, kc_assumed=1.0, rain_forecast_24h_mm=0.0, root_depth_m=0.5,
                field_capacity_pct=30.0, wilting_pct=10.0)
    base.update(kw)
    return pd.DataFrame([base])


def test_water_balance_baseline_physics():
    # 0 لتر: يفقد ETc×¼ = 2 مم من 500 مم عمق ⇒ −0.4 نقطة
    assert water_balance_6h(_rows(), 20)[0] == pytest.approx(19.6)
    # 1000 لتر × 0.8 ÷ 100 م² = 8 مم صافٍ ⇒ +1.6 − 0.4 = +1.2 نقطة
    assert water_balance_6h(_rows(planned_volume_L=1000), 20)[0] == pytest.approx(21.2)
    # كمية ضخمة تُقص عند التشبع (FC+10) أو عند السعة الحقلية
    assert water_balance_6h(_rows(planned_volume_L=1e6), 20)[0] == pytest.approx(40)
    assert water_balance_6h(_rows(planned_volume_L=1e6), 20, cap="field_capacity")[0] == pytest.approx(30)
    # القراءة المفقودة تُعوَّض بقراءة الأمس (مدخل سابق للقرار) لا بالهدف
    assert reference_vwc(_rows(before_VWC_pct=np.nan), 99)[0] == 21.0


def test_delta_regressor_learns_only_from_inputs():
    from sklearn.linear_model import LinearRegression
    X = pd.concat([_rows(before_VWC_pct=v, planned_volume_L=q) for v, q in [(15, 0), (18, 500), (20, 1000), (25, 0), (22, 1500)]], ignore_index=True)
    y = water_balance_6h(X, 20) + 0.5
    m = DeltaRegressor(LinearRegression(), base="water_balance").fit(X, y)
    assert m.fallback_ == pytest.approx(20.0)  # وسيط الرطوبة في التدريب، لا قيمة من الهدف
    assert np.allclose(m.predict(X), y, atol=1e-6)


def test_saved_crops_model_report_is_consistent():
    rep = json.loads((CROPS / "crops_metrics.json").read_text(encoding="utf-8"))
    b = joblib.load(CROPS / "crops_model.joblib")
    assert rep["model_version"] == b["version"] and rep["task"] == "regression"
    checks = rep["data"]["checks"]
    assert all(v for v in checks.values() if isinstance(v, bool)), checks
    assert not set(rep["features"]) & {"actual_volume_L", "actual_flow_L_min", "et0_realized_24h_mm", "rain_realized_24h_mm",
                                       "true_after_6h_pct", "target_after_6h_VWC_pct", "zone_id", "event_id"}
    sel = rep["selection"]
    assert sel["best"]["monotonic_val_pct"] >= sel["monotonic_min_pct"]
    # الاختيار على التحقق فقط: المختار هو الأقل RMSE تحقق بين المؤهلين
    eligible = [r for r in sel["all"] if r["monotonic_val_pct"] >= sel["monotonic_min_pct"]]
    assert min(r["rmse"] for r in eligible) == pytest.approx(sel["best"]["rmse"])
    test = {r["model_id"]: r for r in rep["results"] if r["split"] == "test"}
    assert test["deployed"]["rmse"] < test["persistence"]["rmse"] < test["median"]["rmse"]


def test_saved_model_reproduces_stored_test_metrics():
    """النموذج المحفوظ يعيد نفس مقاييس الاختبار المبلغ عنها من نفس البيانات (لا أرقام مكتوبة يدويًا)."""
    rep = json.loads((CROPS / "crops_metrics.json").read_text(encoding="utf-8"))
    b = joblib.load(CROPS / "crops_model.joblib")
    con = sqlite3.connect(ROOT / "data/database/rayyan.sqlite")
    df = pd.read_sql("select * from v2_ml_ready where temporal_split='test' and target_after_6h_VWC_pct is not null", con)
    con.close()
    p = b["model"].predict(df[b["features"]])
    rmse = float(np.sqrt(np.mean((p - df.target_after_6h_VWC_pct) ** 2)))
    assert rmse == pytest.approx(rep["headline"]["deployed_test"]["rmse"], rel=1e-9)
