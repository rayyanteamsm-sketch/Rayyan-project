// أقسام المحاصيل الأربع داخل صفحات التطبيق. كل نتيجة من الخادم: FAO-56 + نموذج المحاصيل + SQLite.
import { useEffect, useMemo, useState } from "react";
import { api, type CropHistoryItem, type CropRecommendation, type CropSimulation, type CropZoneId } from "../services/api";
import { CROP_COLOR, CropGlyph, CropRecommendResult, CropZoneCard, Kpi, pct } from "../components/crops";
import { GroupedBars, HBars, LineChart, ResponseCurve, Scatter } from "../components/charts";
import { ActionBadge, ErrorBox, Field, fmtL, fmtTime, Loading, OriginTag, Panel, Tabs, useApi, Warnings } from "../components/ui";

const ZONES: [CropZoneId, string][] = [["Z001", "نخيل مجدول"], ["Z002", "برسيم"], ["Z003", "خضار"], ["Z004", "نجيل"]];
const DEFAULT_DATE = "2026-07-01";
const go = (hash: string) => { window.location.hash = hash; };
const shift = (d: string, days: number) => new Date(Date.parse(d + "T00:00:00Z") + days * 864e5).toISOString().slice(0, 10);
const num = (s: string) => (s.trim() === "" ? undefined : Number(s));

function CropsNotice() {
  return (
    <p className="rounded-lg border border-water/25 bg-water-pale/60 px-3 py-2 text-xs text-[#17506d]">
      <b>المحاصيل الأربع — نموذج مستقل:</b> مجموعة RAYYAN v2 (محاكاة بالبذرة 42603، 2024-10 — 2026-10). لا تُخلط مع بيانات البرمودا.
      القرار والكمية بمعادلات FAO-56 بقيم المنطقة من الملف، والرطوبة المتوقعة من نموذج مدرب على هذه البيانات فقط.
    </p>
  );
}

// ================================================================== لوحة التحكم
export function CropsDashboardPanel() {
  const [date, setDate] = useState<string>("");
  const { data, error, loading, reload } = useApi(() => api.cropDashboard(date || undefined), [date]);
  useEffect(() => { if (data && !date) setDate(data.date); }, [data]);
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const irrigate = data.zones.filter((z) => z.decision.action === "IRRIGATE");
  const totalL = data.zones.reduce((s, z) => s + (z.water_plan?.volume_l ?? 0), 0);
  const usage = Object.fromEntries(data.usage_30d.map((u) => [u.zone_id, u]));
  const days = [...new Set(data.trend_30d.map((t) => t.date))];
  return (
    <div className={`space-y-5 ${loading ? "opacity-70" : ""}`}>
      <CropsNotice />
      <div className="panel flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="grid flex-1 grid-cols-2 gap-3 md:grid-cols-4">
          <Kpi label="مناطق تحتاج ري اليوم" value={`${irrigate.length} / ${data.zones.length}`} tone={irrigate.length ? "water" : "leaf"} />
          <Kpi label="إجمالي الماء المقترح اليوم" value={`${fmtL(totalL, 0)} ل`} tone="water" hint="مجموع كميات FAO-56" />
          <Kpi label="الماء المنفذ في الملف (30 يومًا)" value={`${fmtL(data.usage_30d.reduce((s, u) => s + u.actual_l, 0) / 1000, 1)} م³`} hint={`المخطط ${fmtL(data.usage_30d.reduce((s, u) => s + u.planned_l, 0) / 1000, 1)} م³`} />
          <Kpi label="النموذج" value={<span className="text-sm">{data.model.loaded ? "محمّل" : "غير متاح"}</span>} hint={<span className="font-mono">{data.model.version}</span>} tone="leaf" />
        </div>
        <div className="flex items-center gap-2">
          <button className="btn btn-ghost px-2" aria-label="اليوم السابق" onClick={() => setDate(shift(data.date, -1))} disabled={data.date <= data.range.min}>→</button>
          <input type="date" className="field w-auto" value={date} min={data.range.min} max={data.range.max} onChange={(e) => setDate(e.target.value)} aria-label="يوم البيانات" />
          <button className="btn btn-ghost px-2" aria-label="اليوم التالي" onClick={() => setDate(shift(data.date, 1))} disabled={data.date >= data.range.max}>←</button>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {data.zones.map((z) => <CropZoneCard key={z.zone.zone_id} d={z} onOpen={() => go(`#/zones/${z.zone.zone_id}`)} />)}
      </div>
      <div className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
        <Panel title="رطوبة التربة — آخر 30 يومًا" subtitle="قراءة الحساس عند قرار 06:00 UTC لكل منطقة (من الملف)">
          <LineChart yFormat={(v) => v.toFixed(0) + "%"} yLabel="VWC %"
            series={ZONES.map(([id, crop]) => ({ name: crop, color: CROP_COLOR[id],
              points: days.map((d) => ({ x: new Date(d), y: data.trend_30d.find((t) => t.zone_id === id && t.date === d)?.before_vwc ?? null })) }))} />
        </Panel>
        <Panel title="استهلاك المياه — 30 يومًا" subtitle="المخطط مقابل المنفذ في الملف (م³)">
          <GroupedBars categories={ZONES.map(([, c]) => c)} yFormat={(v) => v.toFixed(0)} yLabel="م³"
            series={[{ name: "مخطط", color: "#C4A87F", values: ZONES.map(([id]) => (usage[id]?.planned_l ?? 0) / 1000) },
              { name: "منفذ", color: "#1F7AA8", values: ZONES.map(([id]) => (usage[id]?.actual_l ?? 0) / 1000) }]} />
          <p className="mt-2 text-xs text-muted">عدد الريات: {ZONES.map(([id, c]) => `${c} ${usage[id]?.irrigations ?? 0}`).join(" · ")}</p>
        </Panel>
      </div>
      <Panel title="آخر التوصيات المحفوظة للمحاصيل" subtitle={data.note} actions={<a className="btn btn-ghost text-sm" href="#/history/crops">السجل الكامل</a>}>
        {data.recent_saved.length === 0 ? <p className="text-sm text-muted">لا توجد توصيات محفوظة بعد. شغّلي توصية من صفحة «توصية الري».</p> : (
          <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>#</th><th>وقت الحفظ</th><th>المنطقة</th><th>اليوم</th><th>المصدر</th><th>القرار</th><th>الكمية</th><th>المتوقعة</th></tr></thead>
            <tbody>{data.recent_saved.map((r) => <tr key={r.crop_rec_id}><td className="num">{r.crop_rec_id}</td><td className="num">{fmtTime(r.created_at)}</td>
              <td>{ZONES.find(([i]) => i === r.zone_id)?.[1]}</td><td className="num">{r.decision_date}</td><td>{r.source === "recommend" ? "توصية" : "محاكاة"}</td>
              <td><ActionBadge action={r.action} /></td><td className="num">{fmtL(r.volume_l, 0)} ل</td><td className="num">{pct(r.predicted_vwc_pct)}</td></tr>)}</tbody></table></div>)}
      </Panel>
    </div>
  );
}

// ================================================================== توصية الري
export function CropsRecommendPanel({ initialZone }: { initialZone?: string | null }) {
  const [zone, setZone] = useState<CropZoneId>((ZONES.find(([z]) => z === initialZone)?.[0]) ?? "Z004");
  const [date, setDate] = useState(DEFAULT_DATE);
  const [f, setF] = useState({ before: "", et0: "", rain: "", temp: "", hum: "", p: "", target: "", budget: "" });
  const [missing, setMissing] = useState(false);
  const [res, setRes] = useState<CropRecommendation | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const zones = useApi(() => api.cropZones(), []);
  const run = async (save: boolean) => {
    setBusy(true); setErr(null);
    try {
      setRes(await api.cropRecommend({ zone_id: zone, decision_date: date, save, sensor_missing: missing,
        before_VWC_pct: missing ? undefined : num(f.before), et0_forecast_24h_mm: num(f.et0), rain_forecast_24h_mm: num(f.rain),
        air_temp_observed_C: num(f.temp), humidity_observed_pct: num(f.hum), p_override: num(f.p), target_vwc_pct: num(f.target), daily_budget_l: num(f.budget) }));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  useEffect(() => { run(false); }, [zone, date]);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const used = res?.inputs_used;
  const ph = (k: string, unit = "") => (used && used[k] != null ? `${Number(used[k]).toFixed(2)}${unit} (من الملف)` : "من الملف");
  const rng = zones.data?.range;
  return (
    <div className="space-y-5">
      <CropsNotice />
      <div className="grid gap-5 xl:grid-cols-[340px_1fr]">
        <form className="panel h-fit space-y-3 p-4 xl:sticky xl:top-4" onSubmit={(e) => { e.preventDefault(); run(true); }}>
          <h3 className="font-display">المدخلات</h3>
          <div className="grid grid-cols-4 gap-1.5" role="radiogroup" aria-label="المنطقة">
            {ZONES.map(([id, c]) => (
              <button type="button" key={id} role="radio" aria-checked={zone === id} onClick={() => setZone(id)}
                className={`flex flex-col items-center rounded-lg border p-1.5 text-[11px] transition ${zone === id ? "border-water bg-water-pale" : "border-line bg-white hover:border-leaf"}`}>
                <CropGlyph zoneId={id} size={26} />{c}
              </button>))}
          </div>
          <Field label="يوم القرار" hint={rng ? `${rng.min} — ${rng.max}` : ""}><input type="date" className="field" value={date} min={rng?.min} max={rng?.max} onChange={(e) => setDate(e.target.value)} required /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="الرطوبة الحالية %"><input className="field field-num" inputMode="decimal" value={f.before} onChange={set("before")} placeholder={ph("before_VWC_pct")} disabled={missing} /></Field>
            <Field label="ET0 متوقع مم"><input className="field field-num" inputMode="decimal" value={f.et0} onChange={set("et0")} placeholder={ph("et0_forecast_24h_mm")} /></Field>
            <Field label="مطر متوقع مم"><input className="field field-num" inputMode="decimal" value={f.rain} onChange={set("rain")} placeholder={ph("rain_forecast_24h_mm")} /></Field>
            <Field label="الحرارة °C"><input className="field field-num" inputMode="decimal" value={f.temp} onChange={set("temp")} placeholder={ph("air_temp_observed_C")} /></Field>
            <Field label="الرطوبة الجوية %"><input className="field field-num" inputMode="decimal" value={f.hum} onChange={set("hum")} placeholder={ph("humidity_observed_pct")} /></Field>
            <Field label="p (FAO-56)"><input className="field field-num" inputMode="decimal" value={f.p} onChange={set("p")} placeholder={res ? String(res.zone.p_table) : ""} /></Field>
            <Field label="الهدف %"><input className="field field-num" inputMode="decimal" value={f.target} onChange={set("target")} placeholder={res ? `${res.zone.field_capacity_pct} (FC)` : "FC"} /></Field>
            <Field label="ميزانية لتر"><input className="field field-num" inputMode="decimal" value={f.budget} onChange={set("budget")} placeholder="بلا حد" /></Field>
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={missing} onChange={(e) => setMissing(e.target.checked)} />محاكاة فقد قراءة الحساس</label>
          <div className="flex gap-2">
            <button className="btn btn-primary flex-1 justify-center" disabled={busy}>{busy ? "جارٍ الحساب…" : "أصدري التوصية واحفظيها"}</button>
            <button type="button" className="btn btn-ghost" disabled={busy} onClick={() => run(false)}>معاينة</button>
          </div>
          <p className="text-[11px] text-muted">الحقول الفارغة تُؤخذ من سجل الملف لذلك اليوم. «احفظي» يسجل التوصية في SQLite (app_crop_recommendations). لا يُرسل أي أمر لصمام.</p>
        </form>
        <div className="min-w-0">{err ? <ErrorBox message={err} /> : res ? <CropRecommendResult r={res} /> : <Loading />}</div>
      </div>
    </div>
  );
}

// ================================================================== المحاكاة
interface Sc { label: string; volume: string; before: string; et0: string; rain: string }
export function CropsSimulationPanel() {
  const [zone, setZone] = useState<CropZoneId>("Z002");
  const [date, setDate] = useState("2026-08-01");
  const [sc, setSc] = useState<Sc[]>([
    { label: "دون ري", volume: "0", before: "", et0: "", rain: "" }, { label: "خطة متوسطة", volume: "6000", before: "", et0: "", rain: "" },
    { label: "إعادة ملء", volume: "20000", before: "", et0: "", rain: "" }]);
  const [res, setRes] = useState<CropSimulation | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true); setErr(null);
    try {
      setRes(await api.cropSimulate({ zone_id: zone, decision_date: date, scenarios: sc.map((s) => ({ label: s.label || undefined, volume_l: Number(s.volume || 0),
        before_VWC_pct: num(s.before), et0_forecast_24h_mm: num(s.et0), rain_forecast_24h_mm: num(s.rain) })) }));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  useEffect(() => { run(); }, [zone, date]);
  const upd = (i: number, k: keyof Sc, v: string) => setSc(sc.map((s, j) => (j === i ? { ...s, [k]: v } : s)));
  const colors = ["#13302A", "#1F7AA8", "#B97A22", "#2F6B4F", "#8A6A45", "#5B7186"];
  return (
    <div className="space-y-5">
      <CropsNotice />
      <Panel title="سيناريوهات الري" subtitle="غيّري الكمية أو الرطوبة الابتدائية أو الطقس (الفارغ = قيمة الملف لذلك اليوم)، ثم شغّلي النموذج الفعلي على الخادم.">
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <Field label="المنطقة"><select className="field" value={zone} onChange={(e) => setZone(e.target.value as CropZoneId)}>{ZONES.map(([id, c]) => <option key={id} value={id}>{id} — {c}</option>)}</select></Field>
          <Field label="اليوم"><input type="date" className="field" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
          <button className="btn btn-ghost" onClick={() => sc.length < 6 && setSc([...sc, { label: `سيناريو ${sc.length + 1}`, volume: "3000", before: "", et0: "", rain: "" }])} disabled={sc.length >= 6}>+ سيناريو</button>
          <button className="btn btn-primary" onClick={run} disabled={busy}>{busy ? "جارٍ التشغيل…" : "شغّلي المحاكاة"}</button>
        </div>
        <div className="overflow-x-auto"><table className="tbl"><thead><tr><th>الاسم</th><th>الكمية (لتر)</th><th>رطوبة ابتدائية %</th><th>ET0 مم</th><th>مطر مم</th><th /></tr></thead>
          <tbody>{sc.map((s, i) => <tr key={i}>
            <td><span className="me-1 inline-block h-2.5 w-2.5 rounded-full" style={{ background: colors[i] }} /><input className="field inline-block w-32" value={s.label} onChange={(e) => upd(i, "label", e.target.value)} /></td>
            <td><input className="field field-num w-28" inputMode="decimal" value={s.volume} onChange={(e) => upd(i, "volume", e.target.value)} /></td>
            <td><input className="field field-num w-24" inputMode="decimal" value={s.before} placeholder="الملف" onChange={(e) => upd(i, "before", e.target.value)} /></td>
            <td><input className="field field-num w-20" inputMode="decimal" value={s.et0} placeholder="الملف" onChange={(e) => upd(i, "et0", e.target.value)} /></td>
            <td><input className="field field-num w-20" inputMode="decimal" value={s.rain} placeholder="الملف" onChange={(e) => upd(i, "rain", e.target.value)} /></td>
            <td><button className="text-xs text-danger hover:underline disabled:opacity-40" disabled={sc.length === 1} onClick={() => setSc(sc.filter((_, j) => j !== i))}>حذف</button></td></tr>)}</tbody></table></div>
      </Panel>
      {err && <ErrorBox message={err} />}
      {res && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {res.scenarios.map((s, i) => (
              <div key={i} className="panel lift p-4" style={{ borderInlineStart: `4px solid ${colors[i]}` }}>
                <div className="flex items-center justify-between"><b>{s.label}</b><OriginTag kind="model" /></div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <Kpi label="الرطوبة بعد 6 ساعات (ML)" value={pct(s.predicted_vwc_pct)} tone="water" hint={s.change_pp != null ? `التغير ${s.change_pp >= 0 ? "+" : ""}${s.change_pp.toFixed(2)} نقطة` : ""} />
                  <Kpi label="موازنة الماء (معادلة)" value={pct(s.water_balance_vwc_pct)} hint={`عمق صافٍ ${s.depth_mm_net.toFixed(1)} مم`} />
                </div>
                <p className="mt-2 text-xs text-muted"><span className="num">{fmtL(s.volume_l, 0)}</span> لتر · <span className="num">{s.duration_min.toFixed(1)}</span> دقيقة · من <span className="num">{pct(s.before_vwc_pct)}</span> · محفوظ #{s.saved_id}</p>
                {s.warnings.length > 0 && <p className="mt-1 text-[11px] text-ochre">⚠ {s.warnings[0]}</p>}
              </div>))}
          </div>
          <Panel title={`منحنى الاستجابة — ${res.crop} (${res.date})`} subtitle={res.disclaimer_ar}>
            <ResponseCurve
              series={[{ name: "نموذج المحاصيل (ML)", color: "#1F7AA8", points: res.curve.map((c) => ({ x: c.volume_l, y: c.predicted_vwc_pct })) },
                { name: "موازنة الماء (معادلة)", color: "#8A6A45", dashed: true, points: res.curve.map((c) => ({ x: c.volume_l, y: c.water_balance_vwc_pct })) }]}
              refLines={[{ y: res.field_capacity_pct, label: `السعة الحقلية ${res.field_capacity_pct}%`, color: "#2F6B4F" }, { y: res.wilting_pct, label: `الذبول ${res.wilting_pct}%`, color: "#8A6A45", dashed: true }]}
              band={{ from: res.training_volume_range_l[0], to: res.training_volume_range_l[1], label: "نطاق التدريب" }}
              markers={res.scenarios.map((s, i) => ({ x: s.volume_l, y: s.predicted_vwc_pct, label: s.label, color: colors[i] }))} />
            <p className="mt-2 text-xs text-muted">المنحنى للسيناريو الأول بمدخلاته. خارج نطاق التدريب يثبت النموذج الشجري تقريبًا، فلا يُعتمد عليه هناك. النموذج: <span className="font-mono">{res.model_version}</span></p>
          </Panel>
        </>
      )}
    </div>
  );
}

// ================================================================== أداء النموذج
export function CropsModelPanel() {
  const { data: m, error, reload } = useApi(() => api.cropMetrics(), []);
  const [split, setSplit] = useState<"test" | "validation">("test");
  const preds = useApi(() => api.cropPredictions(split), [split]);
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!m) return <Loading />;
  const rows = m.results.filter((r) => r.split === split);
  const computed = rows.filter((r) => r.source === "computed_here");
  const famAr: Record<string, string> = { rf: "Random Forest", hgb: "HistGradientBoosting", ridge: "Ridge" };
  const modeAr: Record<string, string> = { absolute: "هدف مطلق", delta: "هدف التغير", hybrid: "هجين (تصحيح موازنة الماء)" };
  const checks = Object.entries(m.data.checks).filter(([, v]) => typeof v === "boolean");
  const h = m.headline;
  return (
    <div className="space-y-5">
      <CropsNotice />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Kpi label="نوع النموذج" value={<span className="text-base">{famAr[m.family]}</span>} hint={modeAr[m.target_mode]} tone="leaf" />
        <Kpi label="المهمة" value={<span className="text-base">Regression</span>} hint={`${m.target_unit} — ${m.horizon}`} />
        <Kpi label="التدريب / التحقق / الاختبار" value={`${m.data.counts.train} / ${m.data.counts.validation} / ${m.data.counts.test}`} hint="تقسيم زمني من الملف" />
        <Kpi label="الاختبار MAE / RMSE" value={`${h.deployed_test.mae.toFixed(3)} / ${h.deployed_test.rmse.toFixed(3)}`} hint="نقطة مئوية" tone="water" />
        <Kpi label="الاختبار R²" value={h.deployed_test.r2.toFixed(3)} hint={`خفض RMSE ${h.rmse_reduction_vs_persistence_pct.toFixed(0)}% مقابل بقاء الرطوبة`} tone="water" />
      </div>
      <div className="rounded-lg border border-ochre/40 bg-ochre-pale p-3 text-sm text-[#6d4a12]">
        <b>قراءة صادقة:</b> خط الأساس الفيزيائي (موازنة الماء) قوي جدًا: RMSE الاختبار {h.water_balance_test.rmse.toFixed(3)} مقابل {h.deployed_test.rmse.toFixed(3)} للنموذج المستخدم
        (تحسن {(100 * (1 - h.deployed_test.rmse / h.water_balance_test.rmse)).toFixed(1)}% فقط). النموذج المختار هجين يتعلم تصحيح المعادلة، وقد اختير على التحقق فقط
        بشرط أن تكون استجابته للكمية رتيبة في ≥ {m.selection.monotonic_min_pct}% من صفوف التحقق. كل المقاييس تقيس تعلم المحاكاة لا دقة ميدانية.
      </div>
      <div className="grid gap-5 xl:grid-cols-[1.35fr_1fr]">
        <Panel title="المقارنة مع خطوط الأساس" subtitle="نقاط مئوية؛ الأقل أفضل في MAE وRMSE" actions={<Tabs value={split} onChange={setSplit} items={[["test", "الاختبار"], ["validation", "التحقق"]]} />}>
          <GroupedBars categories={computed.map((r) => r.model_id.replace("_", " "))} yFormat={(v) => v.toFixed(1)}
            highlight={split === "test" ? "deployed" : undefined}
            series={[{ name: "MAE", color: "#1F7AA8", values: computed.map((r) => r.mae) }, { name: "RMSE", color: "#B97A22", values: computed.map((r) => r.rmse) }]} />
          <div className="mt-3 overflow-x-auto"><table className="tbl"><thead><tr><th>النموذج</th><th>المصدر</th><th>دُرب على</th><th>n</th><th>MAE</th><th>RMSE</th><th>R²</th></tr></thead>
            <tbody>{rows.map((r, i) => <tr key={i} className={r.model_id === "deployed" ? "bg-water-pale/60 font-semibold" : ""}>
              <td>{r.label_ar}</td><td>{r.source === "computed_here" ? <span className="chip bg-[#E6F0EA] text-leaf">محسوب هنا</span> : <span className="chip bg-[#EEE8DF] text-soil">مُبلَّغ في الملف</span>}</td>
              <td className="text-xs">{r.trained_on}</td><td className="num">{r.n}</td><td className="num">{r.mae.toFixed(3)}</td><td className="num">{r.rmse.toFixed(3)}</td><td className="num">{r.r2.toFixed(3)}</td></tr>)}</tbody></table></div>
        </Panel>
        <Panel title="المتنبأ مقابل الفعلي" subtitle={`${split === "test" ? "الاختبار — النموذج المستخدم" : "التحقق — نسخة مدربة على التدريب فقط"} (VWC %)`}>
          {preds.data ? <Scatter xLabel="الفعلي في المحاكاة (VWC %)" label="المتنبأ مقابل الفعلي"
            points={preds.data.items.map((p) => ({ x: p.actual_vwc_pct, y: p.predicted_vwc_pct, color: CROP_COLOR[p.zone_id], id: p.event_id, extra: p.feature_cutoff_at.slice(0, 10) }))} /> : <Loading />}
          <div className="mt-1 flex flex-wrap gap-3 text-xs text-muted">{ZONES.map(([id, c]) => <span key={id}><i className="me-1 inline-block h-2.5 w-2.5 rounded-full align-middle" style={{ background: CROP_COLOR[id] }} />{c}</span>)}</div>
        </Panel>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="الخطأ حسب المحصول — الاختبار" subtitle="R² داخل المنطقة أقل من الإجمالي لأن معظم التباين بين المناطق">
          <table className="tbl"><thead><tr><th>المحصول</th><th>n</th><th>MAE</th><th>RMSE</th><th>R²</th><th>MAE بقاء الرطوبة</th></tr></thead>
            <tbody>{Object.entries(m.error_analysis_test.by_zone).map(([id, z]) => <tr key={id}><td><i className="me-1 inline-block h-2.5 w-2.5 rounded-full" style={{ background: CROP_COLOR[id] }} />{z.crop}</td>
              <td className="num">{z.n}</td><td className="num">{z.mae.toFixed(3)}</td><td className="num">{z.rmse.toFixed(3)}</td><td className="num">{z.r2.toFixed(3)}</td><td className="num text-muted">{z.persistence_mae.toFixed(3)}</td></tr>)}</tbody></table>
          <p className="mt-2 text-xs text-muted">عند فقد القراءة الحالية: {Object.entries(m.error_analysis_test.by_missing_reading).map(([k, v]) => `${k === "1" ? "مفقودة" : "متاحة"} MAE ${v.mae.toFixed(3)} (n=${v.n})`).join(" · ")}</p>
          <h4 className="mt-4 mb-1 text-sm font-semibold">فحص الاستجابة للكمية (الاختبار)</h4>
          <p className="text-sm">رتيبة في <b className="num">{m.response_check_test.monotonic_rows_pct.toFixed(1)}%</b> من الصفوف · متوسط أثر الخطة مقابل عدم الري <b className="num">+{m.response_check_test.mean_gain_planned_vs_none_pp.toFixed(2)}</b> نقطة.</p>
        </Panel>
        <Panel title="أهمية المدخلات (Feature Importance)" subtitle={m.importance.note}>
          <HBars format={(v) => v.toFixed(3)} items={m.importance.permutation_test.slice(0, 12).map((r) => ({ label: r.feature, value: r.rmse_increase, err: r.std, note: m.feature_descriptions_ar[r.feature] }))} />
          <p className="mt-2 text-xs text-muted">زيادة RMSE (نقطة مئوية) عند خلط المدخل عشوائيًا. مرّري المؤشر على الاسم لقراءة وصفه من القاموس.</p>
        </Panel>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="اختيار النموذج" subtitle={m.selection.method}>
          <p className="mb-2 text-sm">{m.selection.n_candidates} إعدادًا · المؤهل بشرط الرتابة {m.selection.n_eligible}. أفضل 8 على التحقق:</p>
          <table className="tbl"><thead><tr><th>العائلة</th><th>الهدف</th><th>RMSE تحقق</th><th>رتابة %</th></tr></thead>
            <tbody>{m.selection.all.slice(0, 8).map((r, i) => <tr key={i} className={i === 0 ? "font-semibold" : ""}><td>{famAr[r.family]}</td><td>{modeAr[r.target_mode]}</td><td className="num">{r.rmse.toFixed(4)}</td><td className="num">{r.monotonic_val_pct.toFixed(1)}</td></tr>)}</tbody></table>
        </Panel>
        <Panel title="منع تسرب البيانات" subtitle="فحوص تُشغَّل قبل التدريب؛ يتوقف التدريب إن فشل أي منها">
          <ul className="space-y-1 text-sm">{checks.map(([k, v]) => <li key={k} className="flex items-center gap-2"><span className={v ? "text-leaf" : "text-danger"}>{v ? "✓" : "✗"}</span><span className="font-mono text-xs">{k}</span></li>)}</ul>
          <p className="mt-2 text-xs text-muted">مدخلات ممنوعة ({m.forbidden_inputs.length}): الحجم والتدفق الفعليان، الطقس المتحقق، الهدف، وحالة المولد الخفية.</p>
          <p className="mt-1 text-xs text-muted">الإصدار <span className="font-mono">{m.model_version}</span> · دُرب {fmtTime(m.trained_at)} · {m.training_seconds} ث · scikit-learn {String(m.software["scikit-learn"])}</p>
        </Panel>
      </div>
      <Panel title="حدود النموذج"><ul className="list-disc space-y-1 ps-5 text-sm">{m.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></Panel>
    </div>
  );
}

// ================================================================== السجل
export function CropsHistoryPanel() {
  const [q, setQ] = useState({ zone_id: "", action: "", source: "", date_from: "", date_to: "", search: "" });
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<number | null>(null);
  const limit = 25;
  const params = useMemo(() => ({ ...q, limit, offset }), [q, offset]);
  const { data, error, loading, reload } = useApi(() => api.cropHistory(params), [params]);
  const set = (k: keyof typeof q) => (e: { target: { value: string } }) => { setQ({ ...q, [k]: e.target.value }); setOffset(0); };
  return (
    <div className="space-y-4">
      <div className="panel grid gap-2 p-4 sm:grid-cols-3 lg:grid-cols-6">
        <Field label="بحث"><input className="field" value={q.search} onChange={set("search")} placeholder="رقم، سجل E…، محصول" /></Field>
        <Field label="المنطقة"><select className="field" value={q.zone_id} onChange={set("zone_id")}><option value="">الكل</option>{ZONES.map(([id, c]) => <option key={id} value={id}>{c}</option>)}</select></Field>
        <Field label="القرار"><select className="field" value={q.action} onChange={set("action")}><option value="">الكل</option><option value="IRRIGATE">ري</option><option value="DEFER">تأجيل</option><option value="CHECK_SENSOR">فحص الحساس</option></select></Field>
        <Field label="المصدر"><select className="field" value={q.source} onChange={set("source")}><option value="">الكل</option><option value="recommend">توصية</option><option value="simulation">محاكاة</option></select></Field>
        <Field label="من يوم"><input type="date" className="field" value={q.date_from} onChange={set("date_from")} /></Field>
        <Field label="إلى يوم"><input type="date" className="field" value={q.date_to} onChange={set("date_to")} /></Field>
      </div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && (
        <div className={`panel overflow-x-auto p-0 ${loading ? "opacity-60" : ""}`}>
          <table className="tbl"><thead><tr><th>#</th><th>وقت الحفظ (UTC)</th><th>المحصول</th><th>يوم البيانات</th><th>المصدر</th><th>القرار</th><th>قبل</th><th>الكمية</th><th>المتوقعة 6 س</th><th /></tr></thead>
            <tbody>{data.items.length === 0 && <tr><td colSpan={10} className="p-6 text-center text-muted">لا توجد سجلات مطابقة.</td></tr>}
              {data.items.map((r: CropHistoryItem) => [
                <tr key={r.crop_rec_id}><td className="num">{r.crop_rec_id}</td><td className="num">{fmtTime(r.created_at)}</td>
                  <td><i className="me-1 inline-block h-2.5 w-2.5 rounded-full" style={{ background: CROP_COLOR[r.zone_id] }} />{r.crop}</td><td className="num">{r.decision_date}</td>
                  <td>{r.source === "recommend" ? "توصية" : "محاكاة"}</td><td><ActionBadge action={r.action} /></td><td className="num">{pct(r.before_vwc_pct)}</td>
                  <td className="num">{fmtL(r.volume_l, 0)} ل</td><td className="num">{pct(r.predicted_vwc_pct)}</td>
                  <td><button className="text-xs text-water hover:underline" onClick={() => setOpen(open === r.crop_rec_id ? null : r.crop_rec_id)}>{open === r.crop_rec_id ? "إخفاء" : "التفاصيل"}</button></td></tr>,
                open === r.crop_rec_id && <tr key={`d${r.crop_rec_id}`}><td colSpan={10} className="bg-mist/60">
                  <div className="grid gap-2 p-2 text-sm md:grid-cols-2"><div><b>الأسباب</b><ul className="list-disc ps-5">{r.reasons.map((t, i) => <li key={i}>{t}</li>)}</ul></div>
                    <div className="text-xs text-muted"><div>السجل الأساسي: <span className="font-mono">{r.base_event_id}</span> · القاعدة: <span className="font-mono">{r.rule_code}</span></div>
                      <div>الاستنزاف {r.depletion_mm?.toFixed(1) ?? "—"} مم · RAW {r.raw_mm?.toFixed(1) ?? "—"} مم · دون ري {pct(r.predicted_no_irrigation_vwc_pct)}</div>
                      <div>النموذج: <span className="font-mono">{r.model_version}</span></div>{r.warnings.length > 0 && <Warnings items={r.warnings} />}</div></div></td></tr>,
              ])}</tbody></table>
          <div className="flex items-center justify-between border-t border-line p-3 text-sm">
            <span className="text-muted">{data.total} سجلًا · يعرض {data.total ? offset + 1 : 0}–{Math.min(offset + limit, data.total)}</span>
            <div className="flex gap-2"><button className="btn btn-ghost py-1" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>السابق</button>
              <button className="btn btn-ghost py-1" disabled={offset + limit >= data.total} onClick={() => setOffset(offset + limit)}>التالي</button></div>
          </div>
        </div>
      )}
    </div>
  );
}
