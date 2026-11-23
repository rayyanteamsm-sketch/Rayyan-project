// مكونات المحاصيل الأربع. كل الأرقام من الخادم (FAO-56 + نموذج المحاصيل)؛ الواجهة تعرض فقط.
import type { ReactNode } from "react";
import type { CropDashZone, CropRecommendation, CropZone } from "../services/api";
import { ResponseCurve } from "./charts";
import SoilColumn from "./SoilColumn";
import { ActionBadge, fmtL, Warnings } from "./ui";

export const CROP_COLOR: Record<string, string> = { Z001: "#B97A22", Z002: "#2F6B4F", Z003: "#1F7AA8", Z004: "#7FA66A" };
export const pct = (v: number | null | undefined, d = 2) => (v == null || Number.isNaN(v) ? "—" : `${v.toFixed(d)}%`);

/** رمز مرسوم لكل محصول (SVG بسيط بلا صور خارجية). */
export function CropGlyph({ zoneId, size = 40 }: { zoneId: string; size?: number }) {
  const c = CROP_COLOR[zoneId] ?? "#2F6B4F";
  const g: Record<string, ReactNode> = {
    Z001: <g stroke={c} strokeWidth="2.4" fill="none" strokeLinecap="round"><path d="M20 38V17" /><path d="M20 17c-4-5-10-6-15-4M20 17c4-5 10-6 15-4M20 16c-2-6-7-9-11-9M20 16c2-6 7-9 11-9M20 15c0-4 1-8 0-11" /><circle cx="17" cy="21" r="1.6" fill={c} /><circle cx="22" cy="22" r="1.6" fill={c} /></g>,
    Z002: <g stroke={c} strokeWidth="2.2" fill="none" strokeLinecap="round">{[8, 14, 20, 26, 32].map((x, i) => <path key={x} d={`M${x} 37c0-8 ${i % 2 ? 2 : -2}-14 ${i % 2 ? 4 : -3}-${20 + (i % 3) * 3}`} />)}<circle cx="12" cy="15" r="2" fill={c} /><circle cx="27" cy="12" r="2" fill={c} /></g>,
    Z003: <g stroke={c} strokeWidth="2.2" fill="none" strokeLinecap="round"><path d="M5 37h30M8 37V21l12-9 12 9v16" /><path d="M14 31c0-4 2-6 6-7M20 37v-9M26 31c0-4-2-6-6-7" /><circle cx="20" cy="22" r="2.4" fill={c} /></g>,
    Z004: <g stroke={c} strokeWidth="2" fill="none" strokeLinecap="round">{Array.from({ length: 9 }, (_, i) => <path key={i} d={`M${5 + i * 3.8} 37q${i % 2 ? 2 : -2} -7 ${i % 3 - 1} -${10 + (i * 5) % 9}`} />)}<path d="M3 37h34" /></g>,
  };
  return <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true">{g[zoneId] ?? g.Z004}</svg>;
}

/** شريط أفقي يوضح موقع الرطوبة بين الذبول والسعة الحقلية والتشبع، مع العتبة والمتوقع. */
export function MoistureGauge({ wp, fc, sat, trigger, current, predicted }: { wp: number; fc: number; sat: number; trigger: number; current: number | null; predicted?: number | null }) {
  const lo = Math.max(0, wp - 4), hi = sat;
  const x = (v: number) => `${Math.min(100, Math.max(0, ((v - lo) / (hi - lo)) * 100))}%`;
  return (
    <div className="pt-5 pb-6" aria-label={`الرطوبة ${pct(current)} بين الذبول ${wp}% والسعة الحقلية ${fc}%`}>
      <div className="relative h-3 rounded-full" style={{ background: `linear-gradient(to left, #1F7AA8 0%, #8CC9E6 ${100 - ((fc - lo) / (hi - lo)) * 100}%, #E9D9B8 ${100 - ((trigger - lo) / (hi - lo)) * 100}%, #C4A87F 100%)`, direction: "ltr" }}>
        {[["WP", wp, "#8A6A45"], ["عتبة", trigger, "#B97A22"], ["FC", fc, "#2F6B4F"]].map(([l, v, col]) => (
          <span key={l as string} className="absolute top-full mt-1 -translate-x-1/2 text-[10px] font-semibold" style={{ left: x(v as number), color: col as string }}>{l} {(v as number).toFixed(1)}</span>
        ))}
        {predicted != null && <span className="absolute -top-1 h-5 w-1 -translate-x-1/2 rounded bg-water-light ring-2 ring-white" style={{ left: x(predicted), transition: "left .9s" }} title={`المتوقعة ${pct(predicted)}`} />}
        {current != null && <span className="absolute -top-1.5 h-6 w-1.5 -translate-x-1/2 rounded bg-ink ring-2 ring-white" style={{ left: x(current), transition: "left .9s" }} />}
        {current != null && <span className="num absolute bottom-full mb-1 -translate-x-1/2 text-[11px] font-bold text-ink" style={{ left: x(current) }}>{current.toFixed(1)}%</span>}
      </div>
    </div>
  );
}

export function ZoneHeader({ z, right }: { z: CropZone; right?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="flex items-center gap-3">
        <span className="grid h-12 w-12 place-items-center rounded-xl" style={{ background: `${CROP_COLOR[z.zone_id]}18` }}><CropGlyph zoneId={z.zone_id} size={34} /></span>
        <div>
          <h3 className="text-lg font-medium">{z.crop} <span className="font-mono text-xs text-muted">{z.zone_id}</span></h3>
          <p className="text-xs text-muted">{z.zone_name} · {fmtL(z.area_m2, 0)} م² · {z.irrigation_system} · {z.soil_type}</p>
        </div>
      </div>
      {right}
    </div>
  );
}

/** بطاقة منطقة في لوحة التحكم. */
export function CropZoneCard({ d, onOpen }: { d: CropDashZone; onOpen?: () => void }) {
  const z = d.zone, m = d.model;
  return (
    <article className="panel lift flex flex-col gap-3 p-4" style={{ borderTop: `3px solid ${CROP_COLOR[z.zone_id]}` }}>
      <ZoneHeader z={z} right={<ActionBadge action={d.decision.action} />} />
      <MoistureGauge wp={z.wilting_pct} fc={z.field_capacity_pct} sat={z.saturation_pct_assumed} trigger={d.fao56.trigger_vwc_pct}
        current={d.before_vwc_pct} predicted={m?.predicted_vwc_with_plan_pct} />
      <dl className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-lg bg-mist/70 p-2"><dt className="text-[11px] text-muted">الحالية</dt><dd className="num font-display text-lg">{pct(d.before_vwc_pct, 1)}</dd></div>
        <div className="rounded-lg bg-mist/70 p-2"><dt className="text-[11px] text-muted">الهدف (FC)</dt><dd className="num font-display text-lg text-leaf">{pct(z.field_capacity_pct, 0)}</dd></div>
        <div className="rounded-lg bg-water-pale p-2"><dt className="text-[11px] text-muted">بعد 6 ساعات</dt><dd className="num font-display text-lg text-water">{pct(m?.predicted_vwc_with_plan_pct, 1)}</dd></div>
      </dl>
      <div className="flex items-end justify-between gap-2 border-t border-line pt-3 text-sm">
        <div><div className="text-xs text-muted">الكمية المقترحة</div>
          <div className="font-display text-xl"><span className="num">{d.water_plan ? fmtL(d.water_plan.volume_l, 0) : "0"}</span> <span className="text-xs text-muted">لتر</span></div>
          <div className="text-[11px] text-muted">{d.water_plan ? <>مدة <span className="num">{d.water_plan.duration_min.toFixed(1)}</span> دقيقة</> : "لا ري اليوم"}</div></div>
        <div className="text-end text-[11px] text-muted">الاستنزاف <span className="num text-ink">{d.fao56.depletion_mm == null ? "—" : d.fao56.depletion_mm.toFixed(1)}</span> / RAW <span className="num text-ink">{d.fao56.raw_mm.toFixed(1)}</span> مم
          {onOpen && <button className="mt-1 block text-water hover:underline" onClick={onOpen}>التفاصيل ←</button>}</div>
      </div>
    </article>
  );
}

const RULE_AR: Record<string, string> = {
  depletion_ge_raw: "الاستنزاف بلغ حد الإجهاد RAW", will_cross_raw_24h: "سيبلغ حد الإجهاد خلال 24 ساعة",
  depletion_below_raw: "الماء سهل الإتاحة كافٍ", rain_covers_depletion: "المطر المتوقع يغطي الاستنزاف",
  sensor_missing: "قراءة الحساس مفقودة", sensor_out_of_range: "قراءة خارج المدى الفيزيائي",
};

/** عرض نتيجة توصية كاملة: القرار، الأسباب، الحسابات، الكمية، تنبؤ النموذج، المنحنى. */
export function CropRecommendResult({ r }: { r: CropRecommendation }) {
  const z = r.zone, m = r.model, plan = r.water_plan;
  const rng = m?.training_volume_range_l;
  return (
    <div className="space-y-4">
      <div className="panel overflow-hidden">
        <div className="hero-strip flex flex-wrap items-center justify-between gap-3 px-5 py-4 text-white">
          <div className="flex items-center gap-3"><span className="grid h-11 w-11 place-items-center rounded-xl bg-white/90"><CropGlyph zoneId={z.zone_id} size={32} /></span>
            <div><div className="text-xs opacity-80">{z.zone_name} · {r.date} · {r.decision_time}</div><div className="font-display text-xl">{z.crop}</div></div></div>
          <div className="text-end"><ActionBadge action={r.decision.action} size="lg" /><div className="mt-1 text-xs opacity-85">{RULE_AR[r.decision.rule_code] ?? r.decision.rule_code}</div></div>
        </div>
        <div className="grid gap-5 p-5 sm:grid-cols-[170px_1fr]">
          <div className="mx-auto w-full max-w-[210px]">
            <SoilColumn pct current={r.inputs_used.before_VWC_pct as number | null} target={plan?.target_vwc_pct ?? z.field_capacity_pct}
              trigger={r.fao56.trigger_vwc_pct} predicted={m?.predicted_vwc_with_plan_pct ?? null} wilting={z.wilting_pct}
              max={Math.ceil(z.saturation_pct_assumed / 5) * 5} label="مقطع منطقة الجذور" compact />
          </div>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 2xl:grid-cols-4">
              <Kpi label="الرطوبة الحالية" value={pct(r.inputs_used.before_VWC_pct as number | null)} />
              <Kpi label="الهدف" value={pct(plan?.target_vwc_pct ?? z.field_capacity_pct, 1)} tone="leaf" />
              <Kpi label="المتوقعة بعد 6 ساعات" value={pct(m?.predicted_vwc_with_plan_pct)} tone="water" hint={m ? `دون ري: ${pct(m.predicted_vwc_no_irrigation_pct)}` : "النموذج غير متاح"} />
              <Kpi label="الكمية المقترحة" value={plan ? `${fmtL(plan.volume_l, 0)} ل` : "0 ل"} tone="water" hint={plan ? `${plan.duration_min.toFixed(1)} دقيقة بتدفق ${plan.flow_l_min} ل/د` : "لا ري"} />
            </div>
            <div>
              <h4 className="mb-1.5 text-sm font-semibold">لماذا هذا القرار؟</h4>
              <ol className="space-y-1.5 text-sm">{r.decision.reasons.map((t, i) => <li key={i} className="flex gap-2"><span className="num mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-water-pale text-[11px] font-bold text-water">{i + 1}</span><span>{t}</span></li>)}</ol>
            </div>
            {plan && <div className="rounded-lg border border-water/25 bg-water-pale/60 p-3 text-sm"><b className="text-water">حساب الكمية (FAO-56):</b> <span className="num">{plan.formula}</span>
              {plan.limits_applied.length > 0 && <div className="mt-1 text-ochre">قُيدت بالميزانية اليومية.</div>}</div>}
          </div>
        </div>
      </div>

      {m?.curve && (
        <div className="panel p-5">
          <h4 className="font-display text-base">استجابة الرطوبة للكمية — نموذج المحاصيل مقابل معادلة موازنة الماء</h4>
          <p className="mb-2 text-xs text-muted">كل نقطة تنبؤ فعلي من الخادم لنفس اليوم والمنطقة بكمية مختلفة. المنطقة المظللة = مدى الكميات في بيانات التدريب.</p>
          <ResponseCurve
            series={[{ name: "نموذج المحاصيل (ML)", color: "#1F7AA8", points: m.curve.map((c) => ({ x: c.volume_l, y: c.predicted_vwc_pct })) },
              { name: "موازنة الماء (معادلة)", color: "#8A6A45", dashed: true, points: m.curve.map((c) => ({ x: c.volume_l, y: c.water_balance_vwc_pct })) }]}
            refLines={[{ y: z.field_capacity_pct, label: `السعة الحقلية ${z.field_capacity_pct}%`, color: "#2F6B4F" },
              { y: r.fao56.trigger_vwc_pct, label: `عتبة الري ${r.fao56.trigger_vwc_pct.toFixed(1)}%`, color: "#B97A22", dashed: true }]}
            band={rng ? { from: rng[0], to: rng[1], label: "نطاق التدريب" } : undefined}
            markers={plan ? [{ x: plan.volume_l, y: m.predicted_vwc_with_plan_pct, label: "المقترح", color: "#13302A" }] : []} />
          <p className="mt-2 text-xs text-muted">{m.model_min_volume_for_target_l != null
            ? <>أقل كمية يتوقع النموذج أن تبلغ الهدف بعد 6 ساعات: <b className="num text-ink">{fmtL(m.model_min_volume_for_target_l, 0)} ل</b>.</>
            : m.model_min_volume_note}</p>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <div className="panel p-4 text-sm">
          <h4 className="mb-2 font-semibold">البيانات التي اعتمد عليها القرار</h4>
          <table className="tbl"><tbody>
            {[["المدخلات", `TAW ${r.fao56.taw_mm.toFixed(1)} مم · RAW ${r.fao56.raw_mm.toFixed(1)} مم · p ${r.fao56.p_adjusted.toFixed(2)}`],
              ["ETc المتوقع", `${r.fao56.etc_mm.toFixed(2)} مم = ET0 ${r.inputs_used.et0_forecast_24h_mm} × Kc ${z.kc_assumed}`],
              ["المطر المتوقع 24 س", `${r.fao56.rain_forecast_mm} مم`],
              ["حرارة / رطوبة جوية", `${r.inputs_used.air_temp_observed_C} °C · ${r.inputs_used.humidity_observed_pct}%`],
              ["قراءة الأمس / متوسط 7 أيام", `${pct(r.inputs_used.lag1_before_VWC_pct as number)} · ${pct(r.inputs_used.past7_before_mean_pct as number)}`],
              ["التربة", `FC ${z.field_capacity_pct}% · WP ${z.wilting_pct}% · جذور ${z.root_depth_m} م · كفاءة ${z.efficiency}`],
              ["مصدر p", z.p_source], ["سجل الملف", `${r.event_id} (جزء ${r.temporal_split})`]].map(([k, v]) => (
              <tr key={k}><td className="w-40 text-muted">{k}</td><td className="num-mixed">{v}</td></tr>))}
          </tbody></table>
          {Object.keys(r.changed_inputs).length > 0 && <p className="mt-2 text-xs text-water">غُيّرت المدخلات: {Object.entries(r.changed_inputs).map(([k, v]) => `${k}: ${v.from ?? "—"} → ${v.to ?? "مفقودة"}`).join("، ")}</p>}
        </div>
        <div className="panel p-4 text-sm">
          <h4 className="mb-2 font-semibold">للمقارنة: ما سجله الملف لنفس اليوم</h4>
          <table className="tbl"><tbody>
            <tr><td className="w-40 text-muted">خطة المولد</td><td><span className="num">{fmtL(r.recorded_in_file.planned_volume_l, 0)}</span> ل</td></tr>
            <tr><td className="text-muted">المنفذ</td><td><span className="num">{fmtL(r.recorded_in_file.actual_volume_l, 0)}</span> ل · {r.recorded_in_file.simulated_fault_label}</td></tr>
            <tr><td className="text-muted">الرطوبة المسجلة بعد 6 س</td><td>{pct(r.recorded_in_file.after_6h_vwc_pct)} <span className="text-xs text-muted">(بخطة المولد، لا بالكمية المقترحة)</span></td></tr>
          </tbody></table>
          <p className="mt-2 text-xs text-muted">{r.recorded_in_file.note}</p>
          <p className="mt-1 text-xs text-muted">{r.method_note}</p>
          {r.saved_id && <p className="mt-2 chip bg-[#E6F0EA] text-leaf">حُفظت في السجل #{r.saved_id}</p>}
        </div>
      </div>
      <Warnings items={r.warnings} />
    </div>
  );
}

export function Kpi({ label, value, hint, tone = "ink" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "ink" | "water" | "leaf" | "ochre" }) {
  const c = { ink: "text-ink", water: "text-water", leaf: "text-leaf", ochre: "text-ochre" }[tone];
  return (
    <div className="rounded-xl border border-line bg-white/70 p-3">
      <div className="text-[11px] text-muted">{label}</div>
      <div className={`num font-display text-xl ${c}`}>{value}</div>
      {hint && <div className="text-[11px] text-muted">{hint}</div>}
    </div>
  );
}
