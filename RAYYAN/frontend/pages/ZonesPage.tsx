// المناطق والمحاصيل: ست مناطق في مجموعتي بيانات مستقلتين، ولكل مجموعة نموذجها.
import { useEffect, useState } from "react";
import { api, type CropRecommendation } from "../services/api";
import { CROP_COLOR, CropGlyph, CropRecommendResult, Kpi } from "../components/crops";
import SoilColumn from "../components/SoilColumn";
import { ErrorBox, Field, fmt, fmtL, Loading, Panel, useApi, Warnings } from "../components/ui";
import type { PageProps } from "./DecisionPage";

const BERMUDA_COLOR = "#5B7186";

export default function ZonesPage({ param }: PageProps) {
  const crops = useApi(() => api.cropZones(), []);
  const berm = useApi(() => api.zones(), []);
  const [sel, setSel] = useState<string>(param ?? "Z001");
  useEffect(() => { if (param) setSel(param); }, [param]);
  const pick = (id: string) => { setSel(id); window.location.hash = `#/zones/${id}`; };
  if (crops.error || berm.error) return <ErrorBox message={(crops.error ?? berm.error)!} />;
  if (!crops.data || !berm.data) return <Loading />;
  const isCrop = sel.length === 4;
  return (
    <div className="space-y-5">
      <p className="text-sm text-muted">ست مناطق في <b>مجموعتي بيانات مستقلتين</b>: منطقتا ثيل البرمودا (نموذج البرمودا وقواعد rule_v1) والمحاصيل الأربع (نموذج المحاصيل وFAO-56).
        لكل مجموعة نموذجها الخاص؛ لم تُدمج البيانات ولم يُفترض تطابق المحاصيل. اختاري منطقة لعرض بياناتها وتشغيل التنبؤ بنموذجها.</p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {crops.data.items.map((z) => (
          <button key={z.zone_id} onClick={() => pick(z.zone_id)} aria-pressed={sel === z.zone_id}
            className={`panel lift p-3 text-start transition ${sel === z.zone_id ? "ring-2 ring-water" : ""}`} style={{ borderTop: `3px solid ${CROP_COLOR[z.zone_id]}` }}>
            <div className="flex items-center gap-2"><CropGlyph zoneId={z.zone_id} size={30} /><div><b>{z.crop}</b><div className="font-mono text-[11px] text-muted">{z.zone_id}</div></div></div>
            <div className="mt-2 text-[11px] text-muted">{z.zone_name} · {fmtL(z.area_m2, 0)} م²</div>
            <div className="mt-1 chip bg-water-pale text-water">نموذج المحاصيل</div>
          </button>))}
        {berm.data.items.map((z) => (
          <button key={String(z.zone_id)} onClick={() => pick(String(z.zone_id))} aria-pressed={sel === z.zone_id}
            className={`panel lift p-3 text-start transition ${sel === z.zone_id ? "ring-2 ring-water" : ""}`} style={{ borderTop: `3px solid ${BERMUDA_COLOR}` }}>
            <div className="flex items-center gap-2"><CropGlyph zoneId="Z004" size={30} /><div><b>ثيل البرمودا</b><div className="font-mono text-[11px] text-muted">{z.zone_id}</div></div></div>
            <div className="mt-2 text-[11px] text-muted">{z.trial_arm === "rayyan" ? "قواعد ريّان" : "جدول تقليدي"} · {z.area_m2} م²</div>
            <div className="mt-1 chip bg-[#EAEFF3] text-[#4a6274]">نموذج البرمودا</div>
          </button>))}
      </div>
      {isCrop ? <CropZoneDetail key={sel} zoneId={sel} range={crops.data.range} zone={crops.data.items.find((z) => z.zone_id === sel)!} />
        : <BermudaZoneDetail key={sel} zone={berm.data.items.find((z) => z.zone_id === sel)!} />}
    </div>
  );
}

function CropZoneDetail({ zoneId, zone, range }: { zoneId: string; zone: import("../services/api").CropZone; range: { min: string; max: string } }) {
  const [date, setDate] = useState("2026-07-01");
  const [res, setRes] = useState<CropRecommendation | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (save: boolean) => {
    setBusy(true); setErr(null);
    try { setRes(await api.cropRecommend({ zone_id: zoneId, decision_date: date, save })); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  useEffect(() => { run(false); }, [date]);
  const props: [string, string][] = [["المحصول", zone.crop], ["نظام الري", zone.irrigation_system], ["التربة", zone.soil_type], ["المساحة", `${fmtL(zone.area_m2, 0)} م²`],
    ["عدد النباتات", zone.plant_count ? String(zone.plant_count) : "— (نظام حقلي)"], ["عمق الجذور", `${zone.root_depth_m} م`], ["السعة الحقلية / الذبول", `${zone.field_capacity_pct}% / ${zone.wilting_pct}%`],
    ["التشبع المفترض", `${zone.saturation_pct_assumed}%`], ["الكفاءة", String(zone.efficiency)], ["التدفق الاسمي", `${zone.nominal_flow_L_min} ل/د`],
    ["Kc المفترض", String(zone.kc_assumed)], ["TAW", `${zone.taw_mm.toFixed(1)} مم`], ["p (FAO-56)", `${zone.p_table}`],
    ["مدى الكميات في التدريب", zone.training_volume_range_l ? `${fmtL(zone.training_volume_range_l[0], 0)} — ${fmtL(zone.training_volume_range_l[1], 0)} ل` : "—"]];
  return (
    <div className="grid gap-5 xl:grid-cols-[320px_1fr]">
      <div className="space-y-4">
        <Panel title={`بيانات ${zone.crop}`} subtitle="من ورقة Zones في الملف (SIMULATED) + معاملات FAO-56">
          <table className="tbl"><tbody>{props.map(([k, v]) => <tr key={k}><td className="text-muted">{k}</td><td className="num-mixed">{v}</td></tr>)}</tbody></table>
          <p className="mt-2 text-[11px] text-muted">{zone.p_source}</p>
        </Panel>
        <Panel title="تشغيل التنبؤ">
          <Field label="اليوم" hint={`${range.min} — ${range.max}`}><input type="date" className="field" value={date} min={range.min} max={range.max} onChange={(e) => setDate(e.target.value)} /></Field>
          <div className="mt-3 flex gap-2"><button className="btn btn-primary flex-1 justify-center" disabled={busy} onClick={() => run(true)}>{busy ? "…" : "شغّلي واحفظي في السجل"}</button>
            <a className="btn btn-ghost" href={`#/recommend/${zoneId}`}>تعديل المدخلات</a></div>
        </Panel>
      </div>
      <div className="min-w-0">{err ? <ErrorBox message={err} /> : res ? <CropRecommendResult r={res} /> : <Loading />}</div>
    </div>
  );
}

function BermudaZoneDetail({ zone }: { zone: Record<string, string | number> }) {
  const [f, setF] = useState({ date: "2025-07-15", pre: "0.10", vol: "40", rain: "0", et0: "8" });
  const [res, setRes] = useState<{ delta_vwc: number; post_vwc: number; target_vwc: number; model_version: string; warnings: string[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setErr(null);
    try { setRes(await api.predict({ zone_id: zone.zone_id, decision_date: f.date, pre_vwc: Number(f.pre), planned_volume_l: Number(f.vol), forecast_rain_mm: Number(f.rain), forecast_et0_mm: Number(f.et0) })); }
    catch (e) { setErr((e as Error).message); }
  };
  useEffect(() => { run(); }, []);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const rowsP: [string, string][] = [["النبات", String(zone.plant_species)], ["التجربة", zone.trial_arm === "rayyan" ? "قواعد ريّان rule_v1" : "جدول تقليدي ثابت"],
    ["المساحة", `${zone.area_m2} م²`], ["عمق الجذور", `${zone.root_depth_m} م`], ["السعة الحقلية / الذبول", `${zone.field_capacity_vwc} / ${zone.wilting_point_vwc} m³/m³`],
    ["نسبة الاستنزاف p", String(zone.depletion_fraction)], ["الكفاءة", String(zone.application_efficiency)], ["التدفق", `${zone.nominal_flow_l_min} ل/د`],
    ["التربة", String(zone.soil_texture)], ["أصل المعاملات", String(zone.parameter_basis)]];
  return (
    <div className="grid gap-5 xl:grid-cols-[320px_1fr]">
      <Panel title={`ثيل البرمودا — ${zone.zone_id}`} subtitle="zone_profiles في حزمة البيانات (افتراضات تصميم)">
        <table className="tbl"><tbody>{rowsP.map(([k, v]) => <tr key={k}><td className="text-muted">{k}</td><td className="num-mixed">{v}</td></tr>)}</tbody></table>
      </Panel>
      <Panel title="تنبؤ نموذج البرمودا" subtitle="تغير الرطوبة بعد ساعتين من نهاية الرية (Random Forest — /api/predict)">
        <form className="grid grid-cols-2 gap-2 md:grid-cols-5" onSubmit={(e) => { e.preventDefault(); run(); }}>
          <Field label="اليوم"><input type="date" className="field" value={f.date} onChange={set("date")} /></Field>
          <Field label="الرطوبة m³/m³"><input className="field field-num" value={f.pre} onChange={set("pre")} /></Field>
          <Field label="الكمية لتر"><input className="field field-num" value={f.vol} onChange={set("vol")} /></Field>
          <Field label="مطر مم"><input className="field field-num" value={f.rain} onChange={set("rain")} /></Field>
          <Field label="ET0 مم"><input className="field field-num" value={f.et0} onChange={set("et0")} /></Field>
          <button className="btn btn-primary col-span-2 justify-center md:col-span-5">تنبئي</button>
        </form>
        {err && <div className="mt-3"><ErrorBox message={err} /></div>}
        {res && <div className="mt-4 grid items-center gap-4 md:grid-cols-[170px_1fr]">
          <SoilColumn current={Number(f.pre)} predicted={res.post_vwc} target={res.target_vwc} wilting={Number(zone.wilting_point_vwc)} compact />
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2"><Kpi label="قبل" value={fmt(Number(f.pre))} /><Kpi label="التغير المتوقع" value={`+${fmt(res.delta_vwc, 4)}`} tone="water" /><Kpi label="بعد الري" value={fmt(res.post_vwc)} tone="water" hint={`الهدف ${res.target_vwc}`} /></div>
            <p className="text-xs text-muted">النموذج: <span className="font-mono">{res.model_version}</span>. للقرار الكامل (ري/تأجيل/فحص) والكمية: <a className="text-water" href="#/recommend">صفحة توصية الري</a>.</p>
            <Warnings items={res.warnings} />
          </div></div>}
      </Panel>
    </div>
  );
}
