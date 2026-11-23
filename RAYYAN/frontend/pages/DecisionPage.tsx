import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Recommendation, type ZoneId } from "../services/api";
import SoilColumn from "../components/SoilColumn";
import { ActionBadge, ARM_AR, ErrorBox, Field, fmt, fmtL, OriginTag, Panel, Warnings, ZONE_AR } from "../components/ui";

export interface PageProps { param?: string | null }

interface Form {
  zone_id: ZoneId; decision_date: string; pre_vwc: string; sensor_age_min: string; sensor_quality: string;
  forecast_rain_mm: string; forecast_et0_mm: string; forecast_temperature_c: string; daily_budget_l: string; other_zone_request_l: string;
}
const INITIAL: Form = { zone_id: "Z02", decision_date: "2025-07-15", pre_vwc: "0.098", sensor_age_min: "30", sensor_quality: "ok",
  forecast_rain_mm: "0", forecast_et0_mm: "9.4", forecast_temperature_c: "37", daily_budget_l: "160", other_zone_request_l: "60" };
const PRESETS: { label: string; patch: Partial<Form> }[] = [
  { label: "صيف جاف", patch: { decision_date: "2025-07-15", pre_vwc: "0.098", sensor_age_min: "30", sensor_quality: "ok", forecast_rain_mm: "0", forecast_et0_mm: "9.4", forecast_temperature_c: "37", daily_budget_l: "160" } },
  { label: "تربة رطبة", patch: { decision_date: "2025-01-20", pre_vwc: "0.138", sensor_age_min: "30", sensor_quality: "ok", forecast_rain_mm: "0", forecast_et0_mm: "3.1", forecast_temperature_c: "15" } },
  { label: "مطر قادم", patch: { decision_date: "2025-03-10", pre_vwc: "0.100", sensor_age_min: "30", sensor_quality: "ok", forecast_rain_mm: "8", forecast_et0_mm: "2.2", forecast_temperature_c: "20" } },
  { label: "حساس معطل", patch: { pre_vwc: "", sensor_quality: "missing", sensor_age_min: "" } },
  { label: "قراءة قديمة", patch: { pre_vwc: "0.11", sensor_quality: "ok", sensor_age_min: "180" } },
  { label: "ميزانية محدودة", patch: { decision_date: "2025-06-03", pre_vwc: "0.085", sensor_age_min: "30", sensor_quality: "ok", forecast_rain_mm: "0", forecast_et0_mm: "11", forecast_temperature_c: "38", daily_budget_l: "40", other_zone_request_l: "60" } },
];
const num = (s: string) => (s.trim() === "" ? null : Number(s));

export function RecommendationView({ r }: { r: Recommendation }) {
  const d = r.decision, th = d.thresholds, wp = r.water_plan, pr = r.prediction;
  const cur = (r.inputs?.pre_vwc as number | undefined) ?? null;
  const warnings = [...r.warnings, ...(pr?.warnings ?? [])];
  return (
    <div className="space-y-4" aria-live="polite">
      <div className="panel grid gap-4 p-5 sm:grid-cols-[1fr_170px]">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className={`font-display text-5xl font-bold ${d.action === "IRRIGATE" ? "text-water" : d.action === "DEFER" ? "text-leaf" : "text-ochre"}`}>{d.action_ar}</span>
            <ActionBadge action={d.action} />
          </div>
          <p className="text-sm text-muted">{ZONE_AR[r.zone_id]} · {ARM_AR[r.trial_arm]} في المحاكاة · <span className="font-mono">{d.rule_version}</span>
            {r.recommendation_id && <> · حُفظت برقم <span className="num">{r.recommendation_id}</span></>}</p>
          <ul className="space-y-2">
            {d.reasons.map((x, i) => (
              <li key={i} className={`border-s-4 ps-3 text-sm ${x.kind === "decisive" ? "border-water font-medium" : "border-line text-muted"}`}>{x.text_ar}</li>
            ))}
          </ul>
          {wp && (
            <div className="grid grid-cols-3 gap-3 rounded-lg bg-water-pale/70 p-3">
              <div><div className="text-xs text-muted">الكمية المقترحة</div><div className="font-display text-3xl text-water"><span className="num">{fmtL(wp.volume_l, 0)}</span> <small className="text-sm">لتر</small></div></div>
              <div><div className="text-xs text-muted">مدة التشغيل</div><div className="font-display text-3xl"><span className="num">{wp.duration_min}</span> <small className="text-sm">دقيقة</small></div></div>
              <div><div className="text-xs text-muted">التدفق الاسمي</div><div className="font-display text-3xl"><span className="num">{wp.flow_l_min}</span> <small className="text-sm">ل/د</small></div></div>
            </div>
          )}
          <p className="rounded-lg border border-line bg-mist/60 p-2 text-xs text-muted">{r.valve_note ?? "لا يوجد صمام أو متحكم متصل؛ التوصية للعرض فقط ولا يُنفذ أي تشغيل."}</p>
        </div>
        <SoilColumn current={cur} target={th.target_vwc} trigger={th.trigger_vwc} wilting={th.wilting_point_vwc}
          predicted={pr?.available ? pr.post_vwc ?? null : null} />
      </div>

      <Warnings items={warnings} />

      {r.agreement && r.stored_decision && (
        <Panel title="مقارنة بقرار المحاكي المحفوظ" subtitle={r.agreement.note}>
          <div className="grid gap-3 text-sm sm:grid-cols-3">
            <div>القرار المحفوظ: <b>{r.stored_decision.action}</b> · <span className="num">{r.stored_decision.planned_volume_l}</span> ل</div>
            <div>طريقة المحاكي: <span className="font-mono">{r.stored_decision.method_version}</span></div>
            <div>{r.agreement.comparable ? (r.agreement.action_match && r.agreement.volume_match ? "✓ مطابق تمامًا" : "✗ مختلف") : "غير قابل للمقارنة المباشرة"}</div>
          </div>
        </Panel>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="كيف حُسبت العتبة" subtitle="قواعد rule_v1 بمعاملات zone_profiles (افتراضات محاكاة)">
          <table className="tbl"><tbody>
            {[["السعة الحقلية FC", fmt(th.field_capacity_vwc)], ["نقطة الذبول WP", fmt(th.wilting_point_vwc)], ["نسبة الاستنزاف p", fmt(th.depletion_fraction, 2)],
              ["الماء المتاح الكلي TAW", `${fmt(th.taw_mm, 1)} مم`], ["الماء سهل الإتاحة RAW", `${fmt(th.raw_mm, 1)} مم`],
              ["عتبة الأساس FC − p(FC−WP)", fmt(th.base_trigger_vwc)], ["Kc الشهري (دراسة Saeed)", fmt(th.kc_month, 2)],
              ["معامل الحرارة", th.temperature_factor == null ? "غير متاح" : fmt(th.temperature_factor, 3)], ["Kc القرار", fmt(th.kc_decision, 3)],
              ["تعديل الطلب الجوي", fmt(th.et_adjustment_vwc, 4)], ["عتبة الري", fmt(th.trigger_vwc)]].map(([k, v]) => (
              <tr key={k}><td>{k}</td><td className="num font-medium">{v}</td></tr>))}
          </tbody></table>
        </Panel>
        <Panel title="حساب كمية المياه" subtitle={wp ? "إعادة ملء منطقة الجذور حتى السعة الحقلية" : "لا تُحسب كمية لأن القرار ليس ريًا"}>
          {wp ? (
            <>
              <ol className="list-decimal space-y-1 ps-5 text-sm">{wp.explanation.map((e, i) => <li key={i}>{e}</li>)}</ol>
              {wp.limits_applied.length > 0 && <p className="mt-2 text-xs text-muted">القيود المطبقة: {wp.limits_applied.map((l) => ({ max_event_l: "حد الرية الواحدة", daily_budget: "الميزانية اليومية", whole_minutes: "دقائق كاملة" }[l] ?? l)).join("، ")}</p>}
              <p className="mt-2 text-xs text-muted">هذه معادلة قواعد، وليست جرعة مثلى متعلَّمة.</p>
            </>
          ) : <p className="text-sm text-muted">{d.action === "CHECK_SENSOR" ? "البيانات غير كافية لتوصية موثوقة: يجب التحقق من الحساس أولًا." : "الرطوبة لا تستدعي الري الآن أو المطر المتوقع يكفي."}</p>}
        </Panel>
      </div>

      {pr && (
        <Panel title="الرطوبة المتوقعة بعد الري" subtitle="بعد ساعتين من نهاية الرية" actions={<OriginTag kind="model" />}>
          {pr.available ? (
            <div className="grid gap-3 text-sm sm:grid-cols-3">
              <div><div className="text-xs text-muted">نموذج Random Forest</div><div className="font-display text-2xl text-water"><span className="num">{fmt(pr.post_vwc)}</span></div><div className="text-xs">تغير <span className="num">+{fmt(pr.delta_vwc, 4)}</span></div></div>
              <div><div className="text-xs text-muted">التقريب الخطي في الحزمة</div><div className="font-display text-2xl"><span className="num">{fmt(pr.linear_post_vwc)}</span></div><div className="text-xs">تغير <span className="num">+{fmt(pr.linear_delta_vwc, 4)}</span></div></div>
              <div><div className="text-xs text-muted">الهدف</div><div className="font-display text-2xl text-leaf"><span className="num">{fmt(pr.target_vwc)}</span></div><div className="text-xs font-mono">{pr.model_version}</div></div>
            </div>
          ) : <p className="text-sm text-muted">{pr.reason}</p>}
        </Panel>
      )}
    </div>
  );
}

export default function DecisionPage({ param }: PageProps) {
  const [form, setForm] = useState<Form>(INITIAL);
  const [res, setRes] = useState<Recommendation | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [replayId, setReplayId] = useState(param || "D20250715Z02");
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  // رقم تسلسلي للطلبات: تُهمل أي استجابة قديمة تصل بعد طلب أحدث (منع السباق بين الطلبات)
  const seq = useRef(0);
  async function run(p: Promise<Recommendation>) {
    const id = ++seq.current;
    setBusy(true); setErr(null);
    try { const r = await p; if (id === seq.current) setRes(r); }
    catch (e) { if (id === seq.current) setErr((e as Error).message); }
    finally { if (id === seq.current) setBusy(false); }
  }
  const submit = (e?: FormEvent, f: Form = form) => {
    e?.preventDefault();
    run(api.recommend({
      zone_id: f.zone_id, decision_date: f.decision_date, pre_vwc: num(f.pre_vwc), sensor_age_min: num(f.sensor_age_min),
      sensor_quality: f.sensor_quality, forecast_rain_mm: num(f.forecast_rain_mm), forecast_et0_mm: num(f.forecast_et0_mm),
      forecast_temperature_c: num(f.forecast_temperature_c), daily_budget_l: num(f.daily_budget_l), other_zone_request_l: num(f.other_zone_request_l) ?? 0,
    }));
  };
  const fillFromSim = async () => {
    setErr(null);
    try {
      const d = await api.simDefaults(form.decision_date);
      if (!d.forecast_available) { setErr("لا يوجد توقع محاكاة محفوظ لهذا التاريخ (النطاق 2024-01-01 إلى 2025-12-31)."); return; }
      const pre = d.pre_vwc_by_zone[form.zone_id];
      setForm({ ...form, pre_vwc: pre == null ? "" : String(pre), sensor_quality: pre == null ? "missing" : "ok", sensor_age_min: "0",
        forecast_rain_mm: String(+(d.forecast.rain_mm ?? 0).toFixed(2)), forecast_et0_mm: String(+(d.forecast.et0_mm ?? 0).toFixed(2)),
        forecast_temperature_c: String(+(d.forecast.temperature_c ?? 0).toFixed(1)) });
    } catch (e) { setErr((e as Error).message); }
  };
  useEffect(() => { if (param) run(api.replay(param, true)); else submit(); }, [param]);

  return (
    <div className="grid gap-5 xl:grid-cols-[22rem_1fr]">
      <div className="space-y-5">
        <Panel title="بيانات المنطقة والحساس والطقس" subtitle="جرّبي التوصية بقيم مختلفة؛ الحساب يتم في الخادم">
          <form onSubmit={submit} className="space-y-3">
            <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="المنطقة">
              {(["Z01", "Z02"] as ZoneId[]).map((z) => (
                <button type="button" key={z} role="radio" aria-checked={form.zone_id === z} onClick={() => setForm({ ...form, zone_id: z })}
                  className={`rounded-lg border px-2 py-2 text-sm ${form.zone_id === z ? "border-leaf bg-leaf text-white" : "border-line bg-white"}`}>{ZONE_AR[z]}</button>
              ))}
            </div>
            <Field label="تاريخ القرار"><input type="date" className="field field-num" value={form.decision_date} onChange={set("decision_date")} required /></Field>
            <fieldset className="space-y-2 rounded-lg border border-line p-3">
              <legend className="px-1 text-xs font-medium text-muted">الحساس</legend>
              <div className="grid grid-cols-2 gap-2">
                <Field label="الرطوبة" hint="m³/m³"><input className="field field-num" inputMode="decimal" value={form.pre_vwc} onChange={set("pre_vwc")} placeholder="فارغ = لا قراءة" /></Field>
                <Field label="عمر القراءة" hint="دقيقة"><input className="field field-num" inputMode="numeric" value={form.sensor_age_min} onChange={set("sensor_age_min")} /></Field>
              </div>
              <Field label="جودة القراءة">
                <select className="field" value={form.sensor_quality} onChange={set("sensor_quality")}>
                  <option value="ok">سليمة ok</option><option value="missing">مفقودة missing</option><option value="invalid_range">خارج المدى invalid_range</option><option value="unknown">غير معروفة</option>
                </select>
              </Field>
            </fieldset>
            <fieldset className="space-y-2 rounded-lg border border-line p-3">
              <legend className="px-1 text-xs font-medium text-muted">توقع الطقس لـ 24 ساعة</legend>
              <div className="grid grid-cols-3 gap-2">
                <Field label="مطر" hint="مم"><input className="field field-num" inputMode="decimal" value={form.forecast_rain_mm} onChange={set("forecast_rain_mm")} /></Field>
                <Field label="ET0" hint="مم"><input className="field field-num" inputMode="decimal" value={form.forecast_et0_mm} onChange={set("forecast_et0_mm")} /></Field>
                <Field label="حرارة" hint="°م"><input className="field field-num" inputMode="decimal" value={form.forecast_temperature_c} onChange={set("forecast_temperature_c")} /></Field>
              </div>
            </fieldset>
            <div className="grid grid-cols-2 gap-2">
              <Field label="ماء الموقع اليوم" hint="لتر"><input className="field field-num" inputMode="decimal" value={form.daily_budget_l} onChange={set("daily_budget_l")} /></Field>
              <Field label="طلب المنطقة الأخرى" hint="لتر"><input className="field field-num" inputMode="decimal" value={form.other_zone_request_l} onChange={set("other_zone_request_l")} /></Field>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {PRESETS.map((p) => (
                <button type="button" key={p.label} className="chip border border-line bg-white px-2.5 py-1 font-normal hover:border-leaf"
                  onClick={() => { const f = { ...form, ...p.patch }; setForm(f); submit(undefined, f); }}>{p.label}</button>
              ))}
            </div>
            <div className="flex gap-2">
              <button className="btn btn-primary flex-1 justify-center" disabled={busy}>{busy ? "جارٍ الحساب…" : "احسبي التوصية"}</button>
              <button type="button" className="btn btn-ghost text-sm" onClick={fillFromSim} title="املئي الرطوبة والطقس من بيانات المحاكاة لهذا التاريخ">من المحاكاة</button>
            </div>
          </form>
        </Panel>
        <Panel title="إعادة تشغيل قرار محفوظ" subtitle="بمدخلاته الأصلية من قاعدة البيانات، ومقارنته بالمحاكي">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); window.location.hash = `/decision/${replayId}`; if (param === replayId) run(api.replay(replayId, true)); }}>
            <input className="field field-num font-mono" value={replayId} onChange={(e) => setReplayId(e.target.value.trim())} aria-label="معرّف القرار" pattern="D\d{8}Z0[12]" title="مثل D20250715Z02" />
            <button className="btn btn-ghost">تشغيل</button>
          </form>
        </Panel>
      </div>
      <div className="min-w-0">
        {err && <div className="mb-4"><ErrorBox message={err} /></div>}
        {res ? <RecommendationView r={res} /> : !err && <p className="text-muted">جارٍ الحساب…</p>}
      </div>
    </div>
  );
}
