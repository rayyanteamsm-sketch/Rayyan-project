"""اختبارات محرك القرار: قاعدة الأمان، المطر، العتبة، والقيم المفقودة."""
from datetime import date

import pytest

from backend.services.decision_engine import Forecast, SensorReading, check_sensor, decide, thresholds
from backend.services.reference import zone

Z = zone("Z02")
D = date(2025, 7, 15)
FC = Forecast(rain_mm=0.0, et0_mm=9.4, temperature_c=37.0)


def test_trigger_formula_matches_hand_calculation():
    th, warn = thresholds(Z, D, FC)
    kc_july = 0.80  # study_crop شهر 7
    tf = 0.35 + 0.65 * min(1, (37 - 8) / 20)
    expected = 0.15 - 0.5 * (0.15 - 0.06) + 9.4 * kc_july * tf / (250 * 2)
    assert th.trigger_vwc == pytest.approx(expected, abs=1e-12)
    assert th.taw_mm == pytest.approx(22.5) and th.raw_mm == pytest.approx(11.25)
    assert th.target_vwc == 0.15 and not warn


def test_below_trigger_irrigates():
    d = decide(Z, SensorReading(0.095, 30, "ok"), FC, D)
    assert d.action == "IRRIGATE" and d.reasons[0].code == "below_trigger"


def test_above_trigger_defers():
    d = decide(Z, SensorReading(0.14, 30, "ok"), FC, D)
    assert d.action == "DEFER" and d.rule_code == "defer_above_trigger"


def test_rain_forecast_defers_even_if_dry():
    d = decide(Z, SensorReading(0.08, 30, "ok"), Forecast(4.0, 3.0, 25), D)
    assert d.action == "DEFER" and d.rule_code == "defer_rain_forecast"
    d2 = decide(Z, SensorReading(0.08, 30, "ok"), Forecast(3.99, 3.0, 25), D)
    assert d2.action == "IRRIGATE"


@pytest.mark.parametrize("reading,code", [
    (SensorReading(None, 0, "ok"), "sensor_missing"),
    (SensorReading(0.1, 0, "missing"), "sensor_missing"),
    (SensorReading(0.1, 0, "invalid_range"), "sensor_flagged"),
    (SensorReading(0.62, 0, "ok"), "sensor_out_of_range"),
    (SensorReading(-0.02, 0, "ok"), "sensor_out_of_range"),
    (SensorReading(0.1, 121, "ok"), "sensor_stale"),
    (SensorReading(0.1, None, "ok"), "sensor_age_unknown"),
    (SensorReading(0.1, -5, "ok"), "sensor_future_timestamp"),
])
def test_broken_sensor_always_checks_sensor(reading, code):
    # حتى مع مطر غزير وجفاف، قاعدة الأمان تسبق كل شيء
    d = decide(Z, reading, Forecast(20.0, 9.0, 35), D)
    assert d.action == "CHECK_SENSOR"
    assert code in [r.code for r in d.sensor.issues]


def test_sensor_age_boundary_is_inclusive():
    assert check_sensor(SensorReading(0.1, 120, "ok"), Z).ok
    assert not check_sensor(SensorReading(0.1, 120.01, "ok"), Z).ok


def test_missing_forecast_is_reported_not_invented():
    d = decide(Z, SensorReading(0.10, 10, "ok"), Forecast(None, None, None), D)
    assert d.action in ("IRRIGATE", "DEFER")
    assert any("المطر" in w for w in d.warnings)
    assert any("التبخر" in w for w in d.warnings)
    assert d.thresholds.et_adjustment_vwc == 0.0


def test_every_decision_has_reasons():
    for vwc in (0.05, 0.1, 0.12, 0.15, None):
        d = decide(Z, SensorReading(vwc, 30, "ok"), FC, D)
        assert d.reasons and all(r.text_ar for r in d.reasons)
