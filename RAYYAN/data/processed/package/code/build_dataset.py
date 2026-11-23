"""RAYYAN: cached primary-source weather + explicitly separate, deterministic simulation.
Run: python code/build_dataset.py --out .
No live hardware commands, no real field labels, no claim of optimal irrigation.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
import argparse, csv, hashlib, json, math, platform, shutil
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
TZ = timezone(timedelta(hours=3))
TABLES, META = {}, {}

def stamp(d):
    return d.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

def parse(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def add(name, columns, rows, grain, origin, pk, fks="", cadence="", source="SIM01", use="", folder="simulation"):
    rows = [dict(zip(columns, r)) if not isinstance(r, dict) else r for r in rows]
    if any(set(r) != set(columns) for r in rows):
        raise ValueError("Column mismatch: " + name)
    TABLES[name] = pd.DataFrame(rows, columns=columns)
    META[name] = dict(table=name, file=f"data/{folder}/{name}.csv", grain_ar=grain, data_type=origin,
                      primary_key=pk, foreign_keys=fks, cadence_ar=cadence, source_id=source, use_ar=use)
    return TABLES[name]

def build(out):
    TABLES.clear(); META.clear()
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "raw/source_manifest.json").read_text(encoding="utf-8"))
    weather_path = ROOT / "raw/weather_era5.json"
    assert hashlib.sha256(weather_path.read_bytes()).hexdigest() == manifest["weather"]["sha256"]
    obj = json.loads(weather_path.read_text(encoding="utf-8"))
    assert obj["hourly_units"]["wind_speed_10m"] == "m/s"
    assert obj["hourly_units"]["precipitation"] == "mm"
    assert obj["utc_offset_seconds"] == 10800
    start = datetime.fromisoformat(cfg["start_date"]).replace(tzinfo=TZ)
    end = (datetime.fromisoformat(cfg["end_date"]) + timedelta(days=1)).replace(tzinfo=TZ)
    days = (end-start).days
    seq = np.random.SeedSequence(cfg["seed"])
    rng_sensor, rng_forecast, rng_flow = [np.random.default_rng(s) for s in seq.spawn(3)]
    hourly = obj["hourly"]
    raw_weather = {}
    for i, t in enumerate(hourly["time"]):
        d = datetime.fromisoformat(t).replace(tzinfo=TZ)
        raw_weather[d] = {k:v[i] for k,v in hourly.items() if k != "time"}
    weather_rows, wx = [], []
    for j in range(days*24):
        a = start + timedelta(hours=j); b = a + timedelta(hours=1)
        v = raw_weather[b]  # accumulated variables refer to the PRECEDING hour
        wid = f"W{j+1:06d}"
        weather_rows.append([wid, "SITE01", stamp(a), stamp(b), v["temperature_2m"], v["relative_humidity_2m"],
            v["precipitation"], v["et0_fao_evapotranspiration"], v["shortwave_radiation"], v["wind_speed_10m"],
            obj["latitude"], obj["longitude"], manifest["weather"]["accessed_at"], "SRC02", "reanalysis"])
        wx.append(v)
    add("weather_reanalysis", ["weather_id","site_id","interval_start_at","interval_end_at","temperature_c","humidity_pct",
        "rain_mm","et0_mm","solar_w_m2","wind_m_s","grid_latitude_deg","grid_longitude_deg","available_at","source_id","product_type"],
        weather_rows, "خلية إعادة تحليل واحدة × ساعة؛ درجة الحرارة والرطوبة والرياح لحظية عند نهاية الفترة، والتراكمات للساعة السابقة",
        "reference", "weather_id", "site_id->sites.site_id", "ساعة، 731 يومًا؛ 0.25 درجة شبكية", "SRC02",
        "استكشاف الطقس وتغذية المحاكاة؛ لا تدخل تاريخيًا كأنها توقع متاح آنذاك", "reference")
    climate = [[1,6.8,21.6,50,242,9.6],[2,9,24.9,40,281,10],[3,12.8,28.7,35,302,11.3],
        [4,18,34.7,33,293,11],[5,22.9,40.7,22,276,12],[6,24.9,43.7,15,295,13.5],
        [7,27,45,14,305,14],[8,26.6,44.7,14,252,14],[9,22.7,41.8,18,202,13],
        [10,17.4,36.7,24,173,12],[11,12.5,29.9,37,199,11.3],[12,8.4,23.7,46,223,9.2]]
    crop = [[111.21,.85,94.5285,97.45206186,6.148939209],[138.42,.85,117.657,121.2958763,4.462122951],
        [202.32,.82,165.9024,171.0334021,3.503565952],[239.28,.80,191.424,197.3443299,2.938503009],
        [300.41,.80,240.328,247.7608247,2.418569622],[332.98,.80,266.384,274.6226804,2.11161331],
        [359.7,.80,287.76,296.6597938,2.019912427],[324.62,.79,256.4498,264.3812371,2.266525456],
        [252.67,.80,202.136,208.3876289,2.782779911],[197.55,.83,163.9665,169.0376289,3.544931434],
        [148.91,.85,126.5735,130.4881443,4.444058195],[117.1,.85,99.535,102.6134021,5.839654393]]
    add("study_climate", ["month","tmin_c","tmax_c","humidity_pct","wind_km_day","sunshine_h_day","source_id","locator"],
        [r+["SRC01","Table 4, printed pp.104-105; monthly climatology 1985-2010"] for r in climate],
        "متوسط مناخي منشور لشهر من السنة، وليس سجلًا يوميًا", "observed_aggregate", "month", source="SRC01", folder="reference")
    add("study_crop", ["month","eto_mm_month","kc","cwr_mm_month","iwr_mm_month","irrigation_interval_days","source_id","locator"],
        [[i+1]+r+["SRC01","Tables 5-6 and 8, printed pp.106-111"] for i,r in enumerate(crop)],
        "حساب مرجعي منشور لشهر وفق افتراضات الدراسة", "reference", "month", source="SRC01", folder="reference")
    params = [
        ["study_fc",.10,"m3/m3","estimated","Table 7, printed p.109","Rosetta/van Genuchten; study soil only"],
        ["study_wp",.05,"m3/m3","estimated","Table 7, printed p.109","study soil only"],
        ["study_root_depth",.75,"m","adopted_literature","Methodology, printed p.103","mean of 0.5-1.0 m; not measured trial roots"],
        ["study_p",.50,"fraction","adopted_literature","Methodology, printed p.103","conditional reference"],
        ["study_water_ec",.85,"dS/m","measured","Soil and water properties, printed p.102","study water sample only"],
        ["study_ece_tolerance",6.9,"dS/m","adopted_literature","Salinity method, printed p.102","not field salinity"],
        ["study_lr",.03,"fraction","calculated_rounded","Table 6, printed p.108","not automatic local leaching requirement"],
        ["study_taw",37.5,"mm","calculated","Table 7, printed p.109","soil and rooting assumptions of study"],
        ["study_raw",18.75,"mm","calculated","Table 7, printed p.109","soil and rooting assumptions of study"],
        ["study_event_depth",19.33,"mm/event","calculated_rounded","Table 8, printed pp.110-111","not a proven optimal local dose"]]
    add("study_parameters", ["parameter_id","value_numeric","unit","value_origin","locator","limitation_ar","source_id"],
        [r+["SRC01"] for r in params], "معامل واحد مع أصله وشروط نقله", "reference", "parameter_id", source="SRC01", folder="reference")
    add("sites", ["site_id","site_name","timezone","weather_request_latitude","weather_request_longitude","coordinate_status","valid_from","valid_to"],
        [["SITE01","حديقة الملك سلمان، الرياض — موقع مقترح غير ممسوح",cfg["timezone"],cfg["weather_request_latitude"],cfg["weather_request_longitude"],
          cfg["coordinate_status"],stamp(start),stamp(end)]], "تعريف موقع افتراضي واحد، بلا ادعاء ترخيص أو تركيب", "simulation", "site_id")
    add("zones", ["zone_id","site_id","area_m2","plant_species","cultivar","irrigation_method","trial_arm","valid_from","valid_to"],
        [[f"Z0{k}","SITE01",cfg["zone_area_m2"],"Cynodon dactylon",None,"simulated_sprinkler",arm,stamp(start),stamp(end)]
         for k,arm in [(1,"conventional"),(2,"rayyan")]], "منطقة ري افتراضية؛ المساحة افتراض تصميم وليست قياسًا", "simulation", "zone_id", "site_id->sites.site_id")
    profiles=[]
    for z in ["Z01","Z02"]:
        profiles.append(["P"+z,z,stamp(start),stamp(end),"loamy_sand_assumed",cfg["root_depth_m"],cfg["field_capacity_vwc"],
            cfg["wilting_point_vwc"],cfg["saturation_vwc"],cfg["depletion_fraction"],cfg["application_efficiency"],cfg["nominal_flow_l_min"],
            cfg["response_lag_min"],"SIM01;SRC03_example36"])
    add("zone_profiles", ["profile_id","zone_id","valid_from","valid_to","soil_texture","root_depth_m","field_capacity_vwc","wilting_point_vwc",
        "saturation_vwc","depletion_fraction","application_efficiency","nominal_flow_l_min","response_lag_min","parameter_basis"],
        profiles,"نسخة افتراضية من التربة والجذور والحدود لمنطقة", "simulation","profile_id","zone_id->zones.zone_id")
    devices=[]
    for z in ["Z01","Z02"]:
        for kind,prefix in [("soil_sensor","S"),("flow_meter","F"),("valve_relay","V")]:
            devices.append([prefix+z,z,kind,.125 if kind=="soil_sensor" else None,"virtual_not_installed",stamp(start),stamp(end)])
    add("devices",["device_id","zone_id","device_type","depth_m","installation_status","valid_from","valid_to"],devices,
        "جهاز افتراضي؛ حساس تربة واحد يمثل متوسط الجذور في النموذج فقط", "simulation","device_id","zone_id->zones.zone_id")
    add("calibrations",["calibration_id","device_id","slope","intercept","raw_unit","output_unit","valid_from","valid_to","validation_rmse_vwc"],
        [["C"+z,"S"+z,.0001,-.1,"ADC_count","m3/m3",stamp(start),stamp(end),0.0] for z in ["Z01","Z02"]],
        "تحويل خطي افتراضي؛ RMSE صفري لنقاط مولدة وليس دقة جهاز حقيقي", "simulation","calibration_id","device_id->devices.device_id")
    add("calibration_points",["point_id","calibration_id","raw_adc","reference_vwc","reference_method"],
        [[f"CP{z}{j}","C"+z,(v+.1)*10000,v,"simulation_oracle_not_lab"] for z in ["Z01","Z02"] for j,v in enumerate([.06,.10,.15,.20,.30])],
        "زوج معايرة مولد وليس عينة مختبر", "simulation","point_id","calibration_id->calibrations.calibration_id")

    raw, clean, faults, scenarios, forecasts, budgets, decisions, candidates = [], [], [], [], [], [], [], []
    controls, flowrows, events, outcomes, balances, sitebalances, plants, incidents = [], [], [], [], [], [], [], []
    histories={"Z01":[],"Z02":[]}; seen={}; sensor_at={}; storage={z:cfg["initial_vwc"]*1000*cfg["root_depth_m"] for z in histories}
    eventcounts={z:0 for z in histories}; counters={z:0.0 for z in histories}; previous_year=2024
    forced_missing_samples=set()
    area=cfg["zone_area_m2"]; rootmm=cfg["root_depth_m"]*1000
    fc=cfg["field_capacity_vwc"]*rootmm; wp=cfg["wilting_point_vwc"]*rootmm; sat=cfg["saturation_vwc"]*rootmm
    taw=fc-wp; drain_factor=1-math.exp(-math.log(2)/(cfg["drainage_half_life_h"]*60))
    def sensor(z,t):
        key=(z,stamp(t))
        if key in sensor_at: return sensor_at[key]
        sample=f"SM{len(clean)+1:07d}"; message=f"M{len(raw)+1:07d}"; theta=storage[z]/rootmm
        value=theta+float(rng_sensor.normal(0,cfg["sensor_noise_sd_vwc"]))
        # A mild deterministic offset represents imperfect spatial representativeness, not a corrected truth.
        value += .0007 if z=="Z01" else -.0007
        adc=round((value+.1)*10000,3); defect=None
        u=float(rng_sensor.random())
        forced=(z=="Z02" and t.date().isoformat()=="2025-03-15") or key in forced_missing_samples
        if forced or u<cfg["sensor_missing_probability"]: adc=None; defect="missing_payload"
        elif u<cfg["sensor_missing_probability"]+cfg["sensor_spike_probability"]: adc=7500.0; defect="out_of_range_spike"
        received=t+timedelta(seconds=int(rng_sensor.integers(5,91))); available=received+timedelta(seconds=1)
        raw.append([message,sample,"S"+z,stamp(t),stamp(received),adc,"ADC_count"])
        calibrated=None if adc is None else adc*.0001-.1
        flag="missing" if adc is None else ("invalid_range" if not 0<=calibrated<=cfg["saturation_vwc"] else "ok")
        usable=calibrated if flag=="ok" else None
        row=[sample,message,"S"+z,"C"+z,stamp(t),stamp(available),calibrated,usable,flag,False]
        clean.append(row); record=dict(zip(["sample_id","message_id","device_id","calibration_id","measured_at","available_at","calibrated_original_vwc","usable_vwc","quality_flag","was_imputed"],row))
        histories[z].append(record); sensor_at[key]=record
        if defect: faults.append([f"Q{len(faults)+1:06d}",message,defect,"injected_for_testing_not_real_frequency"])
        if rng_sensor.random()<cfg["duplicate_probability"]:
            mid=f"M{len(raw)+1:07d}"
            raw.append([mid,sample,"S"+z,stamp(t),stamp(received+timedelta(seconds=3)),adc,"ADC_count"])
            faults.append([f"Q{len(faults)+1:06d}",mid,"duplicate_delivery","injected_for_testing_not_real_frequency"])
        return record
    def controls_for(ev,z):
        for action,t in [("open",ev["planned_start"]),("close",ev["planned_end"])]:
            controls.append([f"CMD{len(controls)+1:06d}",ev["decision_id"],"V"+z,action,stamp(t),stamp(t+timedelta(seconds=2)),
                "accepted",None,"relay_ack_only_not_physical_position"])
        if ev["kind"]=="stuck_open":
            t=ev["actual_end"]
            controls.append([f"CMD{len(controls)+1:06d}",ev["decision_id"],"V"+z,"emergency_close",stamp(t),stamp(t+timedelta(seconds=2)),
                "accepted",None,"relay_ack_only_not_physical_position"])
    for dayindex in range(days):
        d=start+timedelta(days=dayindex); ds=d.date().isoformat()
        if d.year!=previous_year:
            counters={z:0.0 for z in histories}; previous_year=d.year
        budget=cfg["limited_daily_budget_l"] if "2025-06-01"<=ds<="2025-06-07" else cfg["normal_daily_budget_l"]
        bid="B"+ds.replace("-","")
        budgets.append([bid,"SITE01",stamp(d),stamp(d+timedelta(days=1)),budget,stamp(d),"simulation_allocation_not_measured_storage"])
        # Synthetic forecast truth is retrospective forcing + declared error. It is NOT an archived operational forecast.
        validstart=d+timedelta(hours=4); validend=validstart+timedelta(days=1)
        future=[raw_weather[validstart+timedelta(hours=h+1)] for h in range(24)]
        totalrain=sum(v["precipitation"] for v in future); totalet=sum(v["et0_fao_evapotranspiration"] for v in future)
        predictedrain=max(0,totalrain*float(rng_forecast.lognormal(0,.35))) if rng_forecast.random()>.15 else 0.0
        if totalrain==0 and rng_forecast.random()<.03: predictedrain=float(rng_forecast.uniform(.2,4))
        foret=max(0,totalet*float(rng_forecast.lognormal(0,.15)))
        fortemp=float(np.mean([v["temperature_2m"] for v in future])+rng_forecast.normal(0,1.5))
        # Decision coefficients use the forecast known at issue time; physics can use realized forcing.
        decision_kc=crop[d.month-1][1]*(.35+.65*max(0,min(1,(fortemp-8)/20)))
        fid="FC"+ds.replace("-","")
        forecasts.append([fid,"SITE01",stamp(d+timedelta(hours=3)),stamp(d+timedelta(hours=3,minutes=1)),stamp(validstart),stamp(validend),
            round(fortemp,6),round(predictedrain,6),round(foret,6),"synthetic_forecast","SIM01"])
        a0={z:storage[z] for z in histories}; totals={z:dict(rain=0.,gross=0.,loss=0.,runoff=0.,drain=0.,et=0.,stress=0) for z in histories}
        active={}; posttimes={z:set() for z in histories}
        tempmean=float(np.mean([wx[dayindex*24+h]["temperature_2m"] for h in range(24)]))
        seasonal=.35+.65*max(0,min(1,(tempmean-8)/20))  # engineering approximation, NOT validated dormancy
        kc=crop[d.month-1][1]*seasonal
        for minute in range(1440):
            t=d+timedelta(minutes=minute)
            for z in histories:
                if minute%60==0 or minute in posttimes[z]: sensor(z,t)
            if minute==240:
                issued=t; proposals={}
                for z in histories:
                    good=[r for r in histories[z][-10:] if r["quality_flag"]=="ok" and parse(r["available_at"])<=issued]
                    latest=good[-1] if good else None
                    fresh=latest is not None and (issued-parse(latest["measured_at"])).total_seconds()<=7200
                    theta=latest["usable_vwc"] if latest else None
                    if z=="Z01":
                        hot=d.month in [5,6,7,8,9]
                        requested=(60. if hot else 40.) if dayindex%(2 if hot else 3)==0 else 0.
                        reason="fixed_calendar_comparator_design"
                    elif not fresh: requested=0.; reason="inspect_stale_or_invalid_sensor"
                    elif predictedrain>=4: requested=0.; reason="defer_simulated_rain_forecast"
                    elif theta<=cfg["field_capacity_vwc"]-cfg["depletion_fraction"]*(cfg["field_capacity_vwc"]-cfg["wilting_point_vwc"])+foret*decision_kc/(rootmm*2):
                        requested=max(0,(cfg["field_capacity_vwc"]-theta)*rootmm*area/cfg["application_efficiency"])
                        reason="refill_root_zone_rule_assumed_parameters"
                    else: requested=0.; reason="defer_above_trigger"
                    proposals[z]=(min(cfg["max_event_l"],requested),reason,latest,fresh)
                requestedtotal=sum(x[0] for x in proposals.values()); allocation=min(1,budget/requestedtotal) if requestedtotal else 1.
                for z,(requested,reason,latest,fresh) in proposals.items():
                    vol=math.floor(requested*allocation/cfg["nominal_flow_l_min"])*cfg["nominal_flow_l_min"]
                    duration=int(vol/cfg["nominal_flow_l_min"])
                    ps=d+timedelta(hours=5 if z=="Z01" else 6) if vol else None
                    pe=ps+timedelta(minutes=duration) if ps else None
                    target=pe+timedelta(minutes=cfg["response_lag_min"]) if pe else None
                    did="D"+ds.replace("-","")+z
                    pre=latest["usable_vwc"] if latest else None
                    expected=vol*cfg["application_efficiency"]/(area*rootmm)-foret*decision_kc*(4/24)/rootmm if vol else None
                    action="irrigate" if vol else ("inspect" if reason.startswith("inspect") else "defer")
                    decisions.append([did,z,"P"+z,bid,fid,stamp(issued),stamp(issued),latest["sample_id"] if latest else None,
                        action,reason,stamp(ps) if ps else None,stamp(pe) if pe else None,vol,duration,stamp(target) if target else None,
                        expected,"rule_v1" if z=="Z02" else "calendar_v1"])
                    for idx,fraction in enumerate([0.,.5,1.]):
                        dose=vol*fraction
                        delta=dose*cfg["application_efficiency"]/(area*rootmm)-foret*decision_kc*(4/24)/rootmm if pre is not None else None
                        candidates.append([f"{did}_P{idx}",did,dose,delta,"preview_linear_v1_not_independent_truth"])
                    if not vol: continue
                    eventcounts[z]+=1; n=eventcounts[z]; kind="normal"
                    injections={"Z01":{60:"low_flow",180:"no_flow"},"Z02":{40:"no_flow",140:"low_flow",240:"stuck_open"}}
                    kind=injections[z].get(n,kind)
                    scenario=None
                    if kind!="normal":
                        scenario=f"SC{len(scenarios)+1:04d}"
                        scenarios.append([scenario,z,kind,stamp(ps),stamp(pe+timedelta(minutes=10)),
                            "deterministic_event_index_injection_NOT_empirical_prevalence",f"event index {n} in {z}"])
                    rate=cfg["nominal_flow_l_min"]*float(np.clip(rng_flow.normal(1,.025),.9,1.1))
                    if kind=="no_flow": rate=0.
                    if kind=="low_flow": rate*=.5
                    ae=pe+timedelta(minutes=10 if kind=="stuck_open" else 0)
                    ev=dict(event_id=f"E{did[1:]}",decision_id=did,planned_start=ps,planned_end=pe,actual_end=ae,volume=0.,
                        counter_start=counters[z],counter_end=counters[z],rate=rate,kind=kind,scenario=scenario,target=target,
                        pre=latest,expected=expected,minute_duration=int((ae-ps).total_seconds()/60))
                    active[z]=ev; controls_for(ev,z)
                    for offset in [-5,0,5]:
                        q=target+timedelta(minutes=offset)
                        posttimes[z].add(int((q-d).total_seconds()/60))
                        if z=="Z02" and n==120 and offset in [-5,0]: forced_missing_samples.add((z,stamp(q)))
                    flowrows.append([f"FM{len(flowrows)+1:07d}",ev["event_id"],"F"+z,stamp(ps),stamp(ps+timedelta(seconds=2)),
                        str(d.year)+z,counters[z],None])
                    if kind!="normal":
                        alert=ps+timedelta(minutes=5,seconds=2) if kind!="stuck_open" else pe+timedelta(minutes=1,seconds=2)
                        incidents.append([f"I{len(incidents)+1:05d}",z,ev["event_id"],scenario,stamp(alert),
                            "unexpected_flow" if kind=="stuck_open" else ("no_flow" if kind=="no_flow" else "low_flow"),
                            "simulation_oracle_confirmation",kind,stamp(ae+timedelta(minutes=30))])
            hour=dayindex*24+minute//60; w=wx[hour]
            for z in histories:
                ev=active.get(z); vol=0.
                if ev and ev["planned_start"]<=t<ev["actual_end"]:
                    vol=ev["rate"]  # L/min * exactly one minute
                    ev["volume"]+=vol; counters[z]+=vol; ev["counter_end"]=counters[z]
                    flowrows.append([f"FM{len(flowrows)+1:07d}",ev["event_id"],"F"+z,stamp(t+timedelta(minutes=1)),
                        stamp(t+timedelta(minutes=1,seconds=2)),str(d.year)+z,counters[z],ev["rate"]])
                rain=w["precipitation"]/60; gross=vol/area; loss=gross*(1-cfg["application_efficiency"])
                supply=rain+gross-loss; runoff=max(0,supply-cfg["infiltration_limit_mm_h"]/60)
                ks=max(0,min(1,(storage[z]-wp)/((1-cfg["depletion_fraction"])*taw)))
                potential=w["et0_fao_evapotranspiration"]/60*kc
                et=min(storage[z]+supply-runoff,potential*ks)
                interim=storage[z]+supply-runoff-et
                deep=max(0,interim-sat); interim-=deep
                slow=max(0,interim-fc)*drain_factor; deep+=slow; interim-=slow
                storage[z]=interim
                acc=totals[z]; acc["rain"]+=rain; acc["gross"]+=gross; acc["loss"]+=loss; acc["runoff"]+=runoff; acc["drain"]+=deep; acc["et"]+=et
                if ks<.8 and potential>0: acc["stress"]+=1
        for z in histories:
            acc=totals[z]
            residual=a0[z]+acc["rain"]+acc["gross"]-acc["loss"]-acc["runoff"]-acc["drain"]-acc["et"]-storage[z]
            balances.append([f"RB{ds.replace('-','')}{z}",z,ds,a0[z],acc["rain"],acc["gross"],acc["loss"],acc["runoff"],acc["drain"],acc["et"],
                storage[z],storage[z]/rootmm,kc,acc["stress"],residual])
            ev=active.get(z)
            if not ev: continue
            events.append([ev["event_id"],ev["decision_id"],z,"F"+z,stamp(ev["planned_start"]),stamp(ev["actual_end"]),
                stamp(ev["planned_start"]) if ev["rate"]>0 else None,stamp(ev["actual_end"]) if ev["rate"]>0 else None,
                str(d.year)+z,ev["counter_start"],ev["counter_end"],ev["volume"],"counter_difference",ev["scenario"],"simulation_meter_exact_no_noise"])
            records=[sensor_at[(z,stamp(ev["target"]+timedelta(minutes=k)))] for k in [-5,0,5]]
            post=[r["usable_vwc"] for r in records if r["quality_flag"]=="ok"]
            postmean=float(np.mean(post)) if len(post)>=2 else None
            pre=ev["pre"]["usable_vwc"]; delta=postmean-pre if postmean is not None else None
            labelavailable=max(parse(r["available_at"]) for r in records)+timedelta(seconds=60)
            ps=ev["planned_start"]
            firsthour=max(0,int((parse(ev["pre"]["measured_at"])-start).total_seconds()//3600))
            lasthour=min(len(wx),int((ev["target"]-start).total_seconds()//3600)+1)
            rainflag=any(wx[h]["precipitation"]>0 for h in range(firsthour,lasthour))
            flags="rain_window" if rainflag else "none"
            if ev["kind"]!="normal": flags+=";injected_fault"
            outcomes.append(["O"+ev["event_id"],ev["event_id"],ev["decision_id"],ev["pre"]["sample_id"],stamp(ev["target"]),
                ";".join(r["sample_id"] for r in records),pre,postmean,delta,len(post),stamp(labelavailable),
                "valid_simulation_only" if postmean is not None else "missing_insufficient_post_samples",flags,"SIM_SINGLE_SENSOR_V1"])
        used=sum(totals[z]["gross"]*area for z in histories)
        # Virtual site reservoir is distinct from the allocation budget and from root-zone water.
        unmetered=15. if ds=="2025-07-20" else 0.
        previous_storage=500. if dayindex==0 else sitebalances[-1][6]
        inlet=500.-previous_storage; closing=500.-used-unmetered
        sitebalances.append(["SB"+ds.replace("-",""),"SITE01",ds,previous_storage,inlet,used,closing,0.,unmetered,
            stamp(d+timedelta(days=1,minutes=5)),"virtual_complete_boundary_not_field_measurement"])
        if unmetered:
            sid=f"SC{len(scenarios)+1:04d}"; scenarios.append([sid,None,"unmetered_site_withdrawal",stamp(d),stamp(d+timedelta(days=1)),
                "one_designed_case_NOT_empirical_prevalence","15 L omitted from known outlet meter"])
            incidents.append([f"I{len(incidents)+1:05d}",None,None,sid,stamp(d+timedelta(days=1,minutes=5)),"unaccounted_water",
                "simulation_oracle_confirmation","unmetered_withdrawal_NOT_automatically_leak",stamp(d+timedelta(days=1,hours=1))])
        if dayindex%7==6:
            for z in histories:
                recent=[r for r in balances[-14:] if r[1]==z]
                stress=sum(r[13] for r in recent)/(len(recent)*1440)
                cover=max(0,min(100,95-30*stress-20*(1-seasonal)))
                plants.append([f"PA{ds.replace('-','')}{z}",z,stamp(d+timedelta(days=1)),round(cover,6),
                    "UNVALIDATED_SIMULATION_PROXY_NOT_PHENOTYPE",None,"none_simulated",stamp(d+timedelta(days=1,hours=1))])
        if dayindex%180==0: print("simulated day",dayindex,"of",days,flush=True)

    add("measurements_raw",["message_id","sample_id","device_id","measured_at","recorded_at","raw_adc","raw_unit"],raw,
        "رسالة نقل افتراضية؛ قد تتكرر عينة sample_id برسالة أخرى", "simulation","message_id","device_id->devices.device_id","ساعة + 3 عينات قرب وقت نتيجة كل رية")
    add("measurements_clean",["sample_id","message_id","device_id","calibration_id","measured_at","available_at","calibrated_original_vwc","usable_vwc","quality_flag","was_imputed"],clean,
        "عينة بعد التحويل الخطي وفحص المدى؛ لا تعويض ولا قص للقيمة الأصلية", "simulation","sample_id",
        "message_id->measurements_raw.message_id;device_id->devices.device_id;calibration_id->calibrations.calibration_id","ساعة + نافذة الاستجابة")
    add("injection_audit",["injection_id","message_id","defect_type","frequency_basis"],faults,"خلل بيانات مصمم للاختبار؛ خارج Features", "simulation","injection_id",
        "message_id->measurements_raw.message_id",folder="audit")
    add("weather_forecasts",["forecast_id","site_id","issued_at","available_at","valid_from","valid_to","temperature_c","rain_mm","et0_mm","product_type","source_id"],forecasts,
        "إصدار توقع اصطناعي لفترة 24 ساعة؛ ليس أرشيف توقعات فعلي", "simulation","forecast_id","site_id->sites.site_id","يومي 03:00 محلي")
    add("water_budgets",["budget_id","site_id","valid_from","valid_to","allocated_volume_l","available_at","budget_basis"],budgets,
        "تخصيص إداري افتراضي للموقع ليوم؛ ليس رصيد خزان مقاسًا", "simulation","budget_id","site_id->sites.site_id","يومي")
    add("decisions",["decision_id","zone_id","profile_id","budget_id","forecast_id","issued_at","data_cutoff_at","input_sample_id","action","reason",
        "planned_start_at","planned_end_at","planned_volume_l","planned_duration_min","prediction_target_at","predicted_delta_vwc","method_version"],decisions,
        "قرار لمنطقة قبل التنفيذ في 04:00 محليًا", "simulation","decision_id",
        "zone_id->zones.zone_id;profile_id->zone_profiles.profile_id;budget_id->water_budgets.budget_id;forecast_id->weather_forecasts.forecast_id;input_sample_id->measurements_clean.sample_id","قرار يومي لكل منطقة")
    add("plan_candidates",["candidate_id","decision_id","candidate_volume_l","predicted_delta_vwc","method_version"],candidates,
        "خيار جرعة صفر/نصف/كامل من الخطة؛ التوقع تقريب خطي معلن", "simulation","candidate_id","decision_id->decisions.decision_id")
    add("control_events",["command_id","decision_id","device_id","command_action","issued_at","acknowledged_at","ack_status","physical_valve_state","evidence_kind"],controls,
        "أمر متحكم وإقراره؛ لا يثبت وضع الصمام الفيزيائي", "simulation","command_id","decision_id->decisions.decision_id;device_id->devices.device_id")
    add("flow_measurements",["flow_sample_id","event_id","device_id","measured_at","available_at","counter_epoch_id","counter_l","flow_l_min"],flowrows,
        "قراءة عداد افتراضية؛ flow_l_min متوسط الدقيقة السابقة؛ صف البداية بلا معدل", "simulation","flow_sample_id",
        "event_id->irrigation_events.event_id;device_id->devices.device_id","دقيقة أثناء تشغيل الري مع قراءة البداية")
    add("irrigation_events",["event_id","decision_id","zone_id","device_id","execution_started_at","execution_ended_at","flow_started_at","flow_ended_at",
        "counter_epoch_id","meter_start_l","meter_end_l","delivered_volume_l","volume_method","scenario_id","event_quality"],events,
        "تنفيذ رية مخططة، بما فيه محاولة لم يصل فيها ماء؛ اللترات منفذة وليست مثلى", "simulation","event_id",
        "decision_id->decisions.decision_id;zone_id->zones.zone_id;device_id->devices.device_id;scenario_id->test_scenarios.scenario_id")
    add("event_outcomes",["outcome_id","event_id","decision_id","pre_sample_id","prediction_target_at","post_sample_ids","pre_vwc","post_vwc","delta_vwc","post_valid_count",
        "label_available_at","label_status","confounding_flags","protocol_version"],outcomes,
        "فرق رطوبة من عينة متاحة قبل القرار إلى متوسط 3 عينات حول النهاية المخططة +120 دقيقة؛ وسم محاكاة", "simulation","outcome_id",
        "event_id->irrigation_events.event_id;decision_id->decisions.decision_id;pre_sample_id->measurements_clean.sample_id")
    add("root_balance_daily",["balance_id","zone_id","date_local","start_storage_mm","rain_mm","gross_irrigation_mm","application_loss_mm","runoff_mm",
        "deep_drainage_mm","actual_et_mm","end_storage_mm","end_vwc","kc_effective","stress_minutes","mass_residual_mm"],balances,
        "موازنة يومية محسوبة من تكامل دقيقة واحدة؛ حالات المحاكي وليست قراءات تربة", "simulation","balance_id","zone_id->zones.zone_id","يومي لكل منطقة")
    add("site_balance_daily",["site_balance_id","site_id","date_local","starting_storage_l","inlet_volume_l","zone_metered_volume_l","ending_storage_l","known_other_outlet_l",
        "unaccounted_volume_l","available_at","balance_basis"],sitebalances,
        "موازنة حدود خزان افتراضي كاملة؛ المتبقي غير المحسوب ليس تشخيص تسرب", "simulation","site_balance_id","site_id->sites.site_id","يومي")
    add("plant_assessments",["assessment_id","zone_id","assessed_at","cover_pct","protocol_version","field_health_score","interventions","available_at"],plants,
        "مؤشر تغطية محاكى مشتق من الإجهاد والحرارة؛ لا فحص نبات ميداني", "simulation","assessment_id","zone_id->zones.zone_id","أسبوعي")
    add("test_scenarios",["scenario_id","zone_id","scenario_type","valid_from","valid_to","frequency_basis","injection_rule"],scenarios,
        "حالة تشغيل نادرة مصممة، لا معدل حدوث في الواقع", "simulation","scenario_id","zone_id->zones.zone_id",folder="audit")
    add("incident_reviews",["incident_id","zone_id","event_id","scenario_id","detected_at","alert_type","confirmation_status","confirmed_cause","confirmed_at"],incidents,
        "تنبيه وفحص افتراضي؛ السبب الحقيقي من محرك المحاكاة فقط", "simulation","incident_id",
        "zone_id->zones.zone_id;event_id->irrigation_events.event_id;scenario_id->test_scenarios.scenario_id")
    rule_alerts=[]
    dd=TABLES["decisions"].set_index("decision_id")
    ff=TABLES["flow_measurements"]
    for e in TABLES["irrigation_events"].itertuples(index=False):
        readings=ff[ff.event_id.eq(e.event_id)]
        five=readings[readings.flow_l_min.notna()].iloc[:5]
        avg=float(five.flow_l_min.mean())
        kind="no_flow" if avg==0 else ("low_flow" if avg<cfg["nominal_flow_l_min"]*.7 else None)
        if kind:
            known=five.available_at.max()
            rule_alerts.append([f"A{len(rule_alerts)+1:05d}",e.zone_id,e.event_id,kind,known,known,avg,"flow_first5min_rule_v1"])
        pe=dd.loc[e.decision_id].planned_end_at
        later=readings[(readings.measured_at>pe)&(readings.flow_l_min>0)]
        if len(later):
            first=later.iloc[0]
            rule_alerts.append([f"A{len(rule_alerts)+1:05d}",e.zone_id,e.event_id,"unexpected_flow",first.available_at,first.available_at,
                first.flow_l_min,"positive_flow_after_planned_close_v1"])
    for s in TABLES["site_balance_daily"].itertuples(index=False):
        if abs(s.unaccounted_volume_l)>5:
            rule_alerts.append([f"A{len(rule_alerts)+1:05d}",None,None,"unaccounted_water",s.available_at,s.available_at,s.unaccounted_volume_l,"site_residual_gt5L_v1"])
    for q in TABLES["decisions"].query("action=='inspect'").itertuples(index=False):
        rule_alerts.append([f"A{len(rule_alerts)+1:05d}",q.zone_id,None,"stale_sensor",q.issued_at,q.issued_at,None,"sensor_age_gt2h_v1"])
    add("rule_alerts",["alert_id","zone_id","event_id","alert_type","detected_at","input_available_at","alert_value","method_version"],rule_alerts,
        "تنبيه مشتق من بيانات التدفق/الموازنة/قرار فحص بقواعد مستقلة عن سبب السيناريو", "derived_from_simulation","alert_id",
        "zone_id->zones.zone_id;event_id->irrigation_events.event_id")

    # Clean transport deduplication is reconstructed independently during validation.
    # Operational cost is an explicit scenario assumption, never a quoted market tariff.
    costs=[]
    e_df=TABLES["irrigation_events"]
    for z in histories:
        for year in [2024,2025]:
            sub=e_df[(e_df.zone_id==z)&(e_df.execution_started_at.str[:4]==str(year))]
            liters=float(sub.delivered_volume_l.sum())
            costs.append([f"COST{z}{year}",z,year,liters,cfg["simulated_water_tariff_sar_m3"],liters/1000*cfg["simulated_water_tariff_sar_m3"],None,
                "fictional_scenario_rate_NOT_verified_tariff"])
    add("cost_summary",["cost_id","zone_id","year","delivered_volume_l","water_tariff_sar_m3","water_cost_sar","energy_kwh","cost_basis"],costs,
        "تكلفة ماء افتراضية لسنة ومنطقة؛ الطاقة غير متاحة ولا تستنتج من اللترات وحدها", "derived_from_simulation","cost_id","zone_id->zones.zone_id",source="SIM01")
    make_ml(start,end)
    make_documentation(cfg,manifest,obj)
    export_tables(out)
    import validate_dataset
    result=validate_dataset.validate(out, write=True)
    make_summary(out,result)
    return result

def make_ml(start,end):
    dec=TABLES["decisions"].set_index("decision_id"); ev=TABLES["irrigation_events"].set_index("event_id")
    measurements=TABLES["measurements_clean"].set_index("sample_id"); forecasts=TABLES["weather_forecasts"].set_index("forecast_id")
    features=[]; targets=[]; splits=[]; availability=[]
    for o in TABLES["event_outcomes"].to_dict("records"):
        d=dec.loc[o["decision_id"]]; event=ev.loc[o["event_id"]]
        issued=parse(d.issued_at); fc=forecasts.loc[d.forecast_id]; sample=measurements.loc[d.input_sample_id]
        doy=issued.astimezone(TZ).timetuple().tm_yday
        available=max(parse(fc.available_at),parse(sample.available_at))
        profile=TABLES["zone_profiles"].set_index("profile_id").loc[d.profile_id]
        zone=TABLES["zones"].set_index("zone_id").loc[event.zone_id]
        features.append([d.name,event.zone_id,d.issued_at,d.input_sample_id,d.forecast_id,sample.usable_vwc,
            d.planned_volume_l,d.planned_duration_min,profile.root_depth_m,zone.area_m2,fc.rain_mm,fc.et0_mm,
            math.sin(2*math.pi*doy/365.25),math.cos(2*math.pi*doy/365.25),stamp(available)])
        targets.append([d.name,o["delta_vwc"],o["prediction_target_at"],o["label_available_at"],o["label_status"],"simulation_sensor_NOT_field_ground_truth"])
        local=issued.astimezone(TZ)
        split="train" if local.year==2024 else ("validation" if local.month<=6 else "test")
        eligible=o["label_status"]=="valid_simulation_only"
        splits.append([d.name,event.name,event.zone_id,split,eligible,"time_only_two_zones_same_site_NO_new_site_generalization"])
        availability.extend([[d.name,"soil_pre",d.input_sample_id,sample.available_at,d.issued_at],
            [d.name,"forecast",d.forecast_id,fc.available_at,d.issued_at],
            [d.name,"plan",d.name,d.issued_at,d.issued_at]])
    add("ml_features",["decision_id","zone_id","issued_at","input_sample_id","forecast_id","pre_vwc","planned_volume_l","planned_duration_min","root_depth_m","area_m2",
        "forecast_rain_mm","forecast_et0_mm","doy_sin","doy_cos","features_available_at"],features,
        "مدخلات مجمدة متاحة عند القرار؛ zone_id وIDs metadata لا تدخل قائمة Features العددية", "derived_from_simulation","decision_id",
        "decision_id->decisions.decision_id;zone_id->zones.zone_id;input_sample_id->measurements_clean.sample_id;forecast_id->weather_forecasts.forecast_id",folder="ml")
    add("ml_targets",["decision_id","delta_vwc","prediction_target_at","label_available_at","label_status","ground_truth_basis"],targets,
        "وسم منفصل عن Features؛ لا يمثل جرعة مثلى أو حقيقة نباتية مستقلة", "derived_from_simulation","decision_id","decision_id->decisions.decision_id",folder="ml")
    add("split_manifest",["decision_id","event_id","zone_id","split","eligible","split_limitation"],splits,
        "كل عملية ري كاملة في مجموعة زمنية واحدة؛ 2024 تدريب، النصف الأول2025 تحقق، الثاني اختبار", "derived_from_simulation","decision_id",
        "decision_id->decisions.decision_id;event_id->irrigation_events.event_id;zone_id->zones.zone_id",folder="ml")
    add("feature_availability",["decision_id","input_role","input_record_id","input_available_at","issued_at"],availability,
        "تدقيق لكل مصدر Features للتأكد من وصوله قبل القرار", "derived_from_simulation","decision_id,input_role","decision_id->decisions.decision_id",folder="ml")

def make_documentation(cfg,manifest,obj):
    sources=[
      ["PROJECT01","تقرير ريّان المرفق","فريق المشروع","user_supplied_project_report","not_stated","2026-11-07","الرياض؛ موقع مقترح؛ بلا قياسات زمنية",
       "PDF 12 pages","read_all_pages;scope pp5,7-10","user_supplied_private","نطاق الوظائف وخطة البروتوتايب، وليس نتائج تجربة"],
      ["SRC01","Saeed 2018 Bermuda irrigation","AISRP / Journal of Natural Sciences, Life and Applied Sciences",
       "https://journals.ajsrp.com/index.php/jnslas/en/article/view/989","2018-09-30","2026-11-07","جامعة الملك سعود؛ طقس مطار الملك خالد 1985-2010 شهريًا",
       "published_tables_not_raw_sensors","DOI 10.26389/AJSRP.M150618; Tables4-8 printedpp104-111; parameters pp102-103,109",
       "publisher_current_policy_CC_BY_NC_4.0;article_landing_copyright_only;confirm_2018_commercial_reuse",
       "جداول منسوخة ومراجعة؛ لا توجد بيانات أجهزة خام مرتبطة في صفحة المقال؛ معاملات التربة لا تنقل تلقائيًا"],
      ["SRC02","ERA5 via Open-Meteo Historical API","Open-Meteo / ECMWF Copernicus C3S",manifest["weather"]["url"],
       "rolling_dataset_release_not_frozen_by_provider",manifest["weather"]["accessed_at"],"2024-01-01..2025-12-31 local intervals; grid "+str(obj["latitude"])+","+str(obj["longitude"]),
       "hourly_JSON;0.25_degree_grid;elevation_nan_no_downscaling","raw/weather_era5.json; hourly weather variables; checksum in source_manifest.json",
       "CC_BY_4.0_data;free_API_noncommercial_terms_separate","إعادة تحليل مرجعية لا رصد موقع؛ ET0 حساب FAO56 لدى المزوّد؛ لا توقعات تاريخية متاحة وقت القرار"],
      ["SRC03","FAO Irrigation and Drainage Paper56 chapter8","FAO","https://www.fao.org/4/X0490E/x0490e0e.htm","1998","2026-11-07",
       "general_method_not_site_dataset","equations_reference","Equations82,83,84-85 and root-zone balance; Example36 loamy sand FC0.15 WP0.06",
       "FAO_terms_apply_no_blanket_relicensing","أساس الموازنة والإجهاد فقط؛ المثال العام ليس توصيفًا لتربة الحديقة"],
      ["SRC04","Open-Meteo terms","Open-Meteo","https://open-meteo.com/en/terms","current_not_versioned","2026-11-07","service_terms",
       "HTML","Non-Commercial Use / Data License","CC_BY_4.0_data;commercial_service_requires_appropriate_plan","المصدر المجاني للتجربة التعليمية؛ راجعي شروط خدمة التطبيق التجاري"],
      ["SRC05","AISRP copyright policy","AISRP","https://journals.ajsrp.com/index.php/jnslas/en/copyright","current_not_versioned","2026-11-07","journal_policy",
       "HTML","Copyright and Licensing section","CC_BY_NC_4.0_current_policy","سياسة حالية عامة؛ صفحة مقال2018 لا تسمي رخصة محددة؛ لا نفترض ترخيصًا تجاريًا"],
      ["SIM01","RAYYAN transparent simulation v1","this_package_code","code/build_dataset.py","2026-11-07","2026-11-07","2 hypothetical5m2zones;2024-2025",
       "CSV;fixed_seed20261107;1minute_solver","config.json;README_AR.md;code/build_dataset.py","project_generated_scenario_values;third_party_sources_retain_terms",
       "كل الحساسات والعمليات والنتائج والتكاليف افتراضية؛ المراجع تدعم المنهج أو المعاملات فقط، لا السجلات المولدة"]]
    add("sources",["source_id","title","publisher","url","published_at","accessed_at","coverage","format_resolution","locator","license_restrictions","limitation_ar"],sources,
        "مصدر أو منهج واحد مع حدود استخدامه", "documentation","source_id",source="PROJECT01;SRC01;SRC02;SRC03;SRC04;SRC05;SIM01",folder="documentation")
    assumptions=[]
    descriptions={
      "zone_area_m2":"5 م² لكل منطقة: افتراض تصميم البروتوتايب من التقرير، بلا مسح ميداني",
      "root_depth_m":"عمق فعال سطحي افتراضي 0.25م؛ ليس عمق0.75م بالدراسة ولا قياس جذور حقيقي",
      "field_capacity_vwc":"0.15 من المثال العام FAO56 Example36؛ استخدام محاكاة فقط",
      "wilting_point_vwc":"0.06 من المثال العام FAO56 Example36؛ استخدام محاكاة فقط",
      "saturation_vwc":"مسامية افتراضية هندسية، لا مختبر",
      "initial_vwc":"حالة بداية افتراضية متساوية للمجموعتين",
      "depletion_fraction":"افتراض0.5؛ موافق لقيمة turf warm season في FAO56 Table22 عند شروطه؛ لا يثبت حد الموقع",
      "application_efficiency":"كفاءة افتراضية0.8 مشتركة؛ لا اختبار Catch Can فعلي",
      "nominal_flow_l_min":"تدفق تصميم افتراضي، والتدفق الفعلي المحاكى يختلف قليلًا",
      "max_event_l":"سقف افتراضي لجرعة الخطة؛ السيناريو stuck_open قد يتجاوزه في التنفيذ",
      "normal_daily_budget_l":"تخصيص افتراضي مستقل عن الخزان؛ لا رصيد مياه مقاس",
      "limited_daily_budget_l":"ميزانية40لتر في1-7يونيو2025 لاختبار القيد، وليست نقصًا مسجلًا",
      "infiltration_limit_mm_h":"قدرة تسرب افتراضية مشتركة، وليست قياسًا لتربة الموقع",
      "drainage_half_life_h":"تصريف فوقFC بنصف عمر ساعتين افتراضي؛ ليس حل Richards",
      "response_lag_min":"نافذة120دقيقة افتراضية؛ تحتاج اختبار استجابة محلي قبل اعتماد Target",
      "solver_step_minutes":"دقيقة للتكامل ومطابقة سجل التدفق؛ لا دليل زمن استجابة أجهزة حقيقية",
      "sensor_noise_sd_vwc":"ضجيج Gaussian افتراضي، ليس مواصفة مصنع",
      "sensor_missing_probability":"معدل حقن اختبار عشوائي؛ لا تقدير موثوقية أجهزة",
      "sensor_spike_probability":"معدل حقن تجاوز مدى؛ لا تواتر واقعي",
      "duplicate_probability":"تكرار نقل مصمم لاختبار إزالة التكرار؛ الخام محفوظ",
      "simulated_water_tariff_sar_m3":"سعر خيالي معلن2ر.س/م³ للعرض فقط؛ ليس تعرفة سعودية موثقة"
    }
    for k,desc in descriptions.items(): assumptions.append(["A"+str(len(assumptions)+1).zfill(2),k,str(cfg[k]),desc,"SRC03;SIM01" if k in ["field_capacity_vwc","wilting_point_vwc","depletion_fraction"] else "SIM01"])
    assumptions.extend([
      ["A22","kc_temperature_rule","study_kc*(0.35+0.65*clip((daily_mean_temp-8)/20,0,1))","صيغة حرارة موسمية هندسية غير معايرة لسبات البرمودا؛ لا تنبؤ نمو","SRC01;SIM01"],
      ["A23","comparison_schedule","hotMaySep:60L_every2days;other:40L_every3days","خط أساس مصمم؛ ليس سجل العميل التاريخي، ولا تجربة عشوائية مكررة","SIM01"],
      ["A24","forecast_error","ET0_lognormal_sd0.15;rain_lognormal_sd0.35;miss15%;false3%;temp_sd1.5C","توقعات مولدة من forcing مع خطأ مصطنع؛ لا أرشيف توقعات ولا مهارة مثبتة","SIM01"],
      ["A25","virtual_reservoir","500L;daily_refill;15L_unmetered_2025-07-20","اختبار حدود موازنة الموقع منفصل عن موازنة التربة والميزانية","SIM01"],
      ["A26","spatial_model","one_root_bucket_and_virtual_soil_sensor_per_zone","لا يختبر عدم تجانس التربة ولا يمثل خطة الحساسات الخمسة المذكورة بالتقرير","SIM01"]])
    add("assumptions",["assumption_id","parameter_id","assumed_value","description_ar","source_id"],assumptions,
        "افتراض واحد قابل للتعديل؛ فصل المصدر عن الأرقام المولدة", "documentation","assumption_id",folder="documentation")
    missing=[
      [1,"الموقع والصلاحيات","site_id,zone_id,area_m2,boundary_geojson,cultivar","قياس حدود ومساحة المنطقتين وتحديد الموقع وموافقة التنفيذ؛ نفس صنف البرمودا","مرة ثم عند التغيير","مشغّل الموقع ومهندس الري","كل الوظائف؛ نقطة الطقس هنا تمثيلية للرياض فقط"],
      [2,"التربة والجذور","soil_texture,field_capacity_vwc,wilting_point_vwc,root_depth_m,saturation_vwc","عينات ممثلة وأعماق موثقة؛ مختبر/اختبار تشبع وتصريف وقياس عمق جذور فعال","قبل التشغيل ثم التغيير","مختص زراعي ومختبر","تحويل الرطوبة إلى لترات؛ لا تعتمد معاملات المحاكاة"],
      [3,"الأجهزة والمعايرة","device_id,zone_id,depth_m,raw_adc,reference_vwc,calibration_id","جرد الأجهزة الفعلية؛ معايرة خاصة بالتربة مقابل مرجع مستقل؛ فحص العداد بحجم معلوم","قبل التشغيل ودوريًا وفق انجراف الجهاز","مهندس الأجهزة والمختبر","القراءات وGround Truth؛ فحص توزيع حساسات متعددة"],
      [4,"القياسات الخام الفعلية","message_id,sample_id,device_id,measured_at,recorded_at,raw_adc,raw_unit","تسجيل خام دون استبدال؛ توقيت موحد ومراقبة تأخر الاتصال؛ حجم التخزين حسب الأحداث","اقتراح1-5دقائق حول الري وأبطأ خارجها بعد اختبار الاستجابة","المتحكم ومنصة الجمع","توقيت1ساعة بالحزمة للعرض والتجريب لا تشغيل ميداني دقيق"],
      [5,"التدفق والتحكم","event_id,counter_epoch_id,counter_l,flow_l_min,issued_at,acknowledged_at,physical_valve_state","عداد لكل منطقة؛ نبضات محلية وتجميع مناسب لتنبيه5دقائق؛ feedback فعلي إن لزم إثبات وضع الصمام","أثناء الري بوتيرة تحقق زمن التنبيه؛ توثيق reset","فريق الري والأجهزة","قياس المنفذ وفصل الإقرار من التدفق والوضع الفيزيائي"],
      [6,"توقعات وقت الإصدار","forecast_id,issued_at,available_at,valid_from,valid_to,provider_model","حفظ إصدارات توقع تشغيلية مستلمة فعلًا؛ وربط محطة أو مزود بالموقع","كل إصدار مستخدم في القرار","مزود طقس ومحطة الموقع إن توفرت","إعادة التحليل لا تصلح كـFeature مستقبلية متاحة تاريخيًا"],
      [7,"نتائج الاستجابة","decision_id,pre_sample_id,prediction_target_at,post_sample_ids,delta_vwc,label_available_at","اختبار زمن البلل وتثبيت نافذةTarget قبل النتائج؛ حساسات ممثلة معايرة قبل/بعد ونفس بروتوكول المجموعتين","كل رية مستقلة وتشمل الفشل والمطر؛ تجنب ملء الوسوم المفقودة","المختص الزراعي وفريق البيانات","وسوم ميدانية مستقلة لتدريب وتقييم حقيقيين"],
      [8,"النبات والمقارنة","assessed_at,cover_pct,field_health_score,protocol_version,interventions","صور بإضاءة/موضع موحد وفحص مستقل؛ توثيق القص والتسميد والمرض والظل؛ تكرارات مستقلة عند توسيع التجربة","أسبوعي مقترح مع فحص حالات الإجهاد","مختص نبات مقيم دون معرفة الذراع إن أمكن","التوفير مع الحفاظ على الجودة؛ منطقتان واحدة/ذراع لا تثبتان التعميم السببي"],
      [9,"أسباب الأعطال","detected_at,confirmed_at,confirmed_cause,confirmation_status","فحص وتقرير صيانة مستقل؛ unknown حتى التأكيد؛ لا تجعل انخفاض التدفق تسربًا مؤكدًا","لكل تنبيه وفحص حالات بلا تنبيه","فريق الصيانة","Ground Truth للأعطال وتقدير الإنذارات الكاذبة"],
      [10,"موازنة الموقع","starting_storage_l,inlet_volume_l,ending_storage_l,known_other_outlet_l","قياس كل الحدود والمخزون متزامنًا وعدم احتساب العداد الرئيسي والفرعي مرتين","فترة مشتركة مع توثيق خطأ العدادات","مهندس الري","المتبقي Unaccounted وليس تسربًا مؤكدًا"],
      [11,"الماء والتكلفة والطاقة","allocated_volume_l,water_tariff_sar_m3,energy_kwh,cost_basis","مصدر تخصيص فعلي وتعرفة وفواتير؛ عداد طاقة أو قدرة وزمن موثق؛ لا نستنتج kWh من اللترات وحدها","حسب فترة الفاتورة والتشغيل","المشغّل والمالية","المحاكاة هنا تعرض تكلفة افتراضية والطاقة NULL"]]
    add("field_collection_plan",["priority","data_group_ar","required_columns","collection_method_ar","cadence_ar","responsible_ar","purpose_ar"],missing,
        "مجموعة بيانات ناقصة تحتاج جمعًا حقيقيًا وطريقة جمعها", "missing_field_data","priority",folder="documentation")
    functions=[
      ["حالة المنطقتين والطقس","zones;zone_profiles;measurements_clean;weather_reanalysis","محاكاة + إعادة تحليل مرجعية","جاهز لعرض وتحليل تجريبي","معايرة التربة وحساسات الموقع وطقس محلي"],
      ["توقيت الري وكميته ومدته","decisions;water_budgets;weather_forecasts","محاكاة بقواعد حسابية","جاهز لاختبار القواعد؛ لا يحتاج ML مبدئيًا","حدود رطوبة وتدفق وكفاءة فعلية؛ التوصية ليست كمية مثلى مثبتة"],
      ["مقارنة الخطط والميزانية","plan_candidates;water_budgets;decisions","محاكاة","جاهز لسيناريوهات صفر/نصف/كامل وقيد الماء","ميزانية فعلية ونموذج استجابة معاير"],
      ["تنفيذ الري والتحقق من الماء","control_events;flow_measurements;irrigation_events","محاكاة","جاهز لاختبار تسلسل الأمر والإقرار والتدفق","أجهزة وربط فعلي، أمان وتحكم محلي، قياس وضع صمام إذا مطلوب"],
      ["التنبيه والفحص","rule_alerts;incident_reviews;test_scenarios;injection_audit","قواعد مشتقة + سيناريوهات اختبار مصممة","جاهز لفحص السلوك الوظيفي؛ لا تقدير حساسية واقعية","وسوم أعطال مستقلة وحالات طبيعية وأخطاء أجهزة فعلية"],
      ["التنبؤ بتغير رطوبة التربة والتحديث","ml_features;ml_targets;split_manifest;event_outcomes","وسوم محاكاة منفصلة","جاهز لتدريب تجريبي وتدقيق Leakage؛ غير صالح لاعتماد أداء ميداني","سجلات قبل/بعد حقيقية، عدة عمليات ومواسم ومواقع مستقلة"],
      ["موازنة الموقع","site_balance_daily;irrigation_events","خزان ومقاييس افتراضية","جاهز لاختبار المعادلات؛ متبقي لا يؤكد تسربًا","مدخلات ومخارج ومخزون مقاس متزامن وحدود العدادات"],
      ["التقارير والمقارنة وجودة الثيل والتكلفة","root_balance_daily;plant_assessments;cost_summary","مشتقات محاكاة؛ صحة النبات Proxy غير متحقق","جاهز لعرض الأرقام وتسمياتها الصحيحة؛ لا يثبت توفيرًا أو جودة نبات","تقييم نبات مستقل وخط أساس فعلي وتعرفة/طاقة ومكررات مستقلة"]]
    add("function_readiness",["function_ar","tables","data_available_ar","readiness_ar","missing_ar"],functions,
        "وظيفة مثبتة بالتقرير وحالة دعمها", "documentation","function_ar",folder="documentation")

def export_tables(out):
    out.mkdir(parents=True,exist_ok=True)
    for name,df in TABLES.items():
        path=out/META[name]["file"];path.parent.mkdir(parents=True,exist_ok=True)
        df.to_csv(path,index=False,encoding="utf-8",float_format="%.10f",lineterminator="\n",na_rep="")
    (out/"metadata").mkdir(exist_ok=True)
    (out/"metadata/table_metadata.json").write_text(json.dumps(META,ensure_ascii=False,indent=2), encoding="utf-8")
    # Native field collection files have HEADERS ONLY; no simulation records in observed/.
    template_names=["sites","zones","zone_profiles","devices","calibration_points","calibrations","measurements_raw","measurements_clean",
        "weather_forecasts","water_budgets","decisions","control_events","flow_measurements","irrigation_events","event_outcomes","plant_assessments","incident_reviews","site_balance_daily"]
    p=out/"field_templates";p.mkdir(exist_ok=True)
    for name in template_names: TABLES[name].iloc[:0].to_csv(p/(name+".csv"),index=False,encoding="utf-8",lineterminator="\n")
    import schema
    schema.write_dictionary(out,TABLES,META)

def make_summary(out,result):
    catalog=[]
    for n,m in META.items():
        catalog.append({**m,"row_count":len(TABLES[n]),"column_count":len(TABLES[n].columns)})
    pd.DataFrame(catalog).to_csv(out/"metadata/table_catalog.csv",index=False,encoding="utf-8",lineterminator="\n")
    payload={"config":json.loads((ROOT/"config.json").read_text(encoding="utf-8")),"tables":{},"qc_summary":result}
    for n,df in TABLES.items():
        payload["tables"][n]={"columns":list(df.columns),"rows":df.astype(object).where(pd.notnull(df),None).values.tolist(),"meta":META[n]}
    for name in ["data_dictionary","quality_checks","table_catalog"]:
        path=(out/"metadata"/(name+".csv")) if name!="quality_checks" else out/"quality/quality_checks.csv"
        df=pd.read_csv(path,keep_default_na=False)
        payload["tables"][name]={"columns":list(df.columns),"rows":df.astype(object).where(pd.notnull(df),None).values.tolist(),
            "meta":{"data_type":"documentation","file":str(path.relative_to(out))}}
    (out/"metadata/workbook_payload.json").write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False), encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,default=ROOT)
    args=ap.parse_args();build(args.out.resolve())
