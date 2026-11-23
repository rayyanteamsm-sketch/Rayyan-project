"""اختبارات مجموعة v2 والنموذج الثاني: الاستيراد، منع التسرب، مطابقة أرقام الملف، والتنبؤ."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from backend.services import v2_service

ROOT = Path(__file__).resolve().parents[2]
XLSX = ROOT / "data/raw/RAYYAN_ML_Ready.xlsx"
M = json.loads((ROOT / "ml/saved_models/v2/v2_metrics.json").read_text(encoding="utf-8"))
pytestmark = pytest.mark.skipif(not XLSX.exists(), reason="مجموعة v2 غير موجودة")


def test_raw_file_untouched():
    sums = dict(reversed(l.split(maxsplit=1)) for l in (ROOT / "data/raw/SHA256SUMS.txt").read_text().splitlines() if l.strip())
    assert hashlib.sha256(XLSX.read_bytes()).hexdigest() == sums["RAYYAN_ML_Ready.xlsx"]


@pytest.mark.parametrize("sheet,table", [("ML_Ready", "v2_ml_ready"), ("Outcomes", "v2_outcomes"), ("Zones", "v2_zones"),
                                         ("Weather", "v2_weather"), ("Simulation_Audit", "v2_simulation_audit"),
                                         ("Baseline_Metrics", "v2_reported_baselines")])
def test_import_is_complete_and_unchanged(db, sheet, table):
    src = pd.read_excel(XLSX, sheet_name=sheet)
    dst = pd.read_sql(f"select * from {table}", db)
    assert list(dst.columns) == list(src.columns) and len(dst) == len(src)
    num = [c for c in src.columns if pd.api.types.is_numeric_dtype(src[c])]
    pd.testing.assert_frame_equal(dst[num].reset_index(drop=True), src[num].reset_index(drop=True), check_dtype=False)


def test_v2_foreign_keys(db):
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("select count(*) from v2_outcomes o left join v2_ml_ready m using(event_id) where m.event_id is null").fetchone()[0] == 0


def test_no_leakage_checks_pass():
    c = M["data"]["checks"]
    for k in ("features_exclude_forbidden", "no_identifier_inputs", "decision_before_measurement", "weather_issued_before_decision",
              "features_use_forecast_not_realized", "train_before_validation", "validation_before_test"):
        assert c[k] is True, k
    assert not set(M["features"]) & {"actual_volume_L", "actual_flow_L_min", "target_after_6h_VWC_pct", "et0_realized_24h_mm",
                                     "rain_realized_24h_mm", "true_before_pct", "simulated_fault_label"}


def test_counts_match_file():
    c = M["data"]["counts"]
    assert (c["train"], c["validation"], c["test"], c["gap_excluded"], c["missing_targets"]) == (1973, 395, 433, 56, 64)


def test_validation_median_baseline_reproduces_file_exactly():
    ours = next(r for r in M["results"] if r["model_id"] == "train_median" and r["split"] == "validation")
    theirs = next(r for r in M["results"] if r["model_id"] == "reported_train_median" and r["split"] == "validation")
    for k in ("mae", "rmse", "r2"):
        assert ours[k] == pytest.approx(theirs[k], abs=1e-4)


def test_model_beats_computed_baselines_and_matches_file_order():
    t = {r["model_id"]: r for r in M["results"] if r["split"] == "test"}
    assert t["rf_deployed"]["rmse"] < t["persistence"]["rmse"] < t["train_median"]["rmse"]
    assert abs(t["rf_deployed"]["mae"] - t["reported_random_forest"]["mae"]) < 0.1  # متسق مع ما أورده الملف


def test_v2_predict_responds_to_inputs():
    v2_service.load()
    base = v2_service.predict("Z002", "2026-07-01", {})
    assert base["recorded_actual_vwc_pct"] is not None and base["warnings"] == []
    dry = v2_service.predict("Z002", "2026-07-01", {"planned_volume_L": 0.0})
    assert dry["predicted_vwc_pct"] < base["predicted_vwc_pct"] and dry["inputs_used"]["planned_duration_min"] == 0
    assert dry["recorded_actual_vwc_pct"] is None  # لا يُعرض رقم مسجل لسيناريو مُغيَّر
    miss = v2_service.predict("Z002", "2026-07-01", {"before_VWC_pct": None})
    assert miss["inputs_used"]["before_missing"] == 1 and any("مفقودة" in w for w in miss["warnings"])
    with pytest.raises(KeyError):
        v2_service.defaults("Z001", "2023-01-01")
