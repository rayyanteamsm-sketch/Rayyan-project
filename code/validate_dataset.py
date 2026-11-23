"""Independent validation of serialized CSVs, including as-of times and physical balances."""
from pathlib import Path
import argparse, json, hashlib
import numpy as np
import pandas as pd
from schema import FIELDS

def validate(root,write=True):
    root=Path(root); meta=json.loads((root/"metadata/table_metadata.json").read_text(encoding="utf-8"))
    tables={n:pd.read_csv(root/m["file"],keep_default_na=True) for n,m in meta.items()}
    dictionary=pd.read_csv(root/"metadata/data_dictionary.csv",keep_default_na=False)
    cfg=json.loads((Path(__file__).resolve().parents[1]/"config.json").read_text(encoding="utf-8"))
    results=[]
    def check(key,table,ok,observed,expected,action="none",status=None):
        results.append(dict(check_id=f"QC{len(results)+1:04d}",check=key,table=table,status=status or ("PASS" if ok else "FAIL"),
            observed=str(observed),expected=str(expected),action_ar=action))
    def times(series): return pd.to_datetime(series,utc=True,errors="coerce")
    for name,df in tables.items():
        m=meta[name]; pk=m["primary_key"].split(",")
        check("primary_key",name,not df[pk].isna().any().any() and not df.duplicated(pk).any(),
            f"null={df[pk].isna().any(axis=1).sum()};duplicates={df.duplicated(pk).sum()}","0 missing/duplicate keys")
        d=dictionary[dictionary.table==name]
        check("dictionary_coverage",name,set(d.column)==set(df.columns) and not d.column.duplicated().any(),len(d),len(df.columns))
        invalid_types=0; missing_required=0; nullcounts={}
        for c in df.columns:
            spec=d[d.column==c].iloc[0]; values=df[c]; nonnull=values.dropna()
            nullcounts[c]=int(values.isna().sum())
            if spec.nullable=="no": missing_required+=int(values.isna().sum())
            if spec.data_type in ["Float","Integer"]:
                numeric=pd.to_numeric(nonnull,errors="coerce")
                invalid_types+=int(numeric.isna().sum())+int((~np.isfinite(numeric)).sum())
                if spec.data_type=="Integer": invalid_types+=int((numeric%1!=0).sum())
            elif spec.data_type=="Datetime": invalid_types+=int(times(nonnull).isna().sum())
            elif spec.data_type=="Date": invalid_types+=int(pd.to_datetime(nonnull,format="%Y-%m-%d",errors="coerce").isna().sum())
            elif spec.data_type=="Boolean": invalid_types+=int((~nonnull.astype(str).isin(["True","False"])).sum())
        check("logical_types",name,invalid_types==0,invalid_types,"0 invalid values")
        check("required_values",name,missing_required==0,missing_required,"0 missing required values")
        check("missing_profile",name,True,json.dumps({k:v for k,v in nullcounts.items() if v},ensure_ascii=False),"reported;nullable does not mean imputed")
        for rel in m["foreign_keys"].split(";"):
            if not rel: continue
            child,parent=rel.split("->"); pn,pc=parent.split(".")
            wrong=set(df[child].dropna())-set(tables[pn][pc].dropna())
            check("foreign_key:"+rel,name,len(wrong)==0,len(wrong),"0 orphan values")
        for c in ["valid_from","interval_start_at","execution_started_at"]:
            pair={"valid_from":"valid_to","interval_start_at":"interval_end_at","execution_started_at":"execution_ended_at"}[c]
            if c in df and pair in df:
                delta=(times(df[pair])-times(df[c])).dt.total_seconds()
                check("time_interval:"+c,name,bool((delta>0).all()),int((delta<=0).sum()),"end > start")
        if "measured_at" in df:
            a="available_at" if "available_at" in df else "recorded_at"
            check("receive_after_measure",name,bool((times(df[a])>=times(df.measured_at)).all()),
                int((times(df[a])<times(df.measured_at)).sum()),"0 negative latencies")
        if "valid_from" in df and name in ["sites","zones","zone_profiles","devices","calibrations"]:
            check("fixed_simulation_period",name,df.valid_from.nunique()==1 and df.valid_to.nunique()==1,df.valid_from.nunique(),"one declared simulation version")
    w=tables["weather_reanalysis"]; expected_days=(pd.Timestamp(cfg["end_date"])-pd.Timestamp(cfg["start_date"])).days+1
    check("two_year_hourly_coverage","weather_reanalysis",len(w)==expected_days*24 and w.interval_end_at.nunique()==len(w),len(w),expected_days*24)
    intervals=times(w.interval_end_at)-times(w.interval_start_at)
    check("one_hour_intervals","weather_reanalysis",bool((intervals.dt.total_seconds()==3600).all()),int(intervals.dt.total_seconds().min()),3600)
    bounds=((w.humidity_pct>=0)&(w.humidity_pct<=100)&w.rain_mm.ge(0)&w.et0_mm.ge(0)&w.wind_m_s.ge(0)&w.solar_w_m2.ge(0))
    check("weather_ranges","weather_reanalysis",bool(bounds.all()),int((~bounds).sum()),"0 impossible humidity/negative accumulation")
    months=times(w.interval_start_at).dt.tz_convert("Asia/Riyadh").dt.strftime("%Y-%m")
    check("season_coverage","weather_reanalysis",months.nunique()==24,months.nunique(),24)
    check("reanalysis_not_live_features","weather_reanalysis",bool((times(w.available_at)>times(w.interval_end_at)).all()),w.product_type.unique().tolist(),"reference downloaded2026;not known2024-25")
    start=pd.Timestamp(cfg["start_date"],tz="Asia/Riyadh").tz_convert("UTC")
    end=(pd.Timestamp(cfg["end_date"],tz="Asia/Riyadh")+pd.Timedelta(days=1)).tz_convert("UTC")
    check("exact_local_period_bounds","weather_reanalysis",times(w.interval_start_at).min()==start and times(w.interval_end_at).max()==end,
        f"{times(w.interval_start_at).min()}..{times(w.interval_end_at).max()}",f"{start}..{end}")
    crop=tables["study_crop"]
    check("published_crop_equation","study_crop",np.allclose(crop.eto_mm_month*crop.kc,crop.cwr_mm_month,atol=1e-6,rtol=0),
        float(max(abs(crop.eto_mm_month*crop.kc-crop.cwr_mm_month))),"CWR=Kc*ETo;source rounding retained")
    check("published_leaching_equation","study_crop",np.allclose(crop.iwr_mm_month,crop.cwr_mm_month/.97,atol=1e-6,rtol=0),
        float(max(abs(crop.iwr_mm_month-crop.cwr_mm_month/.97))),"IWR=CWR/(1-0.03);not application efficiency")
    monthdays=np.array([31,28,31,30,31,30,31,31,30,31,30,31])
    check("published_interval_equation","study_crop",np.allclose(crop.irrigation_interval_days,18.75*monthdays/crop.cwr_mm_month,atol=1e-7,rtol=0),
        float(max(abs(crop.irrigation_interval_days-18.75*monthdays/crop.cwr_mm_month))),"RAW/(CWR/monthdays);climatologicalFebruary28days")
    p=tables["zone_profiles"]
    check("soil_parameter_order","zone_profiles",bool(((p.wilting_point_vwc>0)&(p.wilting_point_vwc<p.field_capacity_vwc)&
        (p.field_capacity_vwc<p.saturation_vwc)&(p.saturation_vwc<1)&(p.root_depth_m>0)&p.application_efficiency.between(0,1,inclusive="right")).all()),"WP<FC<sat;root>0;0<eff<=1","physical order")
    raw=tables["measurements_raw"]; clean=tables["measurements_clean"]; inj=tables["injection_audit"]
    duplicate_count=int(raw.duplicated("sample_id").sum()); missing=int(raw.raw_adc.isna().sum()); invalid=int(clean.quality_flag.eq("invalid_range").sum())
    for kind,value in [("duplicate_delivery",duplicate_count),("missing_payload",missing),("out_of_range_spike",invalid)]:
        injected=int(inj.defect_type.eq(kind).sum())
        # Duplicates of a missing payload can add raw missing entries; clean missing count is the correct sample count.
        detected=int(clean.quality_flag.eq("missing").sum()) if kind=="missing_payload" else value
        check("raw_defect_detected:"+kind,"measurements_raw",detected==injected,f"detected={detected};injected={injected}","equal",status="EXPECTED_ISSUE" if detected==injected else None,
            action="الخام محفوظ؛ إزالة تكرار النقل فقط، وNULL للقيمة غير الصالحة بلا تعويض")
    chosen=raw.sort_values(["recorded_at","message_id"]).drop_duplicates("sample_id").set_index("sample_id")
    check("first_arrival_deduplication","measurements_clean",bool((clean.set_index("sample_id").message_id==chosen.loc[clean.sample_id].message_id).all()),len(raw)-len(clean),duplicate_count)
    joined=clean.merge(raw,on="message_id",suffixes=("_clean","_raw")).merge(tables["calibrations"][["calibration_id","slope","intercept"]],on="calibration_id")
    calibrated=joined.raw_adc*joined.slope+joined.intercept
    error=np.nanmax(np.abs(calibrated-joined.calibrated_original_vwc))
    check("raw_value_preserved_and_calibrated","measurements_clean",error<1e-8,error,"max abs error<1e-8")
    check("no_imputation","measurements_clean",not clean.was_imputed.any(),int(clean.was_imputed.sum()),0)
    check("quality_mask","measurements_clean",bool((clean.usable_vwc.notna()==clean.quality_flag.eq("ok")).all()),int(clean.usable_vwc.isna().sum()),"NULL exactly when quality!=ok")
    check("usable_physical_bounds","measurements_clean",clean.usable_vwc.dropna().between(0,cfg["saturation_vwc"]).all(),[clean.usable_vwc.min(),clean.usable_vwc.max()],"0..saturation;no clipping of original")
    ev=tables["irrigation_events"]; flow=tables["flow_measurements"]
    maxdiff=float(np.max(np.abs(ev.meter_end_l-ev.meter_start_l-ev.delivered_volume_l)))
    check("volume_counter_difference","irrigation_events",maxdiff<1e-7,maxdiff,"<1e-7 L")
    integral=flow.groupby("event_id").flow_l_min.sum().reindex(ev.event_id).to_numpy()
    check("minute_flow_integral","flow_measurements",np.allclose(integral,ev.delivered_volume_l,rtol=0,atol=1e-7),float(np.max(np.abs(integral-ev.delivered_volume_l))),"<1e-7 L;each rate duration1minute")
    monotonic=flow.sort_values(["device_id","counter_epoch_id","measured_at"]).groupby(["device_id","counter_epoch_id"]).counter_l.diff().dropna().ge(-1e-8).all()
    check("counter_epoch_reset_handling","flow_measurements",monotonic and flow.counter_epoch_id.nunique()==4,flow.counter_epoch_id.nunique(),"4 epochs;nondecreasing within each")
    check("no_flow_is_valid_zero","irrigation_events",bool((ev.flow_started_at.isna()==ev.delivered_volume_l.eq(0)).all()),int(ev.delivered_volume_l.eq(0).sum()),"zero water remains a valid failed attempt")
    d=tables["decisions"]; dj=d.merge(tables["zone_profiles"],on="profile_id",suffixes=("","_profile"))
    wanted=times(dj.planned_end_at)+pd.to_timedelta(dj.response_lag_min,unit="min")
    check("fixed_target_time","decisions",bool((times(dj.prediction_target_at).dropna()==wanted.dropna()).all()),int(d.action.eq("irrigate").sum()),"planned_end+response_lag;never actual_end")
    check("planned_duration","decisions",np.allclose(dj.planned_volume_l,dj.planned_duration_min*dj.nominal_flow_l_min),"volume/duration","equal nominal rate")
    # Recompute the anticipatory trigger using the forecast temperature, never realized future temperature.
    fd=d.merge(tables["weather_forecasts"],on="forecast_id",suffixes=("","_forecast")).merge(clean[["sample_id","usable_vwc"]],left_on="input_sample_id",right_on="sample_id",how="left")
    month=times(fd.issued_at).dt.tz_convert("Asia/Riyadh").dt.month
    kc=month.map(crop.set_index("month").kc)*(.35+.65*((fd.temperature_c-8)/20).clip(0,1))
    threshold=cfg["field_capacity_vwc"]-cfg["depletion_fraction"]*(cfg["field_capacity_vwc"]-cfg["wilting_point_vwc"])+fd.et0_mm*kc/(cfg["root_depth_m"]*1000*2)
    subset=fd[(fd.zone_id=="Z02") & (fd.reason=="refill_root_zone_rule_assumed_parameters")]
    check("decision_uses_asissued_forecast_coefficient","decisions",bool((subset.usable_vwc<=threshold.loc[subset.index]+1e-9).all()),len(subset),"trigger uses simulated forecast temperature,not realized daily mean")
    plan_budget=d.groupby("budget_id").planned_volume_l.sum()
    allot=tables["water_budgets"].set_index("budget_id").allocated_volume_l
    check("plan_budget_constraint","decisions",bool((plan_budget<=allot.loc[plan_budget.index]+1e-8).all()),float((plan_budget-allot.loc[plan_budget.index]).max()),"<=0 L budget overrun in plan")
    rows=d[d.action.eq("irrigate")].merge(ev,on="decision_id")
    over=rows.delivered_volume_l-rows.planned_volume_l
    check("actual_deviation_retained","irrigation_events",True,f"max delivered-minus-plan={over.max():.6f}L","not clipped to plan;faults/flow variability retained")
    # Independent recomputation of all outcome windows and label arithmetic.
    o=tables["event_outcomes"]; cm=clean.set_index("sample_id"); errors=[]; invalid_labels=0; posttime_errors=0
    for row in o.itertuples(index=False):
        ps=cm.loc[row.post_sample_ids.split(";")]
        values=ps.usable_vwc.dropna(); expected=values.mean() if len(values)>=2 else np.nan
        if len(values)>=2: errors.append(abs(row.post_vwc-expected));errors.append(abs(row.delta_vwc-(expected-row.pre_vwc)))
        else: invalid_labels+=int(pd.notna(row.delta_vwc))
        target=pd.Timestamp(row.prediction_target_at)
        offsets=(times(ps.measured_at)-target).dt.total_seconds().tolist()
        posttime_errors+=int(sorted(offsets)!=[-300.,0.,300.])
    check("target_window_samples","event_outcomes",posttime_errors==0,posttime_errors,"all at fixed target-5/0/+5min")
    check("outcome_formula_and_missing_policy","event_outcomes",max(errors or [0])<1e-8 and invalid_labels==0,max(errors or [0]),"mean>=2post;delta=post-pre;no missing label imputation")
    eventzone=ev.set_index("event_id").zone_id
    devzone=tables["devices"].set_index("device_id").zone_id
    wrong_zones=0
    for row in o.itertuples(index=False):
        ids=[row.pre_sample_id]+row.post_sample_ids.split(";")
        wrong_zones+=sum(devzone.loc[cm.loc[k].device_id]!=eventzone.loc[row.event_id] for k in ids)
    check("same_zone_target_sensors","event_outcomes",wrong_zones==0,wrong_zones,"pre and post sensors belong to event zone")
    rb=tables["root_balance_daily"]
    residual=rb.start_storage_mm+rb.rain_mm+rb.gross_irrigation_mm-rb.application_loss_mm-rb.runoff_mm-rb.deep_drainage_mm-rb.actual_et_mm-rb.end_storage_mm
    check("root_mass_balance","root_balance_daily",residual.abs().max()<1e-7,float(residual.abs().max()),"<1e-7 mm each zone-day")
    continuity=rb.sort_values(["zone_id","date_local"]).groupby("zone_id").apply(lambda x:np.max(np.abs(x.start_storage_mm.iloc[1:].to_numpy()-x.end_storage_mm.iloc[:-1].to_numpy())),include_groups=False)
    check("storage_continuity","root_balance_daily",continuity.max()<1e-7,float(continuity.max()),"previous end=next start")
    check("root_physical_bounds","root_balance_daily",rb.end_vwc.between(0,cfg["saturation_vwc"]).all(),[rb.end_vwc.min(),rb.end_vwc.max()],"0..saturation;rare wet/dry states retained")
    sb=tables["site_balance_daily"]
    resid=sb.starting_storage_l+sb.inlet_volume_l-sb.ending_storage_l-sb.zone_metered_volume_l-sb.known_other_outlet_l
    check("site_mass_balance","site_balance_daily",np.allclose(resid,sb.unaccounted_volume_l,atol=1e-7,rtol=0),float(np.max(abs(resid-sb.unaccounted_volume_l))),"formula exact;residual not diagnosis")
    eventday=times(ev.execution_started_at).dt.tz_convert("Asia/Riyadh").dt.strftime("%Y-%m-%d")
    volumes=ev.groupby(eventday).delivered_volume_l.sum().reindex(sb.date_local).fillna(0).to_numpy()
    check("site_to_zone_volume","site_balance_daily",np.allclose(volumes,sb.zone_metered_volume_l,atol=1e-7,rtol=0),float(np.max(abs(volumes-sb.zone_metered_volume_l))),"equals event totals;no double counting")
    for name in ["weather_forecasts","water_budgets"]:
        x=tables[name]
        check("data_available_before_validity",name,bool((times(x.available_at)<=times(x.valid_from)).all()),int((times(x.available_at)>times(x.valid_from)).sum()),0)
    f=tables["ml_features"]; target=tables["ml_targets"]; split=tables["split_manifest"]; a=tables["feature_availability"]
    check("as_of_feature_availability","feature_availability",bool((times(a.input_available_at)<=times(a.issued_at)).all()),int((times(a.input_available_at)>times(a.issued_at)).sum()),0)
    check("feature_snapshot_before_decision","ml_features",bool((times(f.features_available_at)<=times(f.issued_at)).all()),int((times(f.features_available_at)>times(f.issued_at)).sum()),0)
    forbidden={"delta_vwc","post_vwc","delivered_volume_l","execution_ended_at","flow_started_at","scenario_id","confirmed_cause","label_available_at","end_vwc"}
    check("forbidden_future_columns","ml_features",not bool(forbidden&set(f.columns)),sorted(forbidden&set(f.columns)),"empty;IDs excluded from numeric model Features")
    joined=f.merge(target,on="decision_id").merge(split,on=["decision_id","zone_id"])
    t=times(joined.issued_at).dt.tz_convert("Asia/Riyadh")
    wanted=np.where(t.dt.year==2024,"train",np.where(t.dt.month<=6,"validation","test"))
    check("time_split_membership","split_manifest",bool((joined.split==wanted).all()),joined.split.value_counts().to_dict(),"2024/train;2025JanJun/validation;2025JulDec/test")
    check("one_event_one_split","split_manifest",split.groupby("event_id").split.nunique().max()==1,split.groupby("event_id").split.nunique().max(),1)
    trainboundary=pd.Timestamp("2025-01-01T00:00:00+03:00");testboundary=pd.Timestamp("2025-07-01T00:00:00+03:00")
    maxtrain=times(joined.loc[joined.split.eq("train"),"label_available_at"]).max()
    maxval=times(joined.loc[joined.split.eq("validation"),"label_available_at"]).max()
    check("purge_target_overlap","split_manifest",maxtrain<trainboundary and maxval<testboundary,f"train_last_label={maxtrain};validation_last_label={maxval}","labels available before next split starts")
    check("label_after_prediction","ml_targets",bool((times(joined.label_available_at)>times(joined.issued_at)).all()),int(joined.eligible.sum()),"all target availability after decision")
    check("missing_target_excluded","split_manifest",bool((joined.eligible==joined.delta_vwc.notna()).all()) and joined.delta_vwc.isna().sum()>=1,
        int(joined.delta_vwc.isna().sum()),"at least1deliberately incomplete post-window;eligibleFalse;never filled")
    alerts=tables["rule_alerts"]; ir=tables["incident_reviews"]
    check("alert_data_available_first","rule_alerts",bool((times(alerts.input_available_at)<=times(alerts.detected_at)).all()),len(alerts),"0 alerts before input arrived")
    covered=ir.merge(alerts,on=["event_id","alert_type"],how="left",suffixes=("_oracle","_rule"))
    check("injected_operational_cases_detected_by_rules","rule_alerts",covered.alert_id.notna().all(),int(covered.alert_id.notna().sum()),len(ir))
    check("cause_confirmation_after_alert","incident_reviews",bool((times(ir.confirmed_at)>=times(ir.detected_at)).all()),len(ir),"field/oracle confirmation later than detection")
    cs=tables["cost_summary"]
    check("cost_arithmetic","cost_summary",np.allclose(cs.water_cost_sar,cs.delivered_volume_l/1000*cs.water_tariff_sar_m3,atol=1e-8),float(np.max(abs(cs.water_cost_sar-cs.delivered_volume_l/1000*cs.water_tariff_sar_m3))),"assumed scenario only")
    check("energy_not_invented","cost_summary",cs.energy_kwh.isna().all(),int(cs.energy_kwh.isna().sum()),"all NULL: no meter/pump energy measurements")
    check("field_labels_absent","ml_targets",True,"no real field ground truth","requires field collection",status="OPEN_GAP",action="جمعTargetحقيقي ومعايرة ونبات مستقل قبل أي اعتماد ميداني")
    check("independent_site_test_absent","split_manifest",True,"same2zones;1site;1zone_per_arm","additional independent sites and replicated plots",status="OPEN_GAP",action="لا تدعم الحزمة تعميمًا مكانيًا أو إثبات توفير سببي")
    check("valve_position_feedback_absent","control_events",True,"physical_valve_state=NULL","field feedback if physical state must be proven",status="OPEN_GAP",action="الإقرار يؤكد الاستلام فقط؛ التدفق دليل ماء مستقل")
    result={"checks":len(results),"status_counts":pd.Series([r["status"] for r in results]).value_counts().to_dict(),
        "rows":{k:len(v) for k,v in tables.items()},"raw_defects":{"duplicate_messages":duplicate_count,"missing_raw_payloads":missing,"invalid_clean_samples":invalid},
        "field_ground_truth_available":False,"production_model_ready":False}
    if write:
        p=root/"quality";p.mkdir(exist_ok=True)
        pd.DataFrame(results).to_csv(p/"quality_checks.csv",index=False,encoding="utf-8",lineterminator="\n")
        (p/"quality_summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2), encoding="utf-8")
    if result["status_counts"].get("FAIL",0):
        print(pd.DataFrame(results).query("status=='FAIL'").to_string(index=False))
        raise AssertionError("QC invariants failed; see quality/quality_checks.csv")
    return result

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    print(json.dumps(validate(ap.parse_args().root),ensure_ascii=False,indent=2))
