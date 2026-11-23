"""اختبارات حساب الكمية وتحميل النموذج والتنبؤ."""
import json
import math
from datetime import date

import pytest

from backend.app.config import METRICS_PATH
from backend.services import ml_service
from backend.services.reference import zone
from backend.services.water_planner import linear_preview_delta, plan

Z = zone("Z02")


def test_refill_volume_formula():
    p = plan(Z, 0.12, daily_budget_l=1000)
    assert p.requested_l == pytest.approx((0.15 - 0.12) * 250 * 5 / 0.8)   # 46.875
    assert p.volume_l == 46.0 and p.duration_min == 23                        # دقائق كاملة × 2 ل/د
    assert "whole_minutes" in p.limits_applied


def test_cap_80_litres():
    p = plan(Z, 0.05, daily_budget_l=1000)
    assert p.requested_l > 80 and p.volume_l == 80.0 and "max_event_l" in p.limits_applied


def test_budget_allocation_shared_with_other_zone():
    p = plan(Z, 0.08, daily_budget_l=40, other_zone_request_l=60)
    assert p.allocation_factor == pytest.approx(40 / (80 + 60))
    assert p.volume_l == math.floor(80 * 40 / 140 / 2) * 2 and "daily_budget" in p.limits_applied


def test_no_deficit_no_water():
    p = plan(Z, 0.16)
    assert p.volume_l == 0 and p.duration_min == 0


def test_linear_preview_matches_package_formula():
    # نفس معادلة build_dataset: V·eff/(area·root_mm) − ET0·Kc·(4/24)/root_mm
    v = linear_preview_delta(Z, 60, 9.0, 0.7)
    assert v == pytest.approx(60 * 0.8 / (5 * 250) - 9 * 0.7 * (4 / 24) / 250)


def test_model_loads_with_expected_features():
    b = ml_service.load()
    m = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    assert b["features"] == m["features"]
    assert b["version"] == m["model_version"]
    assert ml_service.status()["loaded"]


def test_prediction_is_finite_and_physical():
    x = ml_service.build_features(0.10, 60, 30, 0.25, 5, 0.0, 9.0, date(2025, 7, 15))
    p = ml_service.predict_one(x)
    assert math.isfinite(p["delta_vwc"]) and 0 < p["delta_vwc"] < 0.1
    assert p["post_vwc"] == pytest.approx(0.10 + p["delta_vwc"])
    assert p["warnings"] == []


def test_more_water_does_not_reduce_predicted_response():
    xs = [ml_service.build_features(0.10, v, v / 2, 0.25, 5, 0.0, 9.0, date(2025, 7, 15)) for v in (20, 40, 60, 80)]
    preds = ml_service.predict_many(xs)
    assert all(b >= a - 1e-9 for a, b in zip(preds, preds[1:]))


def test_out_of_range_inputs_warn():
    x = ml_service.build_features(0.10, 5, 2.5, 0.25, 5, 0.0, 9.0, date(2025, 7, 15))
    assert any("خارج نطاق" in w for w in ml_service.predict_one(x)["warnings"])
    y = ml_service.build_features(0.10, 60, 60, 0.25, 5, 0.0, 9.0, date(2025, 7, 15))  # 1 ل/د
    assert any("2 لتر/دقيقة" in w for w in ml_service.predict_one(y)["warnings"])


def test_missing_model_input_raises():
    x = ml_service.build_features(0.10, 60, 30, 0.25, 5, None, 9.0, date(2025, 7, 15))
    with pytest.raises(ValueError):
        ml_service.predict_one(x)


def test_retrain_fallback_when_joblib_unreadable(monkeypatch, tmp_path):
    bad = tmp_path / "broken.joblib"; bad.write_bytes(b"not a model")
    monkeypatch.setattr(ml_service, "MODEL_PATH", bad)
    b = ml_service.load(force=True)
    try:
        assert ml_service.status()["source"] == "retrained_local" and b["version"].endswith("-retrained-local")
        x = ml_service.build_features(0.10, 60, 30, 0.25, 5, 0.0, 9.0, date(2025, 7, 15))
        assert math.isfinite(ml_service.predict_one(x)["delta_vwc"])
    finally:
        monkeypatch.undo()
        ml_service.load(force=True)
    assert ml_service.status()["source"] == "joblib"
