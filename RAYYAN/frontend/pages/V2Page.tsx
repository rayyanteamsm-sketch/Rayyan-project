import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type V2Defaults, type V2Prediction } from "../services/api";
import SoilColumn from "../components/SoilColumn";
import { GroupedBars, HBars, LineChart, PALETTE, Scatter } from "../components/charts";
import { ErrorBox, Field, fmt, fmtL, Loading, OriginTag, Panel, Stat, Tabs, useApi, Warnings } from "../components/ui";
import type { PageProps } from "./DecisionPage";

const ZONE_COLOR: Record<string, string> = { Z001: PALETTE.soil, Z002: PALETTE.leaf, Z003: PALETTE.water, Z004: PALETTE.ochre };
const FAULT_AR: Record<string, string> = { normal: "طبيعية", no_irrigation: "بلا ري", low_flow: "تدفق منخفض", delivery_loss: "فقد في التوصيل" };
const SHORT: Record<string, string> = { train_median: "الوسيط", persistence: "بقاء الرطوبة", rf_frozen: "RF (تدريب فقط)", rf_deployed: "RF المستخدم",
  reported_train_median: "الوسيط (الملف)", reported_persistence: "بقاء الرطوبة (الملف)", reported_simple_water_balance: "موازنة الماء (الملف)", reported_random_forest: "RF (الملف)" };

function WhatIf({ zones }: { zones: { zone_id: string; zone_name: string; crop: string }[] }) {
  const [zone, setZone] = useState("Z004");
  const [date, setDate] = useState("2026-07-01");
  const [base, setBase] = useState<V2Defaults | null>(null);
  const [form, setForm] = useState({ before: "", volume: "", rain: "", et0: "", missing: false });
  const [res, setRes] = useState<V2Prediction | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const seq = useRef(0);
  useEffect(() => {
    const id = ++seq.current; setErr(null);
    api.v2Defaults(zone, date).then((d) => {
      if (id !== seq.current) return;
      setBase(d);
      setForm({ before: d.inputs.before_VWC_pct == null ? "" : String(d.inputs.before_VWC_pct), volume: String(d.inputs.planned_volume_L),
        rain: String(d.inputs.rain_forecast_24h_mm), et0: String(d.inputs.et0_forecast_24h_mm), missing: d.inputs.before_VWC_pct == null });
      return api.v2Predict({ zone_id: zone, decision_date: date }).then((r) => { if (id === seq.current) setRes(r); });
    }).catch((e: Error) => { if (id === seq.current) { setErr(e.message); setBase(null); setRes(null); } });
  }, [zone, date]);
  const n = (s: string) => (s.trim() === "" ? undefined : Number(s));
  const submit = (e: FormEvent) => {
    e.preventDefault(); const id = ++seq.current; setErr(null);
    api.v2Predict({ zone_id: zone, decision_date: date, before_missing_reading: form.missing, before_VWC_pct: form.missing ? undefined : n(form.before),
      planned_volume_L: n(form.volume), rain_forecast_24h_mm: n(form.rain), et0_forecast_24h_mm: n(form.et0) })
      .then((r) => { if (id === seq.current) setRes(r); }).catch((x: Error) => { if (id === seq.current) setErr(x.message); });
  };
  const z = zones.find((x) => x.zone_id === zone);
  return (
    <Panel title="جرّبي النموذج الثاني" subtitle="ابدئي من سجل يوم ومنطقة كما في الملف، ثم غيّري الرطوبة أو الكمية أو الطقس — الحساب في الخادم" actions={<OriginTag kind="model" />}>
      <div className="grid gap-5 lg:grid-cols-[20rem_1fr_170px]">
        <form className="space-y-3" onSubmit={submit}>
          <Field label="المنطقة">
            <select className="field" value={zone} onChange={(e) => setZone(e.target.value)}>
              {zones.map((x) => <option key={x.zone_id} value={x.zone_id}>{x.zone_id} — {x.zone_name} ({x.crop})</option>)}
            </select>
          </Field>
          <Field label="يوم القرار" hint="2024-10-05 — 2026-10-04"><input type="date" className="field field-num" min="2024-10-05" max="2026-10-04" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="الرطوبة الحالية" hint="%"><input className="field field-num" inputMode="decimal" disabled={form.missing} value={form.before} onChange={(e) => setForm({ ...form, before: e.target.value })} /></Field>
            <Field label="الكمية المخططة" hint="لتر"><input className="field field-num" inputMode="decimal" value={form.volume} onChange={(e) => setForm({ ...form, volume: e.target.value })} /></Field>
            <Field label="مطر متوقع" hint="مم"><input className="field field-num" inputMode="decimal" value={form.rain} onChange={(e) => setForm({ ...form, rain: e.target.value })} /></Field>
            <Field label="ET0 متوقع" hint="مم"><input className="field field-num" inputMode="decimal" value={form.et0} onChange={(e) => setForm({ ...form, et0: e.target.value })} /></Field>
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.missing} onChange={(e) => setForm({ ...form, missing: e.target.checked })} />محاكاة فقد قراءة الحساس</label>
          <button className="btn btn-primary w-full justify-center">احسبي الرطوبة بعد 6 ساعات</button>
          {base && <p className="text-xs text-muted">سجل الملف: <span className="font-mono">{base.event_id}</span> · جزء {base.temporal_split} · سيناريو المولد: {FAULT_AR[base.simulated_fault_label] ?? base.simulated_fault_label} · المنفذ <span className="num">{fmtL(base.recorded_actual_volume_l, 0)}</span> ل</p>}
        </form>
        <div className="min-w-0 space-y-3">
          {err && <ErrorBox message={err} />}
          {res && (
            <>
              <div className="grid grid-cols-3 gap-3">
                <Stat label="الرطوبة الحالية" value={fmt(res.before_vwc_pct, 2)} unit="%" tone="water" />
                <Stat label="المتوقعة بعد 6 ساعات" value={fmt(res.predicted_vwc_pct, 2)} unit="%" tone="water" hint={`النموذج ${res.model_version.slice(0, 18)}…`} />
                <Stat label="المسجلة في الملف" value={res.recorded_actual_vwc_pct == null ? "—" : fmt(res.recorded_actual_vwc_pct, 2)} unit={res.recorded_actual_vwc_pct == null ? undefined : "%"}
                  hint={res.recorded_note ?? "للسجل الأصلي دون تغيير"} tone="leaf" />
              </div>
              {Object.keys(res.changed_inputs).length > 0 && (
                <p className="text-sm">المدخلات المغيّرة: {Object.entries(res.changed_inputs).map(([k, v]) => <span key={k} className="me-3 font-mono text-xs">{k}: <span className="num">{String(v.from)} ← {String(v.to)}</span></span>)}</p>
              )}
              <Warnings items={res.warnings} />
              <p className="text-xs text-muted">{z?.zone_name}: السعة الحقلية <span className="num">{res.field_capacity_pct}</span>٪ ونقطة الذبول <span className="num">{res.wilting_pct}</span>٪ (افتراضات محاكاة). حُفظ التشغيل برقم <span className="num">{res.run_id}</span>.</p>
            </>
          )}
        </div>
        {res && <SoilColumn current={res.before_vwc_pct == null ? null : res.before_vwc_pct / 100} predicted={res.predicted_vwc_pct / 100}
          target={res.field_capacity_pct / 100} wilting={res.wilting_pct / 100} max={0.45} label="مقطع التربة (نسبة حجمية)" />}
      </div>
    </Panel>
  );
}

export default function V2Page(_: PageProps) {
  const ov = useApi(() => api.v2Overview(), []);
  const m = useApi(() => api.v2Metrics(), []);
  const [split, setSplit] = useState<"test" | "validation">("test");
  const preds = useApi(() => api.v2Predictions(split), [split]);
  if (ov.error) return <ErrorBox message={ov.error} onRetry={ov.reload} />;
  if (m.error) return <ErrorBox message={m.error} onRetry={m.reload} />;
  if (!ov.data || !m.data) return <Loading />;
  const o = ov.data, d = m.data;
  const test = d.results.filter((r) => r.split === "test");
  const dep = test.find((r) => r.model_id === "rf_deployed")!;
  const wb = test.find((r) => r.model_id === "reported_simple_water_balance");
  const months = [...new Set(o.monthly.map((r) => r.month))];
  return (
    <div className="space-y-5">
      <p className="rounded-lg border border-water/30 bg-water-pale p-3 text-sm text-[#164d6b]">
        <b>مجموعة بيانات مستقلة (RAYYAN ML dataset v2):</b> أربع مناطق بمحاصيل مختلفة، أكتوبر 2024 — أكتوبر 2026، كل سجلاتها محاكاة ({o.provenance}).
        {" "}{o.independence_note}
      </p>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {o.zones.map((z) => {
          const f = o.faults.filter((x) => x.zone_id === z.zone_id);
          return (
            <section key={z.zone_id} className="panel p-4" style={{ borderTop: `4px solid ${ZONE_COLOR[z.zone_id]}` }}>
              <div className="flex items-baseline justify-between"><h2 className="text-lg font-medium">{z.zone_name}</h2><span className="font-mono text-xs text-muted">{z.zone_id}</span></div>
              <p className="text-sm">{z.crop} · {z.irrigation_system} · تربة {z.soil_type}</p>
              <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
                <dt className="text-muted">المساحة</dt><dd className="num m-0">{z.area_m2} م²</dd>
                <dt className="text-muted">عمق الجذور</dt><dd className="num m-0">{z.root_depth_m} م</dd>
                <dt className="text-muted">ذبول / سعة حقلية</dt><dd className="num m-0">{z.wilting_pct} / {z.field_capacity_pct}٪</dd>
                <dt className="text-muted">التدفق / الكفاءة</dt><dd className="num m-0">{z.nominal_flow_L_min} ل/د · {z.efficiency}</dd>
              </dl>
              <p className="mt-2 text-[11px] text-muted">أيام المولد: {f.map((x) => `${FAULT_AR[x.label] ?? x.label} ${x.n}`).join(" · ")}</p>
            </section>
          );
        })}
      </div>

      <div className="panel grid gap-4 p-5 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="نوع النموذج" value="Random Forest" hint="مع تعويض وترميز داخل Pipeline" />
        <Stat label="المهمة" value="Regression" hint="الرطوبة % بعد 6 ساعات" />
        <Stat label="التدريب / التحقق" value={`${d.data.counts.train} / ${d.data.counts.validation}`} hint={`فجوة مستبعدة ${d.data.counts.gap_excluded}`} />
        <Stat label="الاختبار" value={d.data.counts.test} hint="يونيو–أكتوبر 2026" />
        <Stat label="MAE / RMSE اختبار" value={`${fmt(dep.mae, 3)} / ${fmt(dep.rmse, 3)}`} unit="نقطة" tone="water" />
        <Stat label="R² اختبار" value={dep.r2.toFixed(3)} tone="water" hint={`${d.features.length} مدخلًا`} />
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <Panel title="المقارنة مع خطوط الأساس — الاختبار" subtitle="نقاط مئوية؛ الأقل أفضل. «الملف» = كما أورده الملف دون إعادة حساب">
          <GroupedBars categories={test.map((r) => SHORT[r.model_id] ?? r.model_id)} yFormat={(v) => v.toFixed(1)} height={240} series={[
            { name: "MAE", color: PALETTE.water, values: test.map((r) => r.mae) }, { name: "RMSE", color: PALETTE.ochre, values: test.map((r) => r.rmse) }]} />
          <div className="mt-3 overflow-x-auto"><table className="tbl min-w-[600px]">
            <thead><tr><th>النموذج</th><th>الفترة</th><th>المصدر</th><th>n</th><th>MAE</th><th>RMSE</th><th>R²</th></tr></thead>
            <tbody>{d.results.map((r) => (
              <tr key={r.model_id + r.split} className={r.model_id === "rf_deployed" ? "bg-water-pale/60 font-medium" : ""}>
                <td>{r.label_ar}</td><td>{r.split === "test" ? "اختبار" : "تحقق"}</td>
                <td><span className={`chip ${r.source === "computed_here" ? "bg-[#E6F0EA] text-leaf" : "bg-mist text-muted"}`}>{r.source === "computed_here" ? "محسوب هنا" : "الملف"}</span></td>
                <td className="num">{r.n}</td><td className="num">{fmt(r.mae, 4)}</td><td className="num">{fmt(r.rmse, 4)}</td><td className="num">{r.r2.toFixed(4)}</td></tr>))}
            </tbody></table></div>
          {wb && <p className="mt-2 rounded-lg bg-ochre-pale p-2 text-sm text-[#6d4a12]">قراءة صادقة: معادلة موازنة الماء في الملف أفضل في MAE (<span className="num">{fmt(wb.mae, 3)}</span> مقابل <span className="num">{fmt(dep.mae, 3)}</span>)
            وأسوأ في RMSE (<span className="num">{fmt(wb.rmse, 3)}</span> مقابل <span className="num">{fmt(dep.rmse, 3)}</span>): النموذج يقلل الأخطاء الكبيرة، والمعادلة أدق في الأيام المعتادة. صيغة المعادلة غير موثقة في الملف فلم نُعِد حسابها.</p>}
        </Panel>
        <Panel title="المتنبأ مقابل الفعلي" subtitle="نسبة مئوية؛ كل نقطة يوم ومنطقة" actions={<Tabs value={split} onChange={setSplit} items={[["test", "اختبار"], ["validation", "تحقق"]]} />}>
          {preds.data ? <Scatter label="v2 المتنبأ مقابل الفعلي" xLabel="الفعلي في المحاكاة (رطوبة بعد 6 ساعات)" points={preds.data.items.map((p) => ({ x: p.actual_vwc_pct / 100, y: p.predicted_vwc_pct / 100, id: p.event_id, color: ZONE_COLOR[p.zone_id], extra: p.zone_id }))} />
            : preds.error ? <ErrorBox message={preds.error} /> : <Loading />}
          <p className="text-xs text-muted">{o.zones.map((z) => <span key={z.zone_id} className="me-3"><span style={{ color: ZONE_COLOR[z.zone_id] }}>●</span> {z.zone_name}</span>)} المحاور بالكسر الحجمي (÷100).</p>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="الخطأ حسب المنطقة — الاختبار">
          <table className="tbl"><thead><tr><th>المنطقة</th><th>المحصول</th><th>n</th><th>MAE</th><th>RMSE</th><th>R²</th></tr></thead><tbody>
            {Object.entries(d.error_analysis_test.by_zone).map(([z, v]) => <tr key={z}><td><span style={{ color: ZONE_COLOR[z] }}>●</span> {v.zone_name}</td><td>{v.crop}</td><td className="num">{v.n}</td><td className="num">{fmt(v.mae, 3)}</td><td className="num">{fmt(v.rmse, 3)}</td><td className="num">{v.r2.toFixed(3)}</td></tr>)}
          </tbody></table>
          <p className="mt-2 text-xs text-muted">عند فقد القراءة الحالية: {Object.entries(d.error_analysis_test.by_missing_reading).map(([k, v]) => `${k === "1" ? "مفقودة" : "متاحة"} MAE ${fmt(v.mae, 3)} (n=${v.n})`).join(" · ")}</p>
        </Panel>
        <Panel title="أهم المدخلات" subtitle="Permutation على الاختبار — زيادة RMSE بالنقاط المئوية">
          <HBars items={d.importance.permutation_test.slice(0, 10).map((r) => ({ label: r.feature, value: r.rmse_increase, err: r.std, note: d.feature_descriptions_ar[r.feature] }))} format={(v) => v.toFixed(3)} />
        </Panel>
      </div>

      <WhatIf zones={o.zones} />

      <Panel title="الرطوبة بعد 6 ساعات — متوسط شهري" subtitle="من سجلات الملف (Outcomes)">
        <LineChart yFormat={(v) => v.toFixed(0) + "%"} series={o.zones.map((z) => ({ name: z.zone_name, color: ZONE_COLOR[z.zone_id],
          points: months.map((mo) => ({ x: new Date(mo + "-15"), y: o.monthly.find((r) => r.month === mo && r.zone_id === z.zone_id)?.after_vwc ?? null })) }))} />
      </Panel>

      <Panel title="ما لم يتوفر وحدود النموذج">
        <ul className="list-disc space-y-1 ps-5 text-sm">{[...d.not_available, ...d.limitations].map((x) => <li key={x}>{x}</li>)}</ul>
      </Panel>
    </div>
  );
}
