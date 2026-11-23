"""Optional response regression benchmark. Every label is simulation, NOT field evidence."""
from pathlib import Path
import argparse, json, platform
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

FEATURES=["pre_vwc","planned_volume_l","planned_duration_min","root_depth_m","area_m2","forecast_rain_mm","forecast_et0_mm","doy_sin","doy_cos"]

def train(root):
    root=Path(root)
    x=pd.read_csv(root/"data/ml/ml_features.csv").merge(pd.read_csv(root/"data/ml/ml_targets.csv"),on="decision_id")
    x=x.merge(pd.read_csv(root/"data/ml/split_manifest.csv"),on=["decision_id","zone_id"])
    x=x[x.eligible & x.delta_vwc.notna()].copy()
    assert not x[FEATURES].isna().any().any()
    train=x[x.split.eq("train")]; val=x[x.split.eq("validation")]; test=x[x.split.eq("test")]
    cfg=json.loads((Path(__file__).resolve().parents[1]/"config.json").read_text(encoding="utf-8"))
    model=RandomForestRegressor(n_estimators=80,max_depth=8,min_samples_leaf=4,random_state=cfg["seed"],n_jobs=1)
    model.fit(train[FEATURES],train.delta_vwc)
    updated=RandomForestRegressor(n_estimators=80,max_depth=8,min_samples_leaf=4,random_state=cfg["seed"],n_jobs=1)
    development=x[x.split.isin(["train","validation"])]
    updated.fit(development[FEATURES],development.delta_vwc)
    rows=[]; predictions=[]
    for split,frame in [("validation",val),("test",test)]:
        for name,pred,fitdata in [("zero_change_baseline",np.zeros(len(frame)),"none"),
                                  ("RF_fixed_2024",model.predict(frame[FEATURES]),"2024"),
                                  *([( "RF_updated_through_Jun2025",updated.predict(frame[FEATURES]),"2024+2025JanJun")] if split=="test" else [])]:
            rows.append(dict(model_id=name,evaluation_split=split,n_cases=len(frame),mae_vwc=float(mean_absolute_error(frame.delta_vwc,pred)),
                rmse_vwc=float(np.sqrt(mean_squared_error(frame.delta_vwc,pred))),r2=float(r2_score(frame.delta_vwc,pred)),
                training_period=fitdata,label_origin="simulation_only_NO_field_accuracy_claim",deployed=False))
            predictions.extend(dict(decision_id=did,model_id=name,predicted_delta_vwc=float(y),evaluation_split=split) for did,y in zip(frame.decision_id,pred))
    q=root/"quality";q.mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(q/"demo_model_metrics.csv",index=False,encoding="utf-8",float_format="%.10f",lineterminator="\n")
    pd.DataFrame(predictions).to_csv(q/"demo_predictions.csv",index=False,encoding="utf-8",float_format="%.10f",lineterminator="\n")
    card={"task":"regression:soil moisture response after planned irrigation", "target":"delta_vwc=post_vwc-pre_vwc",
        "target_unit":"m3/m3", "timing":"prediction04:00 local;target planned_end+120min;post +/-5min window",
        "ground_truth":"simulation sensors only;no independent field labels", "features":FEATURES,
        "excluded_metadata":["decision_id","zone_id","issued_at","input_sample_id","forecast_id","features_available_at"],
        "forbidden_future":["delivered_volume_l","actual_end","post_vwc","delta_vwc","scenario_id","confirmed_cause","realized_weather"],
        "training_n":len(train),"validation_n":len(val),"test_n":len(test),"updated_fit_n":len(development),
        "hyperparameters":{"n_estimators":80,"max_depth":8,"min_samples_leaf":4,"random_state":cfg["seed"],"n_jobs":1},
        "selection":"parameters fixed in advance;validation not used as test;updated model evaluated on identical untouched test period",
        "limitations":["same simulator;autocorrelated records;2zones same site;1zone per arm","no claim of optimal irrigation or field water savings",
            "temperature/dormancy,soil,meter and plant proxy assumptions need independent measurement","no automatic promotion or live valve control"],
        "software":{"python":platform.python_version(),"numpy":np.__version__,"pandas":pd.__version__,"scikit-learn":sklearn.__version__},
        "metrics":rows}
    (q/"demo_model_card.json").write_text(json.dumps(card,ensure_ascii=False,indent=2), encoding="utf-8")
    # Include small QA outputs in the formatted workbook, never in the Feature matrix.
    pp=root/"metadata/workbook_payload.json"
    if pp.exists():
        payload=json.loads(pp.read_text(encoding="utf-8"))
        for name in ["demo_model_metrics"]:
            df=pd.read_csv(q/(name+".csv"))
            payload["tables"][name]={"columns":list(df.columns),"rows":df.astype(object).where(pd.notnull(df),None).values.tolist(),
                "meta":{"data_type":"derived_from_simulation","file":"quality/"+name+".csv"}}
        pp.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False), encoding="utf-8")
    print(pd.DataFrame(rows).to_string(index=False))
    return card

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    train(ap.parse_args().root)
