import { useEffect, useRef, useState } from "react";
import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { api, type ScenarioResult, type SimulationOut, type ZoneId } from "../services/api";
import { GroupedBars, Legend, PALETTE } from "../components/charts";
import { ErrorBox, fmt, fmtL, OriginTag, Panel, Warnings, ZONE_AR } from "../components/ui";
import type { PageProps } from "./DecisionPage";

interface Sc { label: string; zone_id: ZoneId; decision_date: string; pre_vwc: string; volume_l: string; duration_min: string; autoDuration: boolean; rain: string; et0: string }
const base = (i: number, v: string): Sc => ({ label: `${v} لترًا`, zone_id: "Z02", decision_date: "2025-07-15", pre_vwc: "0.10", volume_l: v, duration_min: String(+v / 2), autoDuration: true, rain: "", et0: "" });
const n = (s: string) => (s.trim() === "" ? null : Number(s));

function SweepChart({ s }: { s: ScenarioResult }) {
  const pts = s.sweep!;
  const W = 760, H = 260, m = { t: 14, r: 16, b: 34, l: 58 };
  const xs = scaleLinear().domain([0, 80]).range([m.l, W - m.r]);
  const ys = scaleLinear().domain([Math.min(0, ...pts.map((p) => Math.min(p.predicted_delta_vwc, p.linear_delta_vwc))),
    Math.max(...pts.map((p) => Math.max(p.predicted_delta_vwc, p.linear_delta_vwc)), s.target_vwc - s.pre_vwc) * 1.08]).range([H - m.b, m.t]).nice();
  const inR = pts.filter((p) => p.in_training_range);
  const lo = inR[0]?.volume_l ?? 16, hi = inR[inR.length - 1]?.volume_l ?? 80;
  const ml = line<(typeof pts)[number]>().x((p) => xs(p.volume_l)).y((p) => ys(p.predicted_delta_vwc))(pts);
  const ln = line<(typeof pts)[number]>().x((p) => xs(p.volume_l)).y((p) => ys(p.linear_delta_vwc))(pts);
  const need = s.target_vwc - s.pre_vwc;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" style={{ direction: "ltr" }} role="img" aria-label="منحنى الاستجابة حسب حجم الري">
        <rect x={xs(lo)} y={m.t} width={xs(hi) - xs(lo)} height={H - m.t - m.b} fill="#E3F1F8" />
        <text x={xs(lo) + 4} y={m.t + 12} fontSize="10.5" fill={PALETTE.water}>نطاق أحجام التدريب</text>
        {ys.ticks(5).map((t) => <g key={t}><line x1={m.l} x2={W - m.r} y1={ys(t)} y2={ys(t)} stroke="#E3EAE5" /><text x={m.l - 6} y={ys(t) + 4} fontSize="11" textAnchor="end" fill="#55685F">{t.toFixed(3)}</text></g>)}
        {[0, 20, 40, 60, 80].map((v) => <text key={v} x={xs(v)} y={H - 16} fontSize="11" textAnchor="middle" fill="#55685F">{v}</text>)}
        <text x={(W + m.l) / 2} y={H - 2} fontSize="11" textAnchor="middle" fill="#13302A">حجم الري (لتر)</text>
        <line x1={m.l} x2={W - m.r} y1={ys(need)} y2={ys(need)} stroke={PALETTE.leaf} strokeDasharray="6 4" />
        <text x={W - m.r} y={ys(need) - 5} fontSize="10.5" textAnchor="end" fill={PALETTE.leaf}>المطلوب لبلوغ الهدف {need.toFixed(3)}</text>
        <path d={ln ?? ""} fill="none" stroke={PALETTE.muted} strokeWidth="2" strokeDasharray="5 4" />
        <path d={ml ?? ""} fill="none" stroke={PALETTE.water} strokeWidth="2.6" />
        {pts.map((p) => <circle key={p.volume_l} cx={xs(p.volume_l)} cy={ys(p.predicted_delta_vwc)} r="3" fill={p.in_training_range ? PALETTE.water : "#fff"} stroke={PALETTE.water}><title>{`${p.volume_l} لتر: نموذج ${p.predicted_delta_vwc.toFixed(4)} · خطي ${p.linear_delta_vwc.toFixed(4)}`}</title></circle>)}
      </svg>
      <Legend items={[{ label: "تنبؤ النموذج Δ رطوبة", color: PALETTE.water }, { label: "التقريب الخطي في الحزمة", color: PALETTE.muted, dashed: true }, { label: "الفرق اللازم لبلوغ الهدف", color: PALETTE.leaf, dashed: true }]} />
      <p className="mt-1 text-xs text-muted">النقاط المفرغة خارج نطاق أحجام التدريب (استقراء). النموذج الشجري يثبت خارج نطاقه بدل أن يستمر في الصعود.</p>
    </div>
  );
}

export default function SimulationPage(_: PageProps) {
  const [scs, setScs] = useState<Sc[]>([base(0, "40"), base(1, "60"), base(2, "80")]);
  const [out, setOut] = useState<SimulationOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const upd = (i: number, patch: Partial<Sc>) => setScs(scs.map((s, k) => {
    if (k !== i) return s;
    const nx = { ...s, ...patch };
    if (nx.autoDuration && (patch.volume_l !== undefined || patch.autoDuration)) nx.duration_min = String((Number(nx.volume_l) || 0) / 2);
    return nx;
  }));
  const seq = useRef(0);
  async function run(list = scs) {
    const id = ++seq.current;
    setBusy(true); setErr(null);
    try {
      const res = await api.simulate({ sweep: true, scenarios: list.map((s) => ({
        label: s.label || undefined, zone_id: s.zone_id, decision_date: s.decision_date, pre_vwc: n(s.pre_vwc), volume_l: n(s.volume_l),
        duration_min: s.autoDuration ? undefined : n(s.duration_min), forecast_rain_mm: n(s.rain) ?? undefined, forecast_et0_mm: n(s.et0) ?? undefined,
      })) });
      if (id === seq.current) setOut(res);
    } catch (e) { if (id === seq.current) setErr((e as Error).message); } finally { if (id === seq.current) setBusy(false); }
  }
  useEffect(() => { run(); }, []);
  const r = out?.scenarios ?? [];
  return (
    <div className="space-y-5">
      <p className="rounded-lg border border-water/30 bg-water-pale p-3 text-sm text-[#164d6b]">
        نتائج المحاكاة مخرجات نموذج تعلّم من بيانات محاكاة، وليست قياسات ميدانية. غيّري الكمية أو المدة أو الرطوبة أو المنطقة، ثم قارني السيناريوهات.
      </p>
      <Panel title="السيناريوهات" subtitle="حتى 6 سيناريوهات؛ الطقس يُؤخذ من توقع المحاكاة لذلك اليوم ما لم تدخليه"
        actions={<div className="flex gap-2">
          <button className="btn btn-ghost text-sm" disabled={scs.length >= 6} onClick={() => setScs([...scs, { ...scs[scs.length - 1], label: `سيناريو ${scs.length + 1}` }])}>+ سيناريو</button>
          <button className="btn btn-primary" onClick={() => run()} disabled={busy}>{busy ? "جارٍ التشغيل…" : "شغّلي المحاكاة"}</button>
        </div>}>
        <div className="overflow-x-auto">
          <table className="tbl min-w-[880px]">
            <thead><tr><th>الاسم</th><th>المنطقة</th><th>التاريخ</th><th>الرطوبة الابتدائية</th><th>الكمية (ل)</th><th>المدة (د)</th><th>مطر (مم)</th><th>ET0 (مم)</th><th></th></tr></thead>
            <tbody>
              {scs.map((s, i) => (
                <tr key={i}>
                  <td><input className="field w-28 py-1" value={s.label} maxLength={40} onChange={(e) => upd(i, { label: e.target.value })} aria-label="اسم السيناريو" /></td>
                  <td><select className="field py-1" value={s.zone_id} onChange={(e) => upd(i, { zone_id: e.target.value as ZoneId })} aria-label="المنطقة"><option value="Z01">{ZONE_AR.Z01}</option><option value="Z02">{ZONE_AR.Z02}</option></select></td>
                  <td><input type="date" className="field field-num py-1" min="2024-01-01" max="2025-12-31" value={s.decision_date} onChange={(e) => upd(i, { decision_date: e.target.value })} aria-label="التاريخ" /></td>
                  <td><input className="field field-num w-20 py-1" inputMode="decimal" value={s.pre_vwc} onChange={(e) => upd(i, { pre_vwc: e.target.value })} aria-label="الرطوبة الابتدائية" /></td>
                  <td><input className="field field-num w-20 py-1" inputMode="decimal" value={s.volume_l} onChange={(e) => upd(i, { volume_l: e.target.value })} aria-label="الكمية" /></td>
                  <td>
                    <div className="flex items-center gap-1">
                      <input className="field field-num w-16 py-1" inputMode="decimal" value={s.duration_min} disabled={s.autoDuration} onChange={(e) => upd(i, { duration_min: e.target.value })} aria-label="المدة" />
                      <label className="flex items-center gap-1 text-xs text-muted" title="المدة = الكمية ÷ 2 لتر/دقيقة كما في كل بيانات التدريب"><input type="checkbox" checked={s.autoDuration} onChange={(e) => upd(i, { autoDuration: e.target.checked })} />تلقائي</label>
                    </div>
                  </td>
                  <td><input className="field field-num w-16 py-1" inputMode="decimal" placeholder="محفوظ" value={s.rain} onChange={(e) => upd(i, { rain: e.target.value })} aria-label="المطر" /></td>
                  <td><input className="field field-num w-16 py-1" inputMode="decimal" placeholder="محفوظ" value={s.et0} onChange={(e) => upd(i, { et0: e.target.value })} aria-label="التبخر-النتح" /></td>
                  <td><button className="text-sm text-danger disabled:opacity-30" disabled={scs.length === 1} onClick={() => setScs(scs.filter((_, k) => k !== i))} aria-label="حذف">حذف</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      {err && <ErrorBox message={err} />}
      {r.length > 0 && (
        <>
          <Panel title="مقارنة السيناريوهات" actions={<OriginTag kind="model" />}>
            <div className="overflow-x-auto">
              <table className="tbl min-w-[760px]">
                <thead><tr><th>السيناريو</th><th>الماء المستخدم</th><th>الرطوبة الابتدائية</th><th>المتوقعة بعد الري</th><th>الفرق</th><th>التقريب الخطي</th><th>بُعدها عن الهدف</th><th>لتر لكل 0.01</th></tr></thead>
                <tbody>
                  {r.map((s) => (
                    <tr key={s.simulation_id}>
                      <td><b>{s.label}</b><div className="text-xs text-muted">{ZONE_AR[s.zone_id]} · <span className="num">{s.decision_date}</span> · مطر <span className="num">{fmt(s.forecast_rain_mm, 1)}</span> · ET0 <span className="num">{fmt(s.forecast_et0_mm, 1)}</span></div></td>
                      <td className="whitespace-nowrap"><span className="num">{fmtL(s.volume_l)}</span> لتر · <span className="num">{fmtL(s.duration_min)}</span> دقيقة</td>
                      <td className="num">{fmt(s.pre_vwc)}</td>
                      <td className="num font-semibold text-water">{fmt(s.predicted_post_vwc)}</td>
                      <td className="num">+{fmt(s.predicted_delta_vwc, 4)}</td>
                      <td className="num text-muted">+{fmt(s.linear_delta_vwc, 4)}</td>
                      <td className={`num ${s.gap_to_target_vwc > 0 ? "text-ochre" : "text-leaf"}`}>{s.gap_to_target_vwc > 0 ? fmt(s.gap_to_target_vwc) + " تحت" : "بلغ الهدف"}</td>
                      <td className="num">{s.water_per_delta ? fmtL(s.water_per_delta / 100, 1) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4">
              <GroupedBars categories={r.map((s) => s.label)} yLabel="m³/m³" yFormat={(v) => v.toFixed(3)} series={[
                { name: "الرطوبة الابتدائية", color: "#C4A87F", values: r.map((s) => s.pre_vwc) },
                { name: "المتوقعة بعد الري (النموذج)", color: PALETTE.water, values: r.map((s) => s.predicted_post_vwc) },
                { name: "الهدف", color: PALETTE.leaf, values: r.map((s) => s.target_vwc) },
              ]} height={220} />
            </div>
            <div className="mt-3"><Warnings items={[...new Set(r.flatMap((s) => s.warnings))]} /></div>
          </Panel>
          {r[0].sweep && <Panel title={`منحنى الاستجابة — ${r[0].label}`} subtitle="كيف يتغير تنبؤ النموذج مع الكمية من 0 إلى 80 لترًا، مقارنة بالتقريب الخطي في الحزمة"><SweepChart s={r[0]} /></Panel>}
          <p className="text-xs text-muted">{out?.linear_note_ar} كل سيناريو حُفظ في جدول app_simulations.</p>
        </>
      )}
    </div>
  );
}
