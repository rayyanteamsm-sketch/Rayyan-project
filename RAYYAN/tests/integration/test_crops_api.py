"""اختبارات تكامل للمحاصيل الأربع ومعالجة الصور وFastAPI على خادم حقيقي وقاعدة بيانات مؤقتة."""


def count(db, table, where=""):
    return db.execute(f"select count(*) from {table} {where}").fetchone()[0]


REC = {"zone_id": "Z002", "decision_date": "2026-07-01"}


def test_health_reports_both_models(client):
    s, h, _ = client.get("/api/health")
    assert s == 200 and h["model"]["loaded"]
    s, z, _ = client.get("/api/crops/zones")
    assert s == 200 and [i["zone_id"] for i in z["items"]] == ["Z001", "Z002", "Z003", "Z004"]
    assert z["model"]["loaded"] and z["model"]["version"].startswith("crops-")
    assert {i["crop"] for i in z["items"]} == {"نخيل مجدول", "برسيم", "خضار", "نجيل"}


def test_recommend_irrigate_with_fao56_amount_and_is_saved(client, db):
    before = count(db, "app_crop_recommendations")
    s, r, h = client.post("/api/crops/recommend", REC)
    assert s == 200 and r["decision"]["action"] == "IRRIGATE"
    z, f, plan = r["zone"], r["fao56"], r["water_plan"]
    theta = r["inputs_used"]["before_VWC_pct"]
    # الكمية = (FC − θ) × الجذور × 1000 × المساحة ÷ الكفاءة ؛ المدة = الكمية ÷ التدفق
    expected = (z["field_capacity_pct"] - theta) / 100 * z["root_depth_m"] * 1000 * z["area_m2"] / z["efficiency"]
    assert plan["volume_l"] == round(expected, 1)
    assert plan["duration_min"] == round(expected / z["nominal_flow_L_min"], 1)
    assert f["depletion_mm"] + f["etc_mm"] - f["rain_forecast_mm"] >= f["raw_mm"]
    m = r["model"]
    assert m["predicted_vwc_with_plan_pct"] > m["predicted_vwc_no_irrigation_pct"]
    assert len(m["curve"]) == 25 and r["valve_command"] is None
    row = db.execute("select * from app_crop_recommendations where crop_rec_id=?", (r["saved_id"],)).fetchone()
    assert count(db, "app_crop_recommendations") == before + 1
    assert row["zone_id"] == "Z002" and row["action"] == "IRRIGATE" and row["volume_l"] == plan["volume_l"]
    assert row["base_event_id"] == r["event_id"] and row["source"] == "recommend"
    req = db.execute("select * from app_requests where request_id=?", (row["request_id"],)).fetchone()
    assert req["path"] == "/api/crops/recommend" and int(h["x-request-id"]) == req["request_id"]


def test_recommend_rules_defer_rain_sensor(client):
    s, r, _ = client.post("/api/crops/recommend", {**REC, "rain_forecast_24h_mm": 60, "save": False})
    assert r["decision"]["action"] == "DEFER" and r["decision"]["rule_code"] == "rain_covers_depletion" and r["water_plan"] is None
    s, r, _ = client.post("/api/crops/recommend", {**REC, "before_VWC_pct": 33.5, "save": False})
    assert r["decision"]["action"] == "DEFER" and r["decision"]["rule_code"] == "depletion_below_raw"
    # 26.8%: الري لازم خلال 24 ساعة (Dr 28.8 + ETc 7.35 ≥ RAW 32.8)؛ مطر 4 مم أقل من Dr لكنه يعيد Dr+ETc−مطر تحت RAW
    s, r, _ = client.post("/api/crops/recommend", {**REC, "rain_forecast_24h_mm": 4, "save": False})
    assert r["decision"]["rule_code"] == "rain_offsets_etc" and r["decision"]["action"] == "DEFER"
    s, r, _ = client.post("/api/crops/recommend", {**REC, "sensor_missing": True, "save": False})
    assert r["decision"]["action"] == "CHECK_SENSOR" and r["water_plan"] is None
    assert r["model"] is not None and any("مفقودة" in w for w in r["warnings"])
    s, r, _ = client.post("/api/crops/recommend", {**REC, "before_VWC_pct": 50, "save": False})
    assert r["decision"]["rule_code"] == "sensor_out_of_range"
    s, r, _ = client.post("/api/crops/recommend", {**REC, "daily_budget_l": 1000, "save": False})
    assert r["water_plan"]["volume_l"] == 1000 and "daily_budget" in r["water_plan"]["limits_applied"]
    s, r, _ = client.post("/api/crops/recommend", {**REC, "p_override": 0.8, "save": False})
    assert r["fao56"]["p_table"] == 0.8


def test_recommend_validation_and_not_found(client):
    s, b, _ = client.post("/api/crops/recommend", {"zone_id": "Z9", "decision_date": "x", "extra": 1, "before_VWC_pct": -3})
    assert s == 422 and b["error"]["code"] == "validation_error"
    assert {"zone_id", "decision_date", "extra", "before_VWC_pct"} <= {d["field"] for d in b["error"]["details"]}
    s, b, _ = client.post("/api/crops/recommend", {"zone_id": "Z001", "decision_date": "2023-01-01"})
    assert s == 404 and b["error"]["code"] == "crop_record_not_found" and "2024-10-05" in b["error"]["message"]
    s, b, _ = client.get("/api/crops/dashboard?date=2030-01-01")
    assert s == 422 and b["error"]["code"] == "date_out_of_range"


def test_simulation_is_monotonic_in_volume_and_saved(client, db):
    before = count(db, "app_crop_recommendations", "where source='simulation'")
    body = {"zone_id": "Z004", "decision_date": "2026-07-01", "scenarios": [{"volume_l": v} for v in (0, 1500, 3000, 5000)]}
    s, r, _ = client.post("/api/crops/simulate", body)
    assert s == 200 and len(r["scenarios"]) == 4
    p = [x["predicted_vwc_pct"] for x in r["scenarios"]]
    assert p == sorted(p) and p[-1] > p[0]
    assert count(db, "app_crop_recommendations", "where source='simulation'") == before + 4
    assert "ليست قياسات" in r["disclaimer_ar"]
    assert client.post("/api/crops/simulate", {**body, "scenarios": []})[0] == 422


def test_dashboard_metrics_predictions_history(client):
    s, d, _ = client.get("/api/crops/dashboard?date=2026-07-01")
    assert s == 200 and len(d["zones"]) == 4 and d["date"] == "2026-07-01" and len(d["usage_30d"]) == 4
    s, m, _ = client.get("/api/crops/metrics")
    assert s == 200 and m["task"] == "regression" and any(r["source"] == "reported_in_file" for r in m["results"])
    s, p, _ = client.get("/api/crops/predictions?split=test")
    assert len(p["items"]) == m["data"]["counts"]["test"] and all(i["out_of_sample"] == 1 for i in p["items"])
    assert client.post("/api/crops/recommend", REC)[0] == 200  # سجل محفوظ لهذا الاختبار نفسه
    s, h, _ = client.get("/api/crops/history?zone_id=Z002&source=recommend")
    assert s == 200 and h["total"] >= 1 and all(i["zone_id"] == "Z002" and i["source"] == "recommend" for i in h["items"])
    assert isinstance(h["items"][0]["reasons"], list)
    from urllib.parse import quote
    s, h, _ = client.get(f"/api/crops/history?search={quote('برسيم')}&limit=5")
    assert s == 200 and all(i["crop"] == "برسيم" for i in h["items"])
    assert client.get("/api/crops/history?date_from=2026-02-01&date_to=2026-01-01")[0] == 422


def test_image_analysis_reads_image_processing_outputs(client):
    s, b, _ = client.get("/api/site/image-analysis")
    assert s == 200 and len(b["items"]) == 12 and b["summary"]["originals_unchanged"] is True
    for it in b["items"][:3]:
        for url in it["images"].values():
            st, body, h = client.get(url)
            assert st == 200 and h["content-type"] == "image/png", url
    assert all(0 <= i["green_cover_pct"] <= 100 for i in b["items"])


def test_fastapi_docs_and_invalid_json(client):
    s, spec, _ = client.get("/api/openapi.json")
    assert s == 200 and "CropRecommendRequest" in spec["components"]["schemas"] and "/api/crops/recommend" in spec["paths"]
    s, html, _ = client.get("/api/swagger")
    assert s == 200 and b"swagger" in html.lower()
    s, b, _ = client.request("POST", "/api/crops/recommend", None)
    assert s == 422
    import json, urllib.request, urllib.error
    req = urllib.request.Request(client.base + "/api/crops/recommend", data=b"{bad", method="POST", headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req)
        code = 200
    except urllib.error.HTTPError as e:
        code, body = e.code, json.loads(e.read())
    assert code == 400 and body["error"]["code"] == "invalid_json"
