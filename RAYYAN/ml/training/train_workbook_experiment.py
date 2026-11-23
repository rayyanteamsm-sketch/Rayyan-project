"""
تجربة ثانوية: إعادة منهج الـNotebook المرفق (Untitled19.ipynb) على مصنف التدريب
Rayyan_Bermuda_Model_Training_2024_2025.xlsx — ورقة VWC_Response و Data_Dictionary.

لماذا ثانوية؟ هذا المصنف لا يرتبط بمعرّفات قاعدة SQLite (decision_id بصيغة DRAY…)، ويستخدم
معاملات مناطق مختلفة (تدفق 1 لتر/دقيقة وأحجام 9.5/39/45 لترًا). لذلك لا يُستخدم في النظام،
ويُعرض للمقارنة والشفافية فقط.

الاختلاف عن الـNotebook: XGBoost غير مثبت في البيئة، فاستُخدم RandomForest فقط مع نفس
طريقة الضبط (PredefinedSplit على التحقق) ونفس فترات التقييم (test و stress_test).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import PredefinedSplit, RandomizedSearchCV
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[2]
XLSX = ROOT / "data/processed/inputs/Rayyan_Bermuda_Model_Training_2024_2025.xlsx"
OUT = ROOT / "ml/saved_models/workbook_experiment.json"
SEED = 20261107


def metrics(y, p):
    return {"n": int(len(y)), "mae": float(mean_absolute_error(y, p)),
            "rmse": float(np.sqrt(mean_squared_error(y, p))), "r2": float(r2_score(y, p))}


def main():
    df = pd.read_excel(XLSX, sheet_name="VWC_Response")
    dic = pd.read_excel(XLSX, sheet_name="Data_Dictionary")
    feats = dic.loc[dic.sheet.eq("VWC_Response") & dic.role.eq("feature"), "column"].tolist()
    elig = df.response_eligible.astype(str).str.lower().isin(["true", "1"])
    n0 = len(df)
    df = df[elig & df.delta_vwc.notna()].copy()
    df["split"] = df.split.str.lower().str.strip()
    X = df[feats].apply(lambda c: c.astype(float) if c.dtype != bool else c.astype(int)).astype(float)
    y = df.delta_vwc.astype(float)
    part = {s: (X[df.split == s], y[df.split == s]) for s in ["train", "validation", "test", "stress_test"]}
    pipe = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
                     ("model", RandomForestRegressor(random_state=SEED, n_jobs=-1))])
    grid = {"model__n_estimators": [200, 400], "model__max_depth": [None, 6, 8, 12],
            "model__min_samples_leaf": [1, 3, 5, 10], "model__max_features": ["sqrt", 0.5, 1.0]}
    Xtv = pd.concat([part["train"][0], part["validation"][0]]); ytv = pd.concat([part["train"][1], part["validation"][1]])
    fold = np.r_[np.full(len(part["train"][0]), -1), np.zeros(len(part["validation"][0]), dtype=int)]
    s = RandomizedSearchCV(pipe, grid, n_iter=25, cv=PredefinedSplit(fold), scoring="neg_root_mean_squared_error",
                           random_state=SEED, n_jobs=-1, refit=False).fit(Xtv, ytv)
    best = s.best_params_
    pipe.set_params(**best).fit(Xtv, ytv)
    base = Pipeline([("impute", SimpleImputer(strategy="median", keep_empty_features=True)), ("model", DummyRegressor())]).fit(Xtv, ytv)
    res = []
    for split in ["test", "stress_test"]:
        Xs, ys = part[split]
        res.append({"model_id": "baseline_mean", "split": split, **metrics(ys, base.predict(Xs))})
        res.append({"model_id": "random_forest", "split": split, **metrics(ys, pipe.predict(Xs))})
    rep = {"title": "تجربة ثانوية على مصنف التدريب (منهج الـNotebook)", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "source_file": XLSX.name, "sheet": "VWC_Response", "features": feats, "n_features": len(feats),
           "rows_total": n0, "rows_used": int(len(df)), "split_sizes": {k: int(len(v[1])) for k, v in part.items()},
           "best_params": {k.replace("model__", ""): v for k, v in best.items()}, "validation_rmse": float(-s.best_score_),
           "results": res, "deviation_from_notebook": "XGBoost غير متاح في البيئة؛ RandomForest فقط.",
           "why_not_used_in_system": "معرّفات هذا المصنف لا ترتبط بقاعدة SQLite، ومعاملات المناطق فيه (تدفق 1 لتر/دقيقة، "
                                     "أحجام 9.5/39/45) تختلف عن الحزمة. النظام يستخدم نموذج Model Card المرتبط بالقاعدة.",
           "label_origin": "simulation_only"}
    OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in res:
        print(f"{r['split']:<12} {r['model_id']:<15} MAE={r['mae']:.5f} RMSE={r['rmse']:.5f} R2={r['r2']:+.3f}")


if __name__ == "__main__":
    main()
