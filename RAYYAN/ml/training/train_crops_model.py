"""
RAYYAN — نموذج المحاصيل الأربع (نخيل، برسيم، خضار، نجيل): الرطوبة بعد 6 ساعات من قرار 06:00 UTC
=================================================================================================
نموذج مستقل عن نموذج البرمودا (لا تُخلط البيانات): المصدر data/raw/RAYYAN_ML_Ready.xlsx بعد استيراده إلى جداول v2_.
لا يحذف ولا يستبدل النموذج الثاني الأصلي في ml/saved_models/v2؛ يكتب في ml/saved_models/crops فقط.

ما يضيفه مقارنة بـ train_v2_model.py:
  - مقارنة عائلات نماذج: Ridge، Random Forest، HistGradientBoosting (مع قيد رتابة فيزيائي: ماء أكثر ⇒ رطوبة لا تقل)،
    وكل منها بهدف مطلق أو بهدف «التغير عن الرطوبة الحالية».
  - خط أساس فيزيائي محسوب هنا: موازنة ماء 6 ساعات بمعادلة موثقة (crops_lib.water_balance_6h).
  - فحص استجابة النموذج للكمية (ضروري لأن التطبيق يستخدمه لاقتراح الكمية).

القواعد: التقسيم الزمني temporal_split كما في الملف؛ صفوف gap مستبعدة؛ الأهداف الناقصة تُحذف؛ كل المعالجة داخل Pipeline
تتعلم من التدريب فقط؛ الاختيار على التحقق فقط؛ الاختبار يُستخدم مرة واحدة للتقرير.

التشغيل:  python ml/training/train_crops_model.py
"""
from __future__ import annotations

import hashlib
import itertools
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.services.crops_lib import TARGET, DeltaRegressor, water_balance_6h  # noqa: E402

DB = ROOT / "data/database/rayyan.sqlite"
OUT = ROOT / "ml/saved_models/crops"
SEED = 42603
FORBIDDEN_ROLES = ["post_event_do_not_use_pre_event", "future_realized_do_not_use", "simulation_truth_do_not_train", "target"]
MONO = ("planned_volume_L", "planned_duration_min")


def metrics(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    return {"n": int(len(y)), "mae": float(mean_absolute_error(y, p)), "rmse": float(np.sqrt(mean_squared_error(y, p))),
            "r2": float(r2_score(y, p))}


def build(family: str, params: dict, num: list[str], cat: list[str]):
    ohe = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    if family == "ridge":
        pre = ColumnTransformer([("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), num),
                                 ("cat", ohe, cat)])
        est = Ridge(**params)
    elif family == "rf":
        pre = ColumnTransformer([("num", SimpleImputer(strategy="median"), num), ("cat", ohe, cat)])
        est = RandomForestRegressor(random_state=SEED, n_jobs=-1, n_estimators=300, **params)
    elif family == "hgb":  # يتعامل مع القيم الناقصة أصليًا؛ قيد رتابة على الحجم والمدة
        pre = ColumnTransformer([("num", "passthrough", num), ("cat", ohe, cat)], verbose_feature_names_out=False)
        pre.set_output(transform="pandas")
        est = HistGradientBoostingRegressor(random_state=SEED, max_iter=400, monotonic_cst={m: 1 for m in MONO}, **params)
    else:
        raise ValueError(family)
    return Pipeline([("pre", pre), ("model", est)])


GRIDS = {
    "ridge": {"alpha": [0.1, 1.0, 10.0]},
    "rf": {"max_depth": [None, 12], "min_samples_leaf": [1, 3], "max_features": [0.5, 1.0]},
    "hgb": {"learning_rate": [0.05, 0.1], "max_leaf_nodes": [15, 31], "l2_regularization": [0.0, 1.0]},
}
LABELS = {"ridge": "Ridge (خطي)", "rf": "Random Forest", "hgb": "HistGradientBoosting + قيد رتابة"}
MODE_AR = {"absolute": "هدف مطلق", "delta": "هدف التغير", "hybrid": "هجين: تصحيح موازنة الماء"}
MONOTONIC_MIN_PCT = 99.0  # شرط اختيار مُعلن مسبقًا: التطبيق يقترح كميات بالنموذج، فيجب ألا تقل الرطوبة المتوقعة بزيادة الماء


def candidates(num, cat, wb_cap):
    for family, grid in GRIDS.items():
        for vals in itertools.product(*grid.values()):
            params = dict(zip(grid.keys(), vals))
            for target_mode in ("absolute", "delta", "hybrid"):
                def make(family=family, params=params, target_mode=target_mode):
                    p = build(family, params, num, cat)
                    if target_mode == "delta":
                        return DeltaRegressor(p, base="persistence")
                    if target_mode == "hybrid":
                        return DeltaRegressor(p, base="water_balance", cap=wb_cap)
                    return p
                yield {"family": family, "params": params, "target_mode": target_mode, "make": make}


def response_check(model, d: pd.DataFrame, feats: list[str]) -> dict:
    """هل يزيد التنبؤ (أو يثبت) عند زيادة كمية الري؟ يُحسب على الاختبار لكل صف بثلاثة مستويات."""
    base = d[feats].copy()
    lo, hi = base.copy(), base.copy()
    lo["planned_volume_L"], lo["planned_duration_min"] = 0.0, 0.0
    hi["planned_volume_L"] = base["planned_volume_L"] * 1.25 + 100
    hi["planned_duration_min"] = hi["planned_volume_L"] / base["nominal_flow_L_min"]
    p0, p1, p2 = (model.predict(x) for x in (lo, base, hi))
    ok = (p1 >= p0 - 1e-9) & (p2 >= p1 - 1e-9)
    return {"rows": int(len(d)), "monotonic_rows_pct": float(100 * ok.mean()),
            "mean_gain_planned_vs_none_pp": float(np.mean(p1 - p0)), "mean_gain_more_vs_planned_pp": float(np.mean(p2 - p1))}


def main():
    t_start = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    dic = pd.read_sql("select * from v2_dictionary", con)
    df = pd.read_sql("select * from v2_ml_ready", con)
    w = pd.read_sql("select * from v2_weather", con)
    zones = pd.read_sql("select * from v2_zones", con).set_index("zone_id")
    reported = pd.read_sql("select * from v2_reported_baselines", con)

    feats = dic[(dic.sheet == "ML_Ready") & (dic.role == "feature")].field.tolist()
    forbidden = dic[dic.role.isin(FORBIDDEN_ROLES)].field.unique().tolist()
    cat = [f for f in feats if not pd.api.types.is_numeric_dtype(df[f])]
    num = [f for f in feats if f not in cat]

    # ---------------- فحوص منع التسرب قبل التدريب (يتوقف التدريب إن فشل أي منها)
    checks = {"features_from_dictionary": len(feats),
              "features_exclude_forbidden": not (set(feats) & (set(forbidden) - {"event_id", "zone_id", "provenance"})),
              "no_identifier_inputs": not (set(feats) & {"event_id", "zone_id", "weather_id", "feature_cutoff_at", "measured_at", "temporal_split"}),
              "decision_before_measurement": bool((pd.to_datetime(df.feature_cutoff_at) < pd.to_datetime(df.measured_at)).all())}
    mw = df.merge(w, on="weather_id", suffixes=("", "_w"))
    checks["weather_issued_before_decision"] = bool((pd.to_datetime(mw.issued_at) <= pd.to_datetime(mw.feature_cutoff_at)).all())
    checks["features_use_forecast_not_realized"] = bool(np.allclose(mw.et0_forecast_24h_mm, mw.et0_forecast_24h_mm_w)
                                                        and np.allclose(mw.rain_forecast_24h_mm, mw.rain_forecast_24h_mm_w))
    t0 = {s: pd.to_datetime(g.feature_cutoff_at) for s, g in df.groupby("temporal_split")}
    checks["train_before_validation"] = bool(t0["train"].max() < t0["validation"].min())
    checks["validation_before_test"] = bool(t0["validation"].max() < t0["test"].min())
    lag_ok = df.sort_values("feature_cutoff_at").groupby("zone_id").apply(
        lambda g: bool(np.allclose(g.lag1_before_VWC_pct.iloc[1:].to_numpy(), g.before_VWC_pct.shift(1).iloc[1:].to_numpy(), equal_nan=True)),
        include_groups=False)
    checks["lag1_is_previous_day_reading"] = bool(lag_ok.all())
    checks["split_periods"] = {s: [str(v.min().date()), str(v.max().date())] for s, v in t0.items()}
    checks["rows_total"] = int(len(df))
    checks["gap_rows_excluded"] = int((df.temporal_split == "gap").sum())
    checks["missing_targets_dropped"] = int(df[TARGET].isna().sum())
    checks["missing_current_reading"] = int(df.before_VWC_pct.isna().sum())
    failed = [k for k, v in checks.items() if v is False]
    if failed:
        raise SystemExit(f"فشل التحقق: {failed}")
    print("✓ فحوص التسرب:", {k: v for k, v in checks.items() if isinstance(v, bool)})

    data = df[df[TARGET].notna() & df.temporal_split.isin(["train", "validation", "test"])].copy()
    tr, va, te = (data[data.temporal_split == s] for s in ("train", "validation", "test"))
    dev = pd.concat([tr, va])
    print(f"التدريب {len(tr)} · التحقق {len(va)} · الاختبار {len(te)}")

    med_tr, med_dev = float(tr[TARGET].median()), float(dev[TARGET].median())
    fb_tr, fb_dev = float(tr.before_VWC_pct.median()), float(dev.before_VWC_pct.median())
    # سقف معادلة موازنة الماء يُختار على التحقق فقط (يُستخدم في خط الأساس وفي النموذج الهجين)
    wb_cap = min(("saturation", "field_capacity"), key=lambda cap: metrics(va[TARGET], water_balance_6h(va, fb_tr, cap))["rmse"])

    # ---------------- البحث على التحقق فقط: الدقة + فحص الاستجابة للكمية
    search = []
    for c in candidates(num, cat, wb_cap):
        t = time.time()
        m = c["make"]().fit(tr[feats], tr[TARGET])
        search.append({"family": c["family"], "params": c["params"], "target_mode": c["target_mode"], "make": c["make"],
                       "fit_seconds": round(time.time() - t, 2), **metrics(va[TARGET], m.predict(va[feats])),
                       "monotonic_val_pct": response_check(m, va, feats)["monotonic_rows_pct"]})
    eligible = [r for r in search if r["monotonic_val_pct"] >= MONOTONIC_MIN_PCT] or search
    best = min(eligible, key=lambda r: r["rmse"])
    best_unconstrained = min(search, key=lambda r: r["rmse"])
    best_by_family = {}
    for r in sorted(search, key=lambda r: r["rmse"]):
        best_by_family.setdefault((r["family"], r["target_mode"]), r)
    print(f"مؤهل (رتابة ≥ {MONOTONIC_MIN_PCT}% على التحقق): {len(eligible)}/{len(search)}")
    print("أفضل إعداد على التحقق:", best["family"], best["target_mode"], best["params"], f"RMSE={best['rmse']:.4f}",
          "| الأفضل دون شرط:", best_unconstrained["family"], best_unconstrained["target_mode"], f"{best_unconstrained['rmse']:.4f}")

    results = []
    def add(mid, label, split, y, p, trained_on, family="baseline", source="computed_here"):
        results.append({"model_id": mid, "label_ar": label, "family": family, "split": split, "trained_on": trained_on,
                        "source": source, **metrics(y, p)})

    for split, d, med, fb, on in [("validation", va, med_tr, fb_tr, "train"), ("test", te, med_dev, fb_dev, "train+validation")]:
        add("median", "خط أساس: الوسيط", split, d[TARGET], np.full(len(d), med), on)
        add("persistence", "خط أساس: الرطوبة الحالية تبقى كما هي", split, d[TARGET],
            d.before_VWC_pct.fillna(d.lag1_before_VWC_pct).fillna(med), "none")
        add("water_balance", f"خط أساس فيزيائي: موازنة ماء 6 ساعات (سقف: {'التشبع' if wb_cap == 'saturation' else 'السعة الحقلية'})",
            split, d[TARGET], water_balance_6h(d, fb, wb_cap), "none (معادلة)")

    # أفضل إعداد لكل عائلة/هدف: مدرب على التدريب فقط ويُقيَّم على التحقق والاختبار (للمقارنة الشفافة)
    for (fam, mode), r in best_by_family.items():
        m = r["make"]().fit(tr[feats], tr[TARGET])
        label = f"{LABELS[fam]} — {MODE_AR[mode]}"
        add(f"{fam}_{mode}", label, "validation", va[TARGET], m.predict(va[feats]), "train", fam)
        add(f"{fam}_{mode}", label, "test", te[TARGET], m.predict(te[feats]), "train", fam)

    deployed = best["make"]().fit(dev[feats], dev[TARGET])
    pte = deployed.predict(te[feats])
    dep_label = f"{LABELS[best['family']]} — {MODE_AR[best['target_mode']]} (المستخدم، تدريب+تحقق)"
    add("deployed", dep_label, "test", te[TARGET], pte, "train+validation", best["family"])
    for r in reported.itertuples():
        results.append({"model_id": f"reported_{r.model}", "label_ar": f"مُبلَّغ في الملف: {r.model}", "family": "reported",
                        "split": r.split, "trained_on": "حسب الملف", "source": "reported_in_file", "n": int(r.n),
                        "mae": float(r.MAE_pp), "rmse": float(r.RMSE_pp), "r2": float(r.R2)})

    # ---------------- تحليل الخطأ والتفسير
    err = te.assign(pred=pte, abs_err=np.abs(pte - te[TARGET]))
    by_zone = {}
    for z, g in err.groupby("zone_id"):
        pers = g.before_VWC_pct.fillna(g.lag1_before_VWC_pct).fillna(med_dev)
        by_zone[z] = {**metrics(g[TARGET], g.pred), "persistence_mae": float(mean_absolute_error(g[TARGET], pers)),
                      "crop": zones.loc[z, "crop"], "zone_name": zones.loc[z, "zone_name"]}
    by_missing = {str(k): {"n": int(len(g)), "mae": float(g.abs_err.mean())} for k, g in err.groupby("before_missing")}
    by_month = [{"month": k, "n": int(len(g)), "mae": float(g.abs_err.mean())}
                for k, g in err.groupby(err.feature_cutoff_at.str[:7])]
    response = response_check(deployed, te, feats)
    pi = permutation_importance(deployed, te[feats], te[TARGET], n_repeats=10, random_state=SEED,
                                scoring="neg_root_mean_squared_error", n_jobs=-1)
    permutation = sorted(({"feature": f, "rmse_increase": float(m), "std": float(s)} for f, m, s in
                          zip(feats, pi.importances_mean, pi.importances_std)), key=lambda r: -r["rmse_increase"])
    desc = dict(zip(dic[dic.sheet == "ML_Ready"].field, dic[dic.sheet == "ML_Ready"].description_ar))
    units = dict(zip(dic[dic.sheet == "ML_Ready"].field, dic[dic.sheet == "ML_Ready"].unit))

    # ---------------- الحفظ
    ranges = {f: {"min": float(dev[f].min()), "max": float(dev[f].max())} for f in num}
    zone_ranges = {z: {"planned_volume_L": [float(g.planned_volume_L.min()), float(g.planned_volume_L.max())],
                       "planned_volume_L_p95": float(g.planned_volume_L.quantile(0.95))} for z, g in dev.groupby("zone_id")}
    data_hash = hashlib.sha256(pd.util.hash_pandas_object(data[["event_id", *feats, TARGET, "temporal_split"]], index=False)
                               .values.tobytes()).hexdigest()
    version = f"crops-{best['family']}-{best['target_mode']}-{datetime.now(timezone.utc):%Y%m%d}-{data_hash[:8]}"
    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    joblib.dump({"model": deployed, "features": feats, "numeric": num, "categorical": cat, "version": version,
                 "trained_at": trained_at, "feature_ranges": ranges, "zone_ranges": zone_ranges, "family": best["family"],
                 "target_mode": best["target_mode"], "params": best["params"], "seed": SEED, "fallback_vwc": fb_dev},
                OUT / "crops_model.joblib", compress=3)

    preds = []
    frozen = best["make"]().fit(tr[feats], tr[TARGET])
    for split, d, m, oos in [("train", tr, deployed, 0), ("validation", va, frozen, 1), ("test", te, deployed, 1)]:
        for eid, z, y, p in zip(d.event_id, d.zone_id, d[TARGET], m.predict(d[feats])):
            preds.append((eid, version, split, z, float(y), float(p), oos))
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("""CREATE TABLE IF NOT EXISTS app_crop_predictions (event_id TEXT NOT NULL REFERENCES v2_ml_ready(event_id),
        model_version TEXT NOT NULL, split TEXT NOT NULL, zone_id TEXT NOT NULL REFERENCES v2_zones(zone_id),
        actual_vwc_pct REAL NOT NULL, predicted_vwc_pct REAL NOT NULL, out_of_sample INTEGER NOT NULL,
        PRIMARY KEY (event_id, model_version))""")
    con.execute("DELETE FROM app_crop_predictions")
    con.executemany("INSERT INTO app_crop_predictions VALUES (?,?,?,?,?,?,?)", preds)
    con.commit()
    con.close()

    test_rows = {r["model_id"]: r for r in results if r["split"] == "test"}
    report = {
        "model_version": version, "trained_at": trained_at, "dataset": "RAYYAN ML dataset v2 — المحاصيل الأربع (RAYYAN_ML_Ready.xlsx)",
        "task": "regression", "target": TARGET, "target_unit": "VWC % (نقطة مئوية)", "horizon": "6 ساعات بعد قرار 06:00 UTC",
        "algorithm": dep_label, "family": best["family"], "target_mode": best["target_mode"], "params": best["params"],
        "features": feats, "numeric_features": num, "categorical_features": cat, "feature_descriptions_ar": desc,
        "feature_units": units, "forbidden_inputs": forbidden,
        "data": {"source": "SQLite v2_ml_ready (من الورقة ML_Ready)", "data_hash_sha256": data_hash, "checks": checks,
                 "counts": {"train": len(tr), "validation": len(va), "test": len(te), "deployed_fit": len(dev),
                            "gap_excluded": checks["gap_rows_excluded"], "missing_targets": checks["missing_targets_dropped"]},
                 "label_origin": "SIMULATED — ليست قياسات ميدانية"},
        "selection": {"method": f"أقل RMSE على التحقق بين المرشحين الذين تكون استجابتهم للكمية رتيبة في ≥ {MONOTONIC_MIN_PCT}% من صفوف التحقق؛ "
                                "الاختبار لم يدخل أي اختيار", "n_candidates": len(search), "n_eligible": len(eligible),
                      "monotonic_min_pct": MONOTONIC_MIN_PCT, "grids": GRIDS,
                      "best": {k: best[k] for k in ("family", "target_mode", "params", "mae", "rmse", "r2", "monotonic_val_pct")},
                      "best_without_constraint": {k: best_unconstrained[k] for k in ("family", "target_mode", "params", "mae", "rmse", "r2", "monotonic_val_pct")},
                      "all": [{k: r[k] for k in ("family", "target_mode", "params", "mae", "rmse", "r2", "monotonic_val_pct", "fit_seconds")}
                              for r in sorted(search, key=lambda r: r["rmse"])],
                      "water_balance_cap_chosen_on_validation": wb_cap},
        "results": results,
        "headline": {"deployed_test": {k: test_rows["deployed"][k] for k in ("mae", "rmse", "r2")},
                     "persistence_test": {k: test_rows["persistence"][k] for k in ("mae", "rmse", "r2")},
                     "water_balance_test": {k: test_rows["water_balance"][k] for k in ("mae", "rmse", "r2")},
                     "rmse_reduction_vs_persistence_pct": 100 * (1 - test_rows["deployed"]["rmse"] / test_rows["persistence"]["rmse"])},
        "error_analysis_test": {"by_zone": by_zone, "by_missing_reading": by_missing, "by_month": by_month},
        "response_check_test": response,
        "importance": {"permutation_test": permutation, "note": "Permutation على الاختبار بعد الاختيار — للتفسير فقط"},
        "feature_ranges": ranges, "zone_ranges": zone_ranges,
        "software": {"scikit-learn": sklearn.__version__, "pandas": pd.__version__, "numpy": np.__version__, "seed": SEED},
        "training_seconds": round(time.time() - t_start, 1),
        "limitations": [
            "كل السجلات SIMULATED بالبذرة 42603؛ المقاييس تقيس تعلم المحاكاة، لا دقة ميدانية ولا توفير ماء.",
            "نفس المناطق الأربع في كل الأجزاء؛ التقسيم الزمني لا يثبت التعميم على مزرعة جديدة.",
            "خصائص المنطقة ثابتة لكل منطقة، فهي تعمل عمليًا كمعرّف للمنطقة.",
            "مجموعة مستقلة عن نموذج البرمودا؛ لم تُدمج البيانات ولم يُفترض تطابق المحاصيل.",
            "معادلة simple_water_balance في الملف غير موثقة؛ أرقامها معروضة كما أوردها الملف. موازنة الماء المحسوبة هنا معادلة مختلفة موثقة في crops_lib.py.",
        ],
    }
    (OUT / "crops_metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\nالنتائج (MAE / RMSE / R² — نقاط مئوية):")
    for r in results:
        if r["source"] == "computed_here":
            print(f"  {r['split']:<10} {r['model_id']:<22} {r['mae']:.4f}  {r['rmse']:.4f}  {r['r2']:+.4f}")
    print("استجابة الكمية على الاختبار:", response)
    print(f"✓ حُفظ: {OUT / 'crops_model.joblib'}  ({report['training_seconds']} ث)")


if __name__ == "__main__":
    main()
