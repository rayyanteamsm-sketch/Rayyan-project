import { useEffect, useState } from "react";
import { api, type HistoryDetail, type HistoryItem } from "../services/api";
import { FlowChart } from "../components/charts";
import { ActionBadge, ErrorBox, fmt, fmtL, fmtTime, Loading, Panel, useApi, ZONE_AR } from "../components/ui";
import type { PageProps } from "./DecisionPage";

interface Filters { source: string; zone_id: string; action: string; status: string; date_from: string; date_to: string; search: string }
const EMPTY: Filters = { source: "all", zone_id: "", action: "", status: "", date_from: "", date_to: "", search: "" };
const PAGE = 25;
const STATUS_OPTIONS: [string, string][] = [["", "كل الحالات"], ["completed", "مكتملة"], ["not_executed", "لا تنفيذ"], ["no_flow", "لم يصل الماء"],
  ["low_flow", "تدفق منخفض"], ["stuck_open", "صمام لم يغلق"], ["label_missing", "نتيجة ناقصة"], ["app_only", "توصية فقط"]];

function Detail({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, error } = useApi(() => api.historyDetail(id), [id]);
  return (
    <aside role="dialog" aria-modal="true" aria-label={`تفاصيل ${id}`} className="fixed inset-0 z-40 flex justify-start bg-ink/30" onClick={onClose}>
      <div className="h-full w-full max-w-2xl overflow-y-auto bg-paper p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xl font-medium">تفاصيل العملية <span className="font-mono text-base">{id}</span></h2>
          <button className="btn btn-ghost py-1" onClick={onClose}>إغلاق</button>
        </div>
        {error && <ErrorBox message={error} />}
        {!data ? <Loading /> : <DetailBody d={data} />}
      </div>
    </aside>
  );
}

function DetailBody({ d }: { d: HistoryDetail }) {
  const v = (k: string) => d[k] as number | string | null;
  const f = d.flow;
  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center gap-2"><ActionBadge action={d.action} /><span className="num">{fmtTime(d.time_local)}</span><span>· {ZONE_AR[String(v("zone_id"))]}</span><span className="chip bg-mist">{d.status_ar}</span></div>
      <table className="tbl"><tbody>
        <tr><td>سبب القرار في المحاكي</td><td className="font-mono text-xs">{String(v("reason"))}</td></tr>
        <tr><td>طريقة القرار</td><td className="font-mono text-xs">{String(v("method_version"))}</td></tr>
        <tr><td>المخطط</td><td className="num">{fmtL(v("planned_volume_l") as number)} ل / {String(v("planned_duration_min"))} د</td></tr>
        <tr><td>المنفذ (عداد المحاكاة)</td><td className="num">{v("delivered_volume_l") == null ? "—" : `${fmtL(v("delivered_volume_l") as number, 2)} ل`}</td></tr>
        <tr><td>الرطوبة قبل / بعد</td><td className="num">{fmt(v("pre_vwc") as number)} ← {fmt(v("post_vwc") as number)}</td></tr>
        <tr><td>Δ الفعلي في المحاكاة</td><td className="num">{fmt(v("delta_vwc") as number, 4)}</td></tr>
        <tr><td>Δ تنبؤ النموذج</td><td className="num">{fmt(v("ml_predicted_delta") as number, 4)} <span className="text-xs text-muted">({String(v("ml_split") ?? "—")}{v("ml_out_of_sample") ? "، خارج العينة" : v("ml_split") ? "، داخل العينة" : ""})</span></td></tr>
        <tr><td>Δ المعادلة الخطية وقت القرار</td><td className="num">{fmt((d as Record<string, unknown>)["predicted_delta_vwc"] as number ?? null, 4)}</td></tr>
        <tr><td>علامات الإرباك</td><td className="text-xs">{String(v("confounding_flags") ?? "—")}</td></tr>
      </tbody></table>
      {f && (
        <Panel title="مراقبة التدفق" subtitle={`أول 5 دقائق: ${fmt(f.first5_avg_flow_l_min, 2)} ل/د من ${f.nominal_flow_l_min} اسمي · الانحراف ${fmtL(f.deviation_l, 2)} ل`}>
          <FlowChart series={f.series} nominal={f.nominal_flow_l_min} plannedEnd={f.planned_end_local} />
          {f.detected_alerts.length > 0 ? <ul className="mt-2 text-danger">{f.detected_alerts.map((a) => <li key={a.type}>⚠ {a.label_ar} — <span className="num">{a.value.toFixed(2)}</span> ل/د</li>)}</ul>
            : <p className="mt-2 text-leaf">لا تنبيهات تدفق لهذه الرية.</p>}
          <p className="mt-1 text-xs text-muted">{f.note}</p>
        </Panel>
      )}
      <a className="text-water" href={`#/decision/${d.decision_id}`}>إعادة تشغيل هذا القرار في محرك ريّان ←</a>
    </div>
  );
}

export default function HistoryPage({ param }: PageProps) {
  const [f, setF] = useState<Filters>(EMPTY);
  const [applied, setApplied] = useState<Filters>(EMPTY);
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(param ?? null);
  useEffect(() => { if (param) setOpen(param); }, [param]);
  const { data, error, loading, reload } = useApi(() => api.history({ ...applied, limit: PAGE, offset: page * PAGE }), [applied, page]);
  const set = (k: keyof Filters) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const apply = (nf = f) => { setPage(0); setApplied(nf); };
  const pages = data ? Math.ceil(data.total / PAGE) : 0;
  const close = () => { setOpen(null); if (window.location.hash.startsWith("#/history/")) window.location.hash = "/history"; };
  const row = (i: HistoryItem) => (
    <tr key={i.source + i.id} className="cursor-pointer" onClick={() => i.decision_id && setOpen(i.decision_id)} tabIndex={0}
      onKeyDown={(e: { key: string }) => e.key === "Enter" && i.decision_id && setOpen(i.decision_id)}>
      <td className="num whitespace-nowrap">{fmtTime(i.time_local)}</td>
      <td className="whitespace-nowrap">{ZONE_AR[i.zone_id]}</td>
      <td className="num">{fmt(i.pre_vwc)}</td>
      <td><ActionBadge action={i.action} /></td>
      <td className="num">{fmtL(i.planned_volume_l, 0)}</td>
      <td className="num">{i.delivered_volume_l == null ? "—" : fmtL(i.delivered_volume_l, 1)}</td>
      <td className="num">{fmt(i.post_vwc)}{i.post_is_prediction && <span className="text-[10px] text-water"> (تنبؤ)</span>}</td>
      <td><span className={`chip ${["no_flow", "low_flow", "stuck_open", "label_missing"].includes(i.status) ? "bg-danger-pale text-danger" : i.status === "app_only" ? "bg-water-pale text-water" : "bg-mist text-muted"}`}>{i.status_ar}</span>
        {i.alerts.length > 0 && <div className="text-[11px] text-danger">{i.alerts.join("، ")}</div>}</td>
      <td className="text-xs text-muted">{i.source_ar}<div className="font-mono">{i.id}</div></td>
    </tr>
  );
  return (
    <div className="space-y-5">
      <Panel title="البحث والتصفية">
        <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8" onSubmit={(e) => { e.preventDefault(); apply(); }}>
          <label className="text-sm xl:col-span-2"><span className="mb-1 block font-medium">بحث بالمعرّف</span><input className="field field-num font-mono" placeholder="D2025… أو E2024…" value={f.search} onChange={set("search")} /></label>
          <label className="text-sm"><span className="mb-1 block font-medium">المصدر</span><select className="field" value={f.source} onChange={set("source")}><option value="all">الكل</option><option value="simulation">سجل المحاكاة</option><option value="app">توصيات التطبيق</option></select></label>
          <label className="text-sm"><span className="mb-1 block font-medium">المنطقة</span><select className="field" value={f.zone_id} onChange={set("zone_id")}><option value="">الكل</option><option value="Z01">{ZONE_AR.Z01}</option><option value="Z02">{ZONE_AR.Z02}</option></select></label>
          <label className="text-sm"><span className="mb-1 block font-medium">نوع القرار</span><select className="field" value={f.action} onChange={set("action")}><option value="">الكل</option><option value="IRRIGATE">ري</option><option value="DEFER">تأجيل</option><option value="CHECK_SENSOR">فحص الحساس</option></select></label>
          <label className="text-sm"><span className="mb-1 block font-medium">الحالة</span><select className="field" value={f.status} onChange={set("status")}>{STATUS_OPTIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <label className="text-sm"><span className="mb-1 block font-medium">من</span><input type="date" className="field field-num" value={f.date_from} onChange={set("date_from")} /></label>
          <label className="text-sm"><span className="mb-1 block font-medium">إلى</span><input type="date" className="field field-num" value={f.date_to} onChange={set("date_to")} /></label>
          <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-4 xl:col-span-8">
            <button className="btn btn-primary">تطبيق</button>
            <button type="button" className="btn btn-ghost" onClick={() => { setF(EMPTY); apply(EMPTY); }}>مسح</button>
            {data && <span className="ms-auto text-sm text-muted"><b className="num">{data.total.toLocaleString("en")}</b> عملية · ري <span className="num">{data.counts_by_action.IRRIGATE}</span> · تأجيل <span className="num">{data.counts_by_action.DEFER}</span> · فحص <span className="num">{data.counts_by_action.CHECK_SENSOR}</span></span>}
          </div>
        </form>
      </Panel>
      {error && <ErrorBox message={error} onRetry={reload} />}
      <Panel>
        {!data ? <Loading /> : data.items.length === 0 ? <p className="p-4 text-muted">لا توجد عمليات تطابق التصفية. جرّبي توسيع نطاق التاريخ أو مسح البحث.</p> : (
          <>
            <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`}>
              <table className="tbl min-w-[980px]">
                <thead><tr><th>التاريخ والوقت</th><th>المنطقة</th><th>الرطوبة قبل</th><th>القرار</th><th>المخطط (ل)</th><th>المنفذ في المحاكاة (ل)</th><th>الرطوبة بعد</th><th>الحالة</th><th>المصدر</th></tr></thead>
                <tbody>{data.items.map(row)}</tbody>
              </table>
            </div>
            <nav className="mt-3 flex items-center justify-between text-sm" aria-label="الصفحات">
              <button className="btn btn-ghost py-1" disabled={page === 0} onClick={() => setPage(page - 1)}>السابق</button>
              <span>صفحة <span className="num">{page + 1}</span> من <span className="num">{pages}</span></span>
              <button className="btn btn-ghost py-1" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>التالي</button>
            </nav>
          </>
        )}
      </Panel>
      <p className="text-xs text-muted">سجل المحاكاة يربط decisions ← irrigation_events ← event_outcomes بالمعرفات decision_id وevent_id وzone_id. «الرطوبة بعد» في توصيات التطبيق تنبؤ نموذج وليست قياسًا.</p>
      {open && <Detail id={open} onClose={close} />}
    </div>
  );
}
