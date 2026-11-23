"""اختبارات تكامل على خادم حقيقي: الـAPI، الحفظ في SQLite، التحقق من المدخلات، السجل، وخدمة الواجهة."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTICE = "تعتمد نتائج النموذج الحالية على بيانات محاكاة، ولا تمثل دقة مثبتة في بيئة زراعية حقيقية."
REC = {"zone_id": "Z02", "decision_date": "2025-07-15", "pre_vwc": 0.098, "sensor_age_min": 30, "sensor_quality": "ok",
       "forecast_rain_mm": 0, "forecast_et0_mm": 9.4, "forecast_temperature_c": 37, "daily_budget_l": 160, "other_zone_request_l": 60}


def count(db, table):
    return db.execute(f"select count(*) from {table}").fetchone()[0]


def test_health_and_model_loaded_at_startup(client):
    s, b, _ = client.get("/api/health")
    assert s == 200 and b["model"]["loaded"] and b["model"]["source"] == "joblib" and b["data_notice"] == NOTICE


def test_recommend_irrigate_is_saved_and_linked(client, db):
    before = count(db, "app_recommendations")
    s, b, h = client.post("/api/irrigation/recommend", REC)
    assert s == 200
    assert b["decision"]["action"] == "IRRIGATE"
    assert b["water_plan"]["volume_l"] == 80 and b["water_plan"]["duration_min"] == 40
    assert b["prediction"]["available"] and b["prediction"]["post_vwc"] > 0.098
    assert b["valve_command"] is None
    row = db.execute("select * from app_recommendations where recommendation_id=?", (b["recommendation_id"],)).fetchone()
    assert count(db, "app_recommendations") == before + 1
    assert row["action"] == "IRRIGATE" and row["suggested_volume_l"] == 80 and row["zone_id"] == "Z02"
    req = db.execute("select * from app_requests where request_id=?", (row["request_id"],)).fetchone()
    assert req["path"] == "/api/irrigation/recommend" and req["status_code"] == 200 and int(h["x-request-id"]) == req["request_id"]


def test_recommend_broken_sensor_and_missing_values(client):
    s, b, _ = client.post("/api/irrigation/recommend", {**REC, "pre_vwc": None, "sensor_quality": "missing"})
    assert s == 200 and b["decision"]["action"] == "CHECK_SENSOR" and b["water_plan"] is None and b["prediction"] is None
    s, b, _ = client.post("/api/irrigation/recommend", {**REC, "sensor_age_min": 500})
    assert b["decision"]["action"] == "CHECK_SENSOR" and b["decision"]["sensor"]["status"] == "sensor_stale"
    s, b, _ = client.post("/api/irrigation/recommend", {"zone_id": "Z02", "decision_date": "2025-07-15", "pre_vwc": 0.09})
    assert s == 200 and b["decision"]["action"] == "IRRIGATE"
    assert any("المطر" in w for w in b["warnings"]) and b["prediction"]["available"] is False


def test_recommend_fills_stored_forecast_when_asked(client):
    s, b, _ = client.post("/api/irrigation/recommend", {"zone_id": "Z02", "decision_date": "2025-07-15", "pre_vwc": 0.09, "use_stored_forecast": True})
    assert s == 200 and b["prediction"]["available"] and any("مُلئت" in w for w in b["warnings"])


def test_rain_defers_and_budget_limits(client):
    s, b, _ = client.post("/api/irrigation/recommend", {**REC, "forecast_rain_mm": 6})
    assert b["decision"]["action"] == "DEFER" and b["decision"]["rule_code"] == "defer_rain_forecast"
    s, b, _ = client.post("/api/irrigation/recommend", {**REC, "daily_budget_l": 40})
    assert b["water_plan"]["volume_l"] == 22 and "daily_budget" in b["water_plan"]["limits_applied"]


def test_validation_errors_are_clear_and_logged(client, db):
    s, b, _ = client.post("/api/irrigation/recommend", {"zone_id": "Z9", "decision_date": "x", "pre_vwc": "a", "extra": 1})
    assert s == 422 and b["error"]["code"] == "validation_error"
    fields = {d["field"] for d in b["error"]["details"]}
    assert {"zone_id", "decision_date", "pre_vwc", "extra"} <= fields
    assert all(d["message"] for d in b["error"]["details"])
    last = db.execute("select * from app_requests where status_code=422 order by request_id desc limit 1").fetchone()
    assert last and "validation_error" in last["error"]
    s, b, _ = client.request("POST", "/api/predict", None)
    assert s == 422
    s, b, _ = client.get("/api/dashboard?date=2030-01-01")
    assert s == 422 and b["error"]["code"] == "date_out_of_range"
    s, b, _ = client.get("/api/does-not-exist")
    assert s == 404 and b["error"]["code"] == "not_found"


def test_predict_endpoint(client):
    s, b, _ = client.post("/api/predict", {"zone_id": "Z02", "decision_date": "2025-07-15", "pre_vwc": 0.10, "planned_volume_l": 60,
                                           "forecast_rain_mm": 0, "forecast_et0_mm": 9.5})
    assert s == 200 and 0 < b["delta_vwc"] < 0.06 and b["features"]["planned_duration_min"] == 30


def test_replay_matches_simulator_and_saves(client, db):
    s, b, _ = client.get("/api/irrigation/replay/D20250715Z02?save=true")
    assert s == 200 and b["agreement"]["comparable"] and b["agreement"]["action_match"] and b["agreement"]["volume_match"]
    row = db.execute("select * from app_recommendations where recommendation_id=?", (b["recommendation_id"],)).fetchone()
    assert row["source"] == "replay_decision" and row["based_on_decision_id"] == "D20250715Z02"
    assert client.get("/api/irrigation/replay/D19990101Z02")[0] == 404


def test_simulation_runs_and_is_saved(client, db):
    before = count(db, "app_simulations")
    body = {"scenarios": [{"zone_id": "Z02", "decision_date": "2025-07-15", "pre_vwc": 0.10, "volume_l": v, "label": f"{v}L"} for v in (20, 40, 80)]}
    s, b, _ = client.post("/api/simulation/run", body)
    assert s == 200 and len(b["scenarios"]) == 3 and count(db, "app_simulations") == before + 3
    p = [x["predicted_delta_vwc"] for x in b["scenarios"]]
    assert p == sorted(p) and len(b["scenarios"][0]["sweep"]) == 21
    assert "ليست قياسات" in b["disclaimer_ar"]
    s, b, _ = client.post("/api/simulation/run", {"scenarios": [{"zone_id": "Z02", "decision_date": "2030-01-01", "pre_vwc": 0.1, "volume_l": 40}]})
    assert s == 422 and "توقع" in b["error"]["message"]
    assert client.post("/api/simulation/run", {"scenarios": []})[0] == 422


def test_model_metrics_are_the_training_numbers(client):
    s, b, _ = client.get("/api/model/metrics")
    m = json.loads((ROOT / "ml/saved_models/metrics.json").read_text(encoding="utf-8"))
    assert s == 200 and b["results"] == m["results"] and b["model_version"] == m["model_version"]
    assert b["task"] == "regression" and "accuracy" not in json.dumps(b["results"]).lower()
    s, imp, _ = client.get("/api/model/importance")
    assert [r["feature"] for r in imp["permutation_test"]] == [r["feature"] for r in m["importance"]["permutation_test"]]
    s, p, _ = client.get("/api/model/predictions?split=test")
    assert len(p["items"]) == 202 and all(i["out_of_sample"] == 1 for i in p["items"])
    assert client.get("/api/model/predictions?split=all")[0] == 422


def test_history_filters_search_and_detail(client):
    s, b, _ = client.get("/api/history?source=simulation&limit=5")
    assert s == 200 and b["total"] == 1462 and len(b["items"]) == 5
    s, b, _ = client.get("/api/history?zone_id=Z02&action=CHECK_SENSOR&source=simulation")
    assert b["total"] == 1 and b["items"][0]["decision_id"] == "D20250315Z02"
    s, b, _ = client.get("/api/history?status=no_flow")
    assert {i["event_id"] for i in b["items"]} == {"E20240415Z02", "E20250407Z01"}
    s, b, _ = client.get("/api/history?date_from=2024-07-01&date_to=2024-07-31&source=simulation")
    assert b["total"] == 62 and all(i["time_local"].startswith("2024-07") for i in b["items"])
    s, b, _ = client.get("/api/history?search=E2025011")
    assert any(i["event_id"] == "E20250111Z02" for i in b["items"])
    s, b, _ = client.get("/api/history?source=app")
    assert b["total"] >= 1 and all(i["source"] == "app" for i in b["items"])
    assert client.get("/api/history?date_from=2025-02-01&date_to=2025-01-01")[0] == 422
    s, d, _ = client.get("/api/history/D20250111Z02")
    assert d["flow"]["detected_alerts"][0]["type"] == "unexpected_flow" and len(d["flow"]["series"]) > 30
    s, r, _ = client.get("/api/history/requests?limit=5")
    assert s == 200 and len(r["items"]) == 5


def test_dashboard_values_come_from_database(client, db):
    s, b, _ = client.get("/api/dashboard?date=2025-12-31")
    assert s == 200 and b["data_notice"] == NOTICE and len(b["zones"]) == 2
    z2 = next(z for z in b["zones"] if z["zone_id"] == "Z02")
    vwc = db.execute("""select m.usable_vwc from decisions d join measurements_clean m on m.sample_id=d.input_sample_id
        where d.decision_id='D20251231Z02'""").fetchone()[0]
    assert z2["recommendation"]["inputs"]["pre_vwc"] == vwc
    assert z2["recommendation"]["water_plan"]["volume_l"] == 72 and z2["water_to_date"]["n"] == 475
    s, w, _ = client.get("/api/water/usage")
    tot = {t["zone_id"]: t["delivered_l"] for t in w["totals"]}
    assert tot == {"Z01": 14670.14, "Z02": 31324.08} and "لا توجد نتيجة توفير" in w["interpretation_ar"]


def test_site_gallery_and_media(client):
    s, b, _ = client.get("/api/site")
    keys = [g["key"] for g in b["provenance"]]
    assert {"observed", "reference", "simulated", "derived", "missing_field"} <= set(keys)
    assert all(d["installation_status"] == "virtual_not_installed" for d in b["devices"])
    s, g, _ = client.get("/api/site/gallery")
    assert len(g["items"]) == 12 and sum(i["converted_from_heic"] for i in g["items"]) == 3
    for it in g["items"]:
        for k in ("thumb", "web", "display_original"):
            st, body, h = client.get("/media/" + it[k])
            assert st == 200 and h["content-type"].startswith("image/"), it[k]


def test_openapi_documents_every_endpoint(client):
    from backend.api.router import REGISTRY
    s, spec, _ = client.get("/api/openapi.json")
    documented = {(p, m.upper()) for p, ops in spec["paths"].items() for m in ops}
    assert {(e.path, e.method) for e in REGISTRY} == documented and len(documented) >= 20
    assert "RecommendRequest" in spec["components"]["schemas"]
    s, html, _ = client.get("/api/docs")
    assert s == 200 and b"/api/irrigation/recommend" in html


def test_frontend_is_served(client):
    s, html, h = client.get("/")
    assert s == 200 and b'id="root"' in html and b"/assets/app.js" in html
    s, js, h = client.get("/assets/app.js")
    assert s == 200 and len(js) > 100_000
    s, html2, _ = client.get("/history")  # SPA fallback
    assert s == 200 and b'id="root"' in html2


def test_v2_endpoints_and_saved_runs(client, db):
    s, h, _ = client.get("/api/health")
    assert h["v2_model"]["available"]
    s, o, _ = client.get("/api/v2/overview")
    assert s == 200 and [z["zone_id"] for z in o["zones"]] == ["Z001", "Z002", "Z003", "Z004"]
    s, m, _ = client.get("/api/v2/metrics")
    assert s == 200 and any(r["source"] == "reported_in_file" for r in m["results"]) and m["task"] == "regression"
    s, p, _ = client.get("/api/v2/predictions?split=test")
    assert len(p["items"]) == 433 and all(i["out_of_sample"] == 1 for i in p["items"])
    s, d, _ = client.get("/api/v2/defaults?zone_id=Z003&date=2026-08-01")
    assert s == 200 and d["inputs"]["crop"] == "خضار"
    assert client.get("/api/v2/defaults?zone_id=Z003&date=2023-08-01")[0] == 404
    assert client.get("/api/v2/defaults?zone_id=Z9&date=2026-08-01")[0] == 422
    before = db.execute("select count(*) from app_v2_runs").fetchone()[0]
    s, r, _ = client.post("/api/v2/predict", {"zone_id": "Z003", "decision_date": "2026-08-01", "planned_volume_L": 0})
    assert s == 200 and r["changed_inputs"] and r["run_id"]
    row = db.execute("select * from app_v2_runs where run_id=?", (r["run_id"],)).fetchone()
    assert db.execute("select count(*) from app_v2_runs").fetchone()[0] == before + 1 and row["base_event_id"] == r["event_id"]
    s, e, _ = client.post("/api/v2/predict", {"zone_id": "Z003", "decision_date": "2026-08-01", "before_VWC_pct": 90})
    assert s == 422
