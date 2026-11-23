"""
RAYYAN v2 — نموذج الرطوبة بعد 6 ساعات لأربع مناطق (نخيل، برسيم، خضار، نجيل)
==========================================================================
المصدر: data/raw/RAYYAN_ML_Ready.xlsx بعد استيراده إلى جداول v2_ في SQLite (scripts/prepare_data.py).
الهدف: target_after_6h_VWC_pct (نسبة مئوية). المدخلات: الحقول ذات role=feature في ورقة Dictionary (24 حقلًا).

القواعد (من ورقة ReadMe في الملف):
- التقسيم temporal_split كما هو؛ صفوف gap مستبعدة؛ الأهداف الناقصة تُحذف ولا تُعوَّض.
- التعويض بالوسيط والترميز يتعلمان من التدريب فقط داخل Pipeline.
- ممنوع: الحجم والتدفق الفعليان، نتيجة الرطوبة، الطقس المتحقق، وجداول Simulation_Audit.
- الاختيار على التحقق فقط؛ الاختبار لا يدخل أي اختيار.

لم تُرفق ملفات feature_manifest.json و README_AR.md وكود الحزمة؛ لذلك:
- قائمة المدخلات من Dictionary (role=feature).
- معادلة simple_water_balance غير موثقة في الملف، فلا نعيد حسابها؛ نعرض أرقامها كما أوردها الملف مع وسم «مُبلَّغ في الملف».

التشغيل:  python ml/training/train_v2_model.py
"""
from __future__ import annotations

import hashlib
import itertools
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data/database/rayyan.sqlite"
OUT = ROOT / "ml/saved_models/v2"
SEED = 42603  # بذرة المحاكاة المعلنة في ReadMe
TARGET = "target_after_6h_VWC_pct"
GRID = {"n_estimators": [300], "max_depth": [None, 12, 20], "min_samples_leaf": [1, 3, 5], "max_features": [1.0, 0.5, "sqrt"]}


def metrics(y, p):
    return {"n": int(len(y)), "mae": float(mean_absolute_error(y, p)),
            "rmse": float(np.sqrt(mean_squared_error(y, p))), "r2": float(r2_score(y, p))}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    dic = pd.read_sql("select * from v2_dictionary", con)
    df = pd.read_sql("select * from v2_ml_ready", con)
    w = pd.read_sql("select * from v2_weather", con)
    reported = pd.read_sql("select * from v2_reported_baselines", con)

    feats = dic[(dic.sheet == "ML_Ready") & (dic.role == "feature")].field.tolist()
    forbidden = dic[dic.role.isin(["post_event_do_not_use_pre_event", "future_realized_do_not_use",
                                   "simulation_truth_do_not_train", "target"])].field.unique().tolist()
    cat = [f for f in feats if not pd.api.types.is_numeric_dtype(df[f])]
    num = [f for f in feats if f not in cat]

    # ---------------- فحوص قبل التدريب
    checks = {}
    checks["features_from_dictionary"] = len(feats)
    checks["features_exclude_forbidden"] = not (set(feats) & (set(forbidden) - {"event_id", "zone_id", "provenance"}))
    checks["no_identifier_inputs"] = not (set(feats) & {"event_id", "zone_id", "weather_id", "feature_cutoff_at", "measured_at", "temporal_split"})
    checks["decision_before_measurement"] = bool((pd.to_datetime(df.feature_cutoff_at) < pd.to_datetime(df.measured_at)).all())
    mw = df.merge(w, on="weather_id", suffixes=("", "_w"))
    checks["weather_issued_before_decision"] = bool((pd.to_datetime(mw.issued_at) <= pd.to_datetime(mw.feature_cutoff_at)).all())
    checks["features_use_forecast_not_realized"] = bool(np.allclose(mw.et0_forecast_24h_mm, mw.et0_forecast_24h_mm_w)
                                                        and np.allclose(mw.rain_forecast_24h_mm, mw.rain_forecast_24h_mm_w))
    t0 = {s: pd.to_datetime(g.feature_cutoff_at) for s, g in df.groupby("temporal_split")}
    checks["train_before_validation"] = bool(t0["train"].max() < t0["validation"].min())
    checks["validation_before_test"] = bool(t0["validation"].max() < t0["test"].min())
    checks["split_periods"] = {s: [str(v.min().date()), str(v.max().date())] for s, v in t0.items()}
    checks["rows_total"] = int(len(df)); checks["gap_rows_excluded"] = int((df.temporal_split == "gap").sum())
    checks["missing_targets_dropped"] = int(df[TARGET].isna().sum())
    checks["missing_current_reading"] = int(df.before_VWC_pct.isna().sum())
    failed = [k for k, v in checks.items() if v is False]
    if failed:
        raise SystemExit(f"فشل التحقق: {failed}")

    data = df[df[TARGET].notna() & df.temporal_split.isin(["train", "validation", "test"])].copy()
    tr, va, te = (data[data.temporal_split == s] for s in ("train", "validation", "test"))
    dev = pd.concat([tr, va])

    def pipe(params):
        pre = ColumnTransformer([("num", SimpleImputer(strategy="median"), num),
                                 ("cat", OneHotEncoder(handle_unknown="ignore"), cat)])
        return Pipeline([("pre", pre), ("model", RandomForestRegressor(random_state=SEED, n_jobs=-1, **params))])

    # ---------------- الاختيار على التحقق فقط
    search = []
    for vals in itertools.product(*GRID.values()):
        p = dict(zip(GRID.keys(), vals))
        m = pipe(p).fit(tr[feats], tr[TARGET])
        search.append({"params": p, **metrics(va[TARGET], m.predict(va[feats]))})
    best = min(search, key=lambda r: r["rmse"])
    print("أفضل إعداد على التحقق:", best["params"], f"RMSE={best['rmse']:.4f}")
    frozen = pipe(best["params"]).fit(tr[feats], tr[TARGET])
    deployed = pipe(best["params"]).fit(dev[feats], dev[TARGET])

    # ---------------- خطوط الأساس المحسوبة هنا
    med_tr, med_dev = float(tr[TARGET].median()), float(dev[TARGET].median())

    def persistence(d, fallback):
        return d.before_VWC_pct.fillna(d.lag1_before_VWC_pct).fillna(fallback)

    results = []
    def add(mid, label, split, y, p, on, source="computed_here"):
        results.append({"model_id": mid, "label_ar": label, "split": split, "trained_on": on, "source": source, **metrics(y, p)})
    for split, d, med in [("validation", va, med_tr), ("test", te, med_dev)]:
        add("train_median", "خط أساس: الوسيط", split, d[TARGET], np.full(len(d), med), "train" if split == "validation" else "train+validation")
        add("persistence", "خط أساس: الرطوبة الحالية تبقى كما هي", split, d[TARGET], persistence(d, med), "none")
        add("rf_frozen", "Random Forest — مدرب على التدريب فقط", split, d[TARGET], frozen.predict(d[feats]), "train")
    add("rf_deployed", "Random Forest — مدرب على التدريب+التحقق (المستخدم)", "test", te[TARGET], deployed.predict(te[feats]), "train+validation")
    for r in reported.itertuples():
        results.append({"model_id": f"reported_{r.model}", "label_ar": f"مُبلَّغ في الملف: {r.model}", "split": r.split,
                        "trained_on": "حسب الملف", "source": "reported_in_file", "n": int(r.n),
                        "mae": float(r.MAE_pp), "rmse": float(r.RMSE_pp), "r2": float(r.R2)})

    # ---------------- تحليل الخطأ والأهمية
    pte = deployed.predict(te[feats])
    err = te.assign(pred=pte)
    zones = pd.read_sql("select zone_id, zone_name, crop from v2_zones", con).set_index("zone_id")
    by_zone = {z: {**metrics(g[TARGET], g.pred), "crop": zones.loc[z, "crop"], "zone_name": zones.loc[z, "zone_name"]}
               for z, g in err.groupby("zone_id")}
    by_missing = {str(k): {"n": int(len(g)), "mae": float(mean_absolute_error(g[TARGET], g.pred))} for k, g in err.groupby("before_missing")}
    pi = permutation_importance(deployed, te[feats], te[TARGET], n_repeats=10, random_state=SEED,
                                scoring="neg_root_mean_squared_error", n_jobs=-1)
    permutation = sorted(({"feature": f, "rmse_increase": float(m), "std": float(s)} for f, m, s in
                          zip(feats, pi.importances_mean, pi.importances_std)), key=lambda r: -r["rmse_increase"])
    desc = dict(zip(dic[dic.sheet == "ML_Ready"].field, dic[dic.sheet == "ML_Ready"].description_ar))

    # ---------------- الحفظ
    ranges = {f: {"min": float(dev[f].min()), "max": float(dev[f].max())} for f in num}
    data_hash = hashlib.sha256(pd.util.hash_pandas_object(data[["event_id", *feats, TARGET, "temporal_split"]], index=False)
                               .values.tobytes()).hexdigest()
    version = f"rf-v2-vwc6h-{datetime.now(timezone.utc):%Y%m%d}-{data_hash[:8]}"
    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    joblib.dump({"model": deployed, "features": feats, "numeric": num, "categorical": cat, "version": version,
                 "trained_at": trained_at, "feature_ranges": ranges, "params": best["params"], "seed": SEED},
                OUT / "v2_model.joblib", compress=3)
    preds = []
    for split, d, m, oos in [("train", tr, deployed, False), ("validation", va, frozen, True), ("test", te, deployed, True)]:
        for eid, z, y, p in zip(d.event_id, d.zone_id, d[TARGET], m.predict(d[feats])):
            preds.append((eid, version, split, z, float(y), float(p), int(oos)))
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("""CREATE TABLE IF NOT EXISTS app_v2_predictions (event_id TEXT NOT NULL REFERENCES v2_ml_ready(event_id),
        model_version TEXT NOT NULL, split TEXT NOT NULL, zone_id TEXT NOT NULL REFERENCES v2_zones(zone_id),
        actual_vwc_pct REAL NOT NULL, predicted_vwc_pct REAL NOT NULL, out_of_sample INTEGER NOT NULL,
        PRIMARY KEY (event_id, model_version))""")
    con.execute("DELETE FROM app_v2_predictions")
    con.executemany("INSERT INTO app_v2_predictions VALUES (?,?,?,?,?,?,?)", preds)
    con.commit(); con.close()

    report = {
        "model_version": version, "trained_at": trained_at, "dataset": "RAYYAN ML dataset v2 (RAYYAN_ML_Ready.xlsx)",
        "task": "regression", "target": TARGET, "target_unit": "VWC % (نقطة مئوية)", "horizon": "6 ساعات بعد قرار 06:00 UTC",
        "algorithm": "RandomForestRegressor + SimpleImputer(median) + OneHotEncoder", "features": feats,
        "numeric_features": num, "categorical_features": cat, "feature_descriptions_ar": desc, "forbidden_inputs": forbidden,
        "data": {"source": "SQLite v2_ml_ready (من الورقة ML_Ready)", "data_hash_sha256": data_hash, "checks": checks,
                 "counts": {"train": len(tr), "validation": len(va), "test": len(te), "deployed_fit": len(dev),
                            "gap_excluded": checks["gap_rows_excluded"], "missing_targets": checks["missing_targets_dropped"]},
                 "label_origin": "SIMULATED — ليست قياسات ميدانية"},
        "selection": {"method": "grid on validation RMSE only; test untouched", "grid": GRID, "n_candidates": len(search),
                      "best_params": best["params"], "best_validation": {k: best[k] for k in ("mae", "rmse", "r2")},
                      "top5": sorted(search, key=lambda r: r["rmse"])[:5]},
        "results": results,
        "error_analysis_test": {"by_zone": by_zone, "by_missing_reading": by_missing},
        "importance": {"permutation_test": permutation, "note": "Permutation على الاختبار بعد الاختيار — للتفسير فقط"},
        "feature_ranges": ranges,
        "software": {"scikit-learn": sklearn.__version__, "pandas": pd.__version__, "seed": SEED},
        "not_available": ["feature_manifest.json و README_AR.md وكود الحزمة لم تُرفق؛ المدخلات من ورقة Dictionary.",
                          "معادلة simple_water_balance غير موثقة في الملف؛ نتائجها معروضة كما أوردها الملف دون إعادة حساب."],
        "limitations": [
            "كل السجلات SIMULATED بالبذرة 42603؛ المقاييس تقيس تعلم المحاكاة لا دقة ميدانية ولا توفير ماء.",
            "نفس المناطق الأربع في كل الأجزاء؛ التقسيم الزمني لا يثبت التعميم على مزرعة جديدة.",
            "خصائص المنطقة (المحصول، التربة، العمق، الكفاءة…) ثابتة لكل منطقة، فهي تعمل عمليًا كمعرّف للمنطقة.",
            "مجموعة مستقلة عن نظام البرمودا: لا ترتبط بقراراته أو قاعدة أحداثه، ولا يغذيها محرك القرار rule_v1.",
        ],
    }
    (OUT / "v2_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nالنتائج (MAE / RMSE / R² — نقاط مئوية):")
    for r in results:
        print(f"  {r['split']:<10} {r['model_id']:<34} {r['mae']:.4f}  {r['rmse']:.4f}  {r['r2']:+.4f}")
    print("✓ حُفظ:", OUT / "v2_model.joblib")


if __name__ == "__main__":
    main()
