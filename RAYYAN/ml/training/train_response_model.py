"""
RAYYAN — تدريب نموذج استجابة رطوبة التربة (Regression)
=========================================================
الهدف: delta_vwc = post_vwc - pre_vwc  (m³/m³)
المدخلات: التسعة المذكورة في MODEL_CARD_AR.md فقط، وكلها متاحة قبل قرار 04:00.
التقسيم: كما في split_manifest دون تغيير — 2024 تدريب، يناير–يونيو 2025 تحقق، يوليو–ديسمبر 2025 اختبار.

قواعد صارمة:
- اختيار الإعدادات يتم على التحقق فقط. بيانات الاختبار لا تدخل التدريب ولا الاختيار.
- لا يدخل الحجم المنفذ أو post_vwc أو المطر المتحقق أو أي معرّف في المدخلات.
- كل الوسوم من محاكاة؛ المقاييس لا تمثل دقة ميدانية.

التشغيل:
    python ml/training/train_response_model.py
"""
from __future__ import annotations

import hashlib
import itertools
import json
import platform
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/database/rayyan.sqlite"
OUT = ROOT / "ml/saved_models"
SEED = 20261107  # من config.json في الحزمة

FEATURES = ["pre_vwc", "planned_volume_l", "planned_duration_min", "root_depth_m", "area_m2",
            "forecast_rain_mm", "forecast_et0_mm", "doy_sin", "doy_cos"]
TARGET = "delta_vwc"
# أعمدة ممنوعة لأنها تُعرف بعد القرار أو معرّفات (من MODEL_CARD و demo_model_card.json)
FORBIDDEN = ["delivered_volume_l", "actual_end", "post_vwc", "delta_vwc", "scenario_id", "confirmed_cause",
             "realized_weather", "decision_id", "zone_id", "issued_at", "input_sample_id", "forecast_id",
             "features_available_at"]
PACKAGE_FIXED = {"n_estimators": 80, "max_depth": 8, "min_samples_leaf": 4}
GRID = {"n_estimators": [200, 400], "max_depth": [None, 6, 10], "min_samples_leaf": [1, 3, 5],
        "max_features": [1.0, 0.6, "sqrt"]}


# ------------------------------------------------------------------ تحميل وتحقق
def load(con) -> pd.DataFrame:
    f = pd.read_sql("select * from ml_features", con)
    t = pd.read_sql("select * from ml_targets", con)
    s = pd.read_sql("select * from split_manifest", con)
    d = pd.read_sql("select decision_id, predicted_delta_vwc as linear_preview_delta from decisions", con)
    o = pd.read_sql("select decision_id, confounding_flags from event_outcomes", con)
    for name, df in [("features", f), ("targets", t), ("split", s)]:
        assert df.decision_id.is_unique, f"decision_id مكرر في {name}"
    x = f.merge(t, on="decision_id", how="inner", validate="1:1")
    x = x.merge(s, on=["decision_id", "zone_id"], how="inner", validate="1:1")
    x = x.merge(d, on="decision_id", how="left", validate="1:1").merge(o, on="decision_id", how="left", validate="1:1")
    assert len(x) == len(f) == len(t) == len(s), "ربط Features/Targets/Split غير مكتمل"
    x["eligible"] = x["eligible"].astype(str).str.lower().isin(["1", "true"])
    return x


def validate(x: pd.DataFrame) -> dict:
    checks = {}
    checks["rows_total"] = int(len(x))
    checks["ineligible_or_missing_target"] = int((~x.eligible | x[TARGET].isna()).sum())
    checks["features_exclude_forbidden"] = not set(FEATURES) & set(FORBIDDEN)
    issued = pd.to_datetime(x.issued_at, utc=True)
    checks["features_available_before_decision"] = bool((pd.to_datetime(x.features_available_at, utc=True) <= issued).all())
    # كل وسوم جزء تُتاح قبل بداية الجزء التالي (لا تسرب زمني)
    e = x[x.eligible & x[TARGET].notna()]
    lab = pd.to_datetime(e.label_available_at, utc=True); iss = pd.to_datetime(e.issued_at, utc=True)
    checks["train_labels_before_validation_start"] = bool(lab[e.split == "train"].max() < iss[e.split == "validation"].min())
    checks["validation_labels_before_test_start"] = bool(lab[e.split == "validation"].max() < iss[e.split == "test"].min())
    checks["no_missing_features_in_eligible"] = bool(not e[FEATURES].isna().any().any())
    checks["split_periods"] = {s: [str(pd.to_datetime(g.issued_at).min().date()), str(pd.to_datetime(g.issued_at).max().date())]
                               for s, g in e.groupby("split")}
    failed = [k for k, v in checks.items() if v is False]
    if failed:
        raise SystemExit(f"فشل التحقق من البيانات: {failed}")
    return checks


def metrics(y, p) -> dict:
    return {"n": int(len(y)), "mae": float(mean_absolute_error(y, p)),
            "rmse": float(np.sqrt(mean_squared_error(y, p))), "r2": float(r2_score(y, p))}


def rf(params: dict) -> RandomForestRegressor:
    return RandomForestRegressor(random_state=SEED, n_jobs=-1, **params)


# ------------------------------------------------------------------ التدريب
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    x = load(con)
    checks = validate(x)
    data = x[x.eligible & x[TARGET].notna()].copy()
    tr, va, te = (data[data.split == s] for s in ("train", "validation", "test"))
    dev = pd.concat([tr, va])
    print(f"البيانات: تدريب {len(tr)} · تحقق {len(va)} · اختبار {len(te)} · مستبعد {checks['ineligible_or_missing_target']}")

    # 1) إعادة إنتاج تجربة الحزمة بإعداداتها الثابتة (للتحقق من سلامة القراءة)
    pkg = RandomForestRegressor(random_state=SEED, n_jobs=1, **PACKAGE_FIXED)
    pkg.fit(tr[FEATURES], tr[TARGET])
    reproduction = {s: metrics(df[TARGET], pkg.predict(df[FEATURES])) for s, df in [("validation", va), ("test", te)]}

    # 2) اختيار الإعدادات على التحقق فقط
    search = []
    for vals in itertools.product(*GRID.values()):
        params = dict(zip(GRID.keys(), vals))
        m = rf(params).fit(tr[FEATURES], tr[TARGET])
        search.append({"params": params, **metrics(va[TARGET], m.predict(va[FEATURES]))})
    search.append({"params": {**PACKAGE_FIXED, "max_features": 1.0}, **reproduction["validation"], "note": "package_fixed"})
    best = min(search, key=lambda r: r["rmse"])
    best_params = best["params"]
    print("أفضل إعداد على التحقق:", best_params, f"RMSE={best['rmse']:.5f}")

    # 3) النموذج المجمد (2024 فقط) والنموذج المحدث (2024 + يناير–يونيو 2025) — كلاهما يُقيَّم على نفس الاختبار
    frozen = rf(best_params).fit(tr[FEATURES], tr[TARGET])
    deployed = rf(best_params).fit(dev[FEATURES], dev[TARGET])

    # 4) خطوط الأساس
    train_mean = float(tr[TARGET].mean()); dev_mean = float(dev[TARGET].mean())
    results = []
    def add(model_id, label_ar, split, y, p, trained_on):
        results.append({"model_id": model_id, "label_ar": label_ar, "split": split, "trained_on": trained_on, **metrics(y, p)})
    for split, df in [("validation", va), ("test", te)]:
        add("baseline_zero_change", "خط أساس: لا تغير", split, df[TARGET], np.zeros(len(df)), "none")
        add("baseline_train_mean", "خط أساس: متوسط التدريب", split, df[TARGET],
            np.full(len(df), train_mean if split == "validation" else dev_mean), "train" if split == "validation" else "train+validation")
        lin = df["linear_preview_delta"]
        add("baseline_linear_rule", "معادلة المشروع الخطية (decisions.predicted_delta_vwc)", split, df[TARGET], lin.fillna(0), "formula")
        add("rf_package_fixed", "Random Forest بإعدادات الحزمة الثابتة", split, df[TARGET], pkg.predict(df[FEATURES]), "train")
        add("rf_selected_frozen", "Random Forest المختار — مدرب على 2024", split, df[TARGET], frozen.predict(df[FEATURES]), "train")
    add("rf_selected_deployed", "Random Forest المختار — مدرب حتى يونيو 2025 (المستخدم في النظام)", "test",
        te[TARGET], deployed.predict(te[FEATURES]), "train+validation")

    # 5) تحليل الخطأ على الاختبار (للنموذج المستخدم)
    pte = deployed.predict(te[FEATURES])
    err = te.assign(pred=pte, abs_err=np.abs(pte - te[TARGET]))
    by_zone = {z: metrics(g[TARGET], g.pred) for z, g in err.groupby("zone_id")}
    by_flag = {f: {"n": int(len(g)), "mae": float(g.abs_err.mean())} for f, g in err.groupby(err.confounding_flags.fillna("none"))}
    by_month = [{"month": m, "n": int(len(g)), "mae": float(g.abs_err.mean()),
                 "mean_actual": float(g[TARGET].mean()), "mean_pred": float(g.pred.mean())}
                for m, g in err.groupby(pd.to_datetime(err.issued_at).dt.strftime("%Y-%m"))]

    # 6) أهمية المدخلات
    impurity = sorted(({"feature": f, "importance": float(v)} for f, v in zip(FEATURES, deployed.feature_importances_)),
                      key=lambda r: -r["importance"])
    pi = permutation_importance(deployed, te[FEATURES], te[TARGET], n_repeats=20, random_state=SEED,
                                scoring="neg_root_mean_squared_error", n_jobs=-1)
    permutation = sorted(({"feature": f, "rmse_increase": float(m), "std": float(s)}
                          for f, m, s in zip(FEATURES, pi.importances_mean, pi.importances_std)),
                         key=lambda r: -r["rmse_increase"])

    # 7) التنبؤات لكل عملية مؤهلة — خارج العينة فقط للتحقق (المجمد) والاختبار (المستخدم)
    preds = []
    for split, df, model, oos in [("train", tr, deployed, False), ("validation", va, frozen, True), ("test", te, deployed, True)]:
        for did, z, y, p in zip(df.decision_id, df.zone_id, df[TARGET], model.predict(df[FEATURES])):
            preds.append({"decision_id": did, "zone_id": z, "split": split, "actual_delta_vwc": float(y),
                          "predicted_delta_vwc": float(p), "out_of_sample": oos})
    pred_df = pd.DataFrame(preds)
    pred_df.to_csv(OUT / "predictions.csv", index=False, encoding="utf-8")

    # 8) نطاقات التدريب لتحذيرات "خارج النطاق" في الـAPI
    ranges = {f: {"min": float(dev[f].min()), "max": float(dev[f].max()), "p05": float(dev[f].quantile(.05)),
                  "p95": float(dev[f].quantile(.95))} for f in FEATURES}
    data_hash = hashlib.sha256(pd.util.hash_pandas_object(data[["decision_id", *FEATURES, TARGET, "split"]], index=False)
                               .values.tobytes()).hexdigest()
    version = f"rf-delta-vwc-{datetime.now(timezone.utc):%Y%m%d}-{data_hash[:8]}"
    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    joblib.dump({"model": deployed, "features": FEATURES, "version": version, "trained_at": trained_at,
                 "target": TARGET, "feature_ranges": ranges, "params": best_params, "seed": SEED,
                 "sklearn_version": sklearn.__version__}, OUT / "response_model.joblib", compress=3)

    package_reference = pd.read_csv(ROOT / "data/processed/package/quality/demo_model_metrics.csv")
    report = {
        "model_version": version, "trained_at": trained_at,
        "task": "regression", "target": TARGET, "target_unit": "m3/m3", "algorithm": "RandomForestRegressor",
        "features": FEATURES, "forbidden_inputs": FORBIDDEN,
        "data": {"source": "data/database/rayyan.sqlite: ml_features + ml_targets + split_manifest",
                 "data_hash_sha256": data_hash, "checks": checks,
                 "counts": {"train": len(tr), "validation": len(va), "test": len(te),
                            "excluded": checks["ineligible_or_missing_target"], "deployed_fit": len(dev)},
                 "label_origin": "simulation_only — ليست قياسات ميدانية"},
        "selection": {"method": "grid on validation RMSE only; test untouched", "grid": GRID,
                      "n_candidates": len(search), "best_params": best_params, "best_validation": best,
                      "top10": sorted(search, key=lambda r: r["rmse"])[:10]},
        "results": results,
        "package_reproduction": {"ours": reproduction,
                                 "package_reported": json.loads(package_reference.to_json(orient="records"))},
        "error_analysis_test": {"by_zone": by_zone, "by_confounding_flag": by_flag, "by_month": by_month},
        "importance": {"impurity": impurity, "permutation_test": permutation,
                       "note": "Permutation على الاختبار بعد الاختيار — للتفسير فقط، لم يُستخدم في اختيار أي إعداد"},
        "feature_ranges": ranges,
        "software": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                     "scikit-learn": sklearn.__version__, "seed": SEED},
        "limitations": [
            "الوسوم من حساسات محاكاة؛ لا توجد حقيقة ميدانية مستقلة.",
            "موقع واحد ومنطقتان؛ التقسيم زمني فقط ولا يختبر التعميم على مواقع جديدة.",
            "السجلات متتابعة زمنيًا ومترابطة؛ ليست مكررات مستقلة.",
            "النموذج يتنبأ بالاستجابة لخطة معطاة ولا يحدد الجرعة المثلى.",
            "الحجم المخطط في التدريب بين 16 و80 لترًا والمدة = الحجم ÷ 2 لتر/دقيقة دائمًا.",
        ],
    }
    (OUT / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    # 9) حفظ التنبؤات في قاعدة البيانات (جدول تطبيق مرتبط بـ decision_id)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("""CREATE TABLE IF NOT EXISTS app_model_predictions (
        decision_id TEXT NOT NULL REFERENCES decisions(decision_id), model_version TEXT NOT NULL,
        split TEXT NOT NULL, actual_delta_vwc REAL NOT NULL, predicted_delta_vwc REAL NOT NULL,
        out_of_sample INTEGER NOT NULL, PRIMARY KEY (decision_id, model_version))""")
    con.execute("DELETE FROM app_model_predictions")
    con.executemany("INSERT INTO app_model_predictions VALUES (?,?,?,?,?,?)",
                    [(r.decision_id, version, r.split, r.actual_delta_vwc, r.predicted_delta_vwc, int(r.out_of_sample))
                     for r in pred_df.itertuples()])
    con.commit(); con.close()

    print("\nالنتائج (MAE / RMSE / R²):")
    for r in results:
        print(f"  {r['split']:<10} {r['model_id']:<24} {r['mae']:.5f}  {r['rmse']:.5f}  {r['r2']:+.3f}")
    print("\nإعادة إنتاج تجربة الحزمة على الاختبار:", round(reproduction["test"]["r2"], 4))
    print("✓ حُفظ:", OUT / "response_model.joblib")


if __name__ == "__main__":
    main()
