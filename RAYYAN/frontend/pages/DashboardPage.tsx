import { useState } from "react";
import { api, type DashboardZone } from "../services/api";
import SoilColumn from "../components/SoilColumn";
import { GroupedBars, LineChart, PALETTE } from "../components/charts";
import type { PageProps } from "./DecisionPage";
import { ActionBadge, ARM_AR, ErrorBox, fmt, fmtL, fmtTime, Loading, OriginTag, Panel, Stat, useApi, ZONE_AR } from "../components/ui";

function ZoneCard({ z }: { z: DashboardZone }) {
  const r = z.recommendation, d = r.decision, wp = r.water_plan, pr = r.prediction;
  const cur = (r.inputs?.pre_vwc as number | null) ?? null;
  return (
    <section className="panel overflow-hidden" aria-labelledby={`zt-${z.zone_id}`}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-[#F4F8F5] px-4 py-3">
        <div>
          <h2 id={`zt-${z.zone_id}`} className="text-lg font-medium">{ZONE_AR[z.zone_id]} <span className="font-mono text-sm text-muted">{z.zone_id}</span></h2>
          <p className="text-xs text-muted">{z.area_m2} م² · {ARM_AR[z.trial_arm]} في المحاكاة</p>
        </div>
        <ActionBadge action={d.action} size="lg" />
      </header>
      <div className="grid gap-4 p-4 sm:grid-cols-[150px_1fr]">
        <div className="mx-auto w-[150px] sm:mx-0">
          <SoilColumn current={cur} target={d.thresholds.target_vwc} trigger={d.thresholds.trigger_vwc} wilting={z.wilting_point_vwc}
            predicted={pr?.available ? pr.post_vwc ?? null : null} compact />
        </div>
        <div className="min-w-0 space-y-3">
          <div className="grid grid-cols-3 gap-3">
            <Stat label="الرطوبة وقت القرار" value={fmt(cur)} unit="m³/m³" tone="water" hint={(r.inputs?.decision_time_local as string)?.replace("T", " ")} />
            <Stat label="الهدف (السعة الحقلية)" value={fmt(d.thresholds.target_vwc)} tone="leaf" />
            <Stat label="المتوقعة بعد الري" value={pr?.available ? fmt(pr.post_vwc) : "—"} tone="water" hint={pr?.available ? "تنبؤ النموذج" : "لا رية مقترحة"} />
          </div>
          <p className="text-sm leading-relaxed">{d.reasons[0]?.text_ar}</p>
          <div className="grid grid-cols-2 gap-3 rounded-lg bg-mist/70 p-3">
            <Stat label="الكمية المقترحة" value={wp ? fmtL(wp.volume_l, 0) : "0"} unit="لتر" hint={wp ? `${wp.duration_min} دقيقة تشغيل` : undefined} />
            <Stat label="قرار المحاكي لنفس اليوم" value={r.stored_decision ? r.stored_decision.planned_volume_l : "—"} unit={r.stored_decision ? "لتر" : undefined}
              hint={r.agreement?.comparable ? (r.agreement.action_match && r.agreement.volume_match ? "مطابق لقواعد ريّان" : "مختلف") : "جدول تقليدي — للمقارنة"} />
          </div>
          {z.last_irrigation && (
            <div className="text-sm">
              <span className="text-muted">آخر رية: </span>
              <span className="num">{fmtTime(z.last_irrigation.started_local)}</span> — مخطط <span className="num">{z.last_irrigation.planned_volume_l}</span> ل،
              منفذ <span className="num">{fmtL(z.last_irrigation.delivered_volume_l)}</span> ل · {z.last_irrigation.status_ar}
            </div>
          )}
          <div className="flex flex-wrap gap-4 text-sm">
            <span><span className="text-muted">استهلاك 30 يومًا: </span><b className="num">{fmtL(z.water_30d.delivered, 0)}</b> ل ({z.water_30d.n} رية)</span>
            <span><span className="text-muted">منذ بداية المحاكاة: </span><b className="num">{fmtL(z.water_to_date.delivered, 0)}</b> ل</span>
          </div>
          <a className="text-sm text-water" href={`#/decision/${r.stored_decision?.decision_id ?? ""}`}>عرض أسباب القرار كاملة ←</a>
        </div>
      </div>
    </section>
  );
}

export default function DashboardPage(_: PageProps) {
  const [day, setDay] = useState<string>("");
  const { data, error, loading, reload } = useApi(() => api.dashboard(day || undefined), [day]);
  const usage = useApi(() => api.waterUsage(), []);
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const shift = (n: number) => {
    const d = new Date(data.date + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n);
    const iso = d.toISOString().slice(0, 10);
    if (iso >= data.data_range.first_date && iso <= data.data_range.last_date) setDay(iso);
  };
  const [z1, z2] = data.zones;
  const trendDates = z1.moisture_trend_30d.map((p) => new Date(p.d + "T00:00:00"));
  return (
    <div className="space-y-5">
      <div className="panel flex flex-wrap items-center gap-x-6 gap-y-3 p-4">
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${data.system.model_loaded ? "bg-turf" : "bg-danger"}`} aria-hidden="true" />
          <div>
            <div className="text-sm font-medium">{data.system.mode_ar}</div>
            <div className="text-xs text-muted">النموذج <span className="font-mono">{data.system.model_version}</span> · الصمامات: معطلة (لا أجهزة)</div>
          </div>
        </div>
        <div className="ms-auto flex flex-wrap items-center gap-2" role="group" aria-label="اختيار يوم من المحاكاة">
          <span className="text-sm text-muted">يوم المحاكاة</span>
          <button className="btn btn-ghost px-2 py-1" onClick={() => shift(-1)} aria-label="اليوم السابق">→</button>
          <input type="date" className="field field-num w-40 py-1" value={data.date} min={data.data_range.first_date} max={data.data_range.last_date}
            onChange={(e) => e.target.value && setDay(e.target.value)} aria-label="التاريخ" />
          <button className="btn btn-ghost px-2 py-1" onClick={() => shift(1)} aria-label="اليوم التالي">←</button>
          {loading && <span className="text-xs text-muted">يُحدّث…</span>}
        </div>
        <div className="flex w-full flex-wrap gap-x-6 gap-y-1 text-xs text-muted">
          <span>نطاق البيانات: <span className="num">{data.data_range.first_date} — {data.data_range.last_date}</span></span>
          <span>ميزانية الموقع اليوم: <b className="num">{data.system.daily_budget_l ?? "—"}</b> لتر</span>
          <span>{data.system.counts.decisions.toLocaleString("en")} قرار · {data.system.counts.events} رية · {data.system.counts.samples.toLocaleString("en")} قراءة</span>
          <OriginTag kind="simulated" />
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">{data.zones.map((z) => <ZoneCard key={z.zone_id} z={z} />)}</div>

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <Panel title="رطوبة التربة — آخر 30 يومًا" subtitle="متوسط يومي لقراءات حساس المحاكاة لكل منطقة">
          <LineChart yLabel="m³/m³" series={[
            { name: ZONE_AR.Z01, color: PALETTE.ochre, points: z1.moisture_trend_30d.map((p, i) => ({ x: trendDates[i], y: p.v })) },
            { name: ZONE_AR.Z02, color: PALETTE.water, points: z2.moisture_trend_30d.map((p) => ({ x: new Date(p.d + "T00:00:00"), y: p.v })) },
          ]} refLines={[{ y: z2.recommendation.decision.thresholds.target_vwc, label: "الهدف", color: PALETTE.leaf },
            { y: z2.recommendation.decision.thresholds.base_trigger_vwc, label: "عتبة الأساس", color: PALETTE.ochre, dashed: true }]} />
        </Panel>
        <Panel title="تنبيهات المراقبة" subtitle="قواعد التدفق والموازنة والحساس حتى هذا اليوم">
          {data.alerts.length === 0 ? <p className="text-sm text-muted">لا تنبيهات حتى هذا التاريخ.</p> : (
            <ul className="divide-y divide-line">
              {data.alerts.map((a) => (
                <li key={a.alert_id} className="py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <b className={a.alert_type === "no_flow" ? "text-danger" : "text-ochre"}>{a.label_ar}</b>
                    <span className="num text-xs text-muted">{fmtTime(a.detected_local)}</span>
                  </div>
                  <div className="text-xs text-muted">
                    {a.zone_id ? ZONE_AR[a.zone_id] : "الموقع"}{a.event_id && <> · <a className="text-water" href={`#/history/D${a.event_id.slice(1)}`}>{a.event_id}</a></>}
                    {a.confirmed_cause && <> · سبب المحاكي: {a.confirmed_cause}</>}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-muted">التنبيه لا يؤكد تسربًا أو عطلًا قبل الفحص الميداني.</p>
        </Panel>
      </div>

      <Panel title="استهلاك المياه: المخطط مقابل المنفذ" subtitle="شهريًا لكل منطقة طوال فترة المحاكاة">
        {usage.error && <ErrorBox message={usage.error} />}
        {usage.data && (() => {
          const months = [...new Set(usage.data.monthly.map((m) => m.month))];
          const val = (z: string, k: "planned_l" | "delivered_l") => months.map((m) => usage.data!.monthly.find((x) => x.month === m && x.zone_id === z)?.[k] ?? 0);
          return (
            <>
              <GroupedBars categories={months.map((m) => m.slice(2).replace("-", "/"))} yLabel="لتر" highlight={data.date.slice(2, 7).replace("-", "/")}
                yFormat={(v) => v.toLocaleString("en", { maximumFractionDigits: 0 })} series={[
                  { name: `${ZONE_AR.Z01} منفذ`, color: PALETTE.ochre, values: val("Z01", "delivered_l") },
                  { name: `${ZONE_AR.Z02} منفذ`, color: PALETTE.water, values: val("Z02", "delivered_l") },
                ]} />
              <div className="mt-3 grid gap-3 md:grid-cols-[1fr_1fr_1.4fr]">
                {usage.data.totals.map((t) => {
                  const st = usage.data!.simulated_stress_hours.find((s) => s.zone_id === t.zone_id);
                  return (
                    <div key={t.zone_id} className="rounded-lg border border-line p-3">
                      <div className="text-sm font-medium">{ZONE_AR[t.zone_id]} — {ARM_AR[t.trial_arm]}</div>
                      <div className="mt-1 text-sm">منفذ <b className="num">{fmtL(t.delivered_l, 0)}</b> ل من مخطط <span className="num">{fmtL(t.planned_l, 0)}</span> ل في {t.events} رية</div>
                      <div className="text-xs text-muted">ساعات إجهاد في المحاكي: <span className="num">{fmtL(st?.stress_hours ?? null, 0)}</span></div>
                    </div>
                  );
                })}
                <p className="rounded-lg bg-ochre-pale p-3 text-sm text-[#6d4a12]">{usage.data.interpretation_ar}</p>
              </div>
            </>
          );
        })()}
      </Panel>
    </div>
  );
}
