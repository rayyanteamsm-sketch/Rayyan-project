"""سلامة البيانات والعلاقات ونتائج التدريب، ومطابقة المحرك والتنبيهات لسجلات المحاكي."""
import hashlib
import json
from pathlib import Path

import pytest

from backend.services.flow_monitor import analyse_event
from backend.services.history import query
from backend.services.recommendation import SIM_ACTION, build, stored_inputs

ROOT = Path(__file__).resolve().parents[2]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_original_upload_untouched():
    line = (ROOT / "data/raw/SHA256SUMS.txt").read_text().split()
    assert sha(ROOT / "data/raw/original_upload.zip") == line[0]


def test_package_sqlite_copy_matches_original_checksum():
    sums = dict(reversed(l.split(maxsplit=1)) for l in (ROOT / "data/processed/package/SHA256SUMS.txt").read_text().splitlines() if l.strip())
    key = next(k for k in sums if k.strip().lstrip("*").endswith("Rayyan_Bermuda_2024_2025.sqlite"))
    assert sha(ROOT / "data/processed/package/Rayyan_Bermuda_2024_2025.sqlite") == sums[key]


def test_foreign_keys_and_original_row_counts(db):
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    for t in db.execute("select [table], row_count from _table_catalog").fetchall():
        assert db.execute(f"select count(*) from [{t[0]}]").fetchone()[0] == t[1], t[0]


def test_decision_event_outcome_links_are_one_to_one(db):
    assert db.execute("select count(*) from decisions").fetchone()[0] == 1462
    assert db.execute("select count(*) from irrigation_events").fetchone()[0] == 770
    assert db.execute("select count(*) from decisions where action='irrigate'").fetchone()[0] == 770
    dup = db.execute("select decision_id, count(*) c from irrigation_events group by decision_id having c > 1").fetchall()
    assert dup == []
    bad_zone = db.execute("""select count(*) from irrigation_events e join decisions d using(decision_id)
        where e.zone_id != d.zone_id""").fetchone()[0]
    assert bad_zone == 0
    orphan = db.execute("""select count(*) from event_outcomes o left join irrigation_events e using(event_id)
        where e.event_id is null or o.decision_id != e.decision_id""").fetchone()[0]
    assert orphan == 0


def test_history_has_no_duplicated_records():
    h = query(source="simulation", limit=5000)
    ids = [i["decision_id"] for i in h["items"]]
    assert h["total"] == 1462 and len(ids) == len(set(ids))


def test_training_report_has_no_leakage_and_correct_counts():
    m = json.loads((ROOT / "ml/saved_models/metrics.json").read_text(encoding="utf-8"))
    c = m["data"]["checks"]
    for k in ("features_exclude_forbidden", "features_available_before_decision", "train_labels_before_validation_start",
              "validation_labels_before_test_start", "no_missing_features_in_eligible"):
        assert c[k] is True, k
    assert m["data"]["counts"] == {"train": 384, "validation": 183, "test": 202, "excluded": 1, "deployed_fit": 567}
    assert "test" not in m["selection"]["method"].split(";")[0]
    assert not set(m["features"]) & set(m["forbidden_inputs"])
    assert m["task"] == "regression" and not any("accuracy" in k for r in m["results"] for k in r)


def test_package_experiment_reproduced():
    m = json.loads((ROOT / "ml/saved_models/metrics.json").read_text(encoding="utf-8"))
    ref = next(r for r in m["package_reproduction"]["package_reported"] if r["model_id"] == "RF_fixed_2024" and r["evaluation_split"] == "test")
    # يتطابق حتى 4 منازل عشرية؛ فرق ~8e-6 يُرجَّح أنه من اختلاف إصدار scikit-learn عن بيئة الحزمة (موثق في MODEL_CARD)
    assert m["package_reproduction"]["ours"]["test"]["r2"] == pytest.approx(ref["r2"], abs=1e-4)


def test_model_beats_baselines_on_test():
    m = json.loads((ROOT / "ml/saved_models/metrics.json").read_text(encoding="utf-8"))
    t = {r["model_id"]: r for r in m["results"] if r["split"] == "test"}
    for b in ("baseline_zero_change", "baseline_train_mean", "baseline_linear_rule"):
        assert t["rf_selected_deployed"]["rmse"] < t[b]["rmse"]


@pytest.mark.parametrize("did", ["D20240101Z02", "D20240715Z02", "D20250315Z02", "D20250602Z02", "D20250604Z02",
                                 "D20250606Z02", "D20251231Z02", "D20240415Z02", "D20241120Z02"])
def test_engine_reproduces_simulator_rule_v1(did):
    inp, st = stored_inputs(did)
    res = build(inp)
    assert res["decision"]["action"] == SIM_ACTION[st["action"]]
    assert ((res["water_plan"] or {}).get("volume_l") or 0) == pytest.approx(st["planned_volume_l"])


def test_engine_full_validation_report():
    r = json.loads((ROOT / "ml/saved_models/decision_engine_validation.json").read_text(encoding="utf-8"))
    assert r["decisions_compared"] == 731 and r["action_matches"] == 731 and r["volume_matches"] == 731


def test_flow_rules_reproduce_stored_alerts(db):
    stored = {(e, a) for e, a in db.execute("select event_id, alert_type from rule_alerts where event_id is not null")}
    detected = set()
    for (eid,) in db.execute("select event_id from irrigation_events").fetchall():
        for a in analyse_event(eid)["detected_alerts"]:
            detected.add((eid, a["type"]))
    assert detected == stored and len(stored) == 5
