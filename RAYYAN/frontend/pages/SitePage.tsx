import { useEffect, useState } from "react";
import { api, type GalleryItem } from "../services/api";
import { ARM_AR, ErrorBox, Loading, OriginTag, Panel, useApi, ZONE_AR } from "../components/ui";
import type { PageProps } from "./DecisionPage";

const ORIGIN_KIND: Record<string, "observed" | "reference" | "simulated" | "derived" | "missing"> = {
  observed: "observed", reference: "reference", simulated: "simulated", derived: "derived", missing_field: "missing",
};

function Lightbox({ items, index, onClose, onMove }: { items: GalleryItem[]; index: number; onClose: () => void; onMove: (d: number) => void }) {
  const it = items[index];
  useEffect(() => {
    const k = (e: { key: string }) => { if (e.key === "Escape") onClose(); if (e.key === "ArrowLeft") onMove(1); if (e.key === "ArrowRight") onMove(-1); };
    window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k);
  }, [index]);
  return (
    <div role="dialog" aria-modal="true" aria-label={`صورة ${it.id}`} className="fixed inset-0 z-50 flex flex-col bg-[#0d1f1a]/95 p-3 text-white" onClick={onClose}>
      <div className="flex items-center justify-between gap-3 text-sm" onClick={(e) => e.stopPropagation()}>
        <span>{it.group_label} · <span className="font-mono">{it.id}</span> · <span className="num">{it.width}×{it.height}</span>{it.converted_from_heic && " · نسخة JPEG محولة من HEIC"}</span>
        <span className="flex gap-2">
          <a className="btn border-white/30 py-1 text-white" href={`/media/${it.display_original}`} target="_blank" rel="noreferrer">الدقة الأصلية ↗</a>
          <button className="btn border-white/30 py-1 text-white" onClick={onClose}>إغلاق</button>
        </span>
      </div>
      <div className="relative flex min-h-0 flex-1 items-center justify-center" onClick={(e) => e.stopPropagation()}>
        <button className="absolute right-1 z-10 rounded-full bg-white/15 px-3 py-2 text-xl" onClick={() => onMove(-1)} aria-label="السابقة">›</button>
        <img src={`/media/${it.web}`} alt={`${it.group_label} — ${it.id}`} className="max-h-full max-w-full object-contain" />
        <button className="absolute left-1 z-10 rounded-full bg-white/15 px-3 py-2 text-xl" onClick={() => onMove(1)} aria-label="التالية">‹</button>
      </div>
      <p className="text-center text-xs text-white/70" onClick={(e) => e.stopPropagation()}>{it.group_note} الصور مرجع بصري ولم تُستخدم في تدريب أي نموذج.</p>
    </div>
  );
}

export default function SitePage(_: PageProps) {
  const s = useApi(() => api.site(), []);
  const g = useApi(() => api.gallery(), []);
  const [open, setOpen] = useState<number | null>(null);
  if (s.error) return <ErrorBox message={s.error} onRetry={s.reload} />;
  if (!s.data) return <Loading />;
  const d = s.data, imgs = g.data?.items ?? [];
  const groups = [...new Set(imgs.map((i) => i.group))];
  return (
    <div className="space-y-5">
      <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
        <Panel title="الموقع" actions={<OriginTag kind="simulated" />}>
          <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
            <dt className="text-muted">الاسم</dt><dd className="m-0">{String(d.site.site_name)}</dd>
            <dt className="text-muted">النبات</dt><dd className="m-0">ثيل البرمودا <span className="font-mono">Cynodon dactylon</span> — الصنف غير محدد</dd>
            <dt className="text-muted">نقطة الطقس</dt><dd className="m-0"><span className="num">{String(d.site.weather_request_latitude)}N، {String(d.site.weather_request_longitude)}E</span> — نقطة تمثيلية للرياض، ليست قطعة ممسوحة</dd>
            <dt className="text-muted">المنطقة الزمنية</dt><dd className="m-0 font-mono">{String(d.site.timezone)}</dd>
            <dt className="text-muted">الفترة</dt><dd className="m-0 num">2024-01-01 — 2025-12-31</dd>
          </dl>
          <p className="mt-3 rounded-lg bg-mist p-2 text-xs text-muted">الموقع المقترح في تقرير المشروع: حديقة الملك سلمان. لا يوجد ادعاء بموافقة تنفيذ أو أجهزة مركبة.</p>
        </Panel>
        <Panel title="المنطقتان وخصائص التربة المفترضة" subtitle="من zone_profiles — افتراضات محاكاة وليست قياسًا ميدانيًا">
          <div className="overflow-x-auto"><table className="tbl min-w-[560px]">
            <thead><tr><th>الخاصية</th>{d.zones.map((z) => <th key={String(z.zone_id)}>{ZONE_AR[String(z.zone_id)]}</th>)}</tr></thead>
            <tbody>
              {([["ذراع المقارنة", "trial_arm"], ["المساحة م²", "area_m2"], ["طريقة الري", "irrigation_method"], ["قوام التربة", "soil_texture"], ["عمق الجذور م", "root_depth_m"],
                ["السعة الحقلية", "field_capacity_vwc"], ["نقطة الذبول", "wilting_point_vwc"], ["التشبع", "saturation_vwc"], ["نسبة الاستنزاف p", "depletion_fraction"],
                ["كفاءة الري", "application_efficiency"], ["التدفق الاسمي ل/د", "nominal_flow_l_min"], ["زمن الاستجابة د", "response_lag_min"], ["أساس المعاملات", "parameter_basis"]] as [string, string][]).map(([l, k]) => (
                <tr key={k}><td>{l}</td>{d.zones.map((z) => <td key={String(z.zone_id)} className={typeof z[k] === "number" ? "num" : "text-xs"}>{k === "trial_arm" ? ARM_AR[String(z[k])] : String(z[k])}</td>)}</tr>
              ))}
            </tbody>
          </table></div>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="الأجهزة في نموذج المحاكاة" subtitle="كلها افتراضية وغير مركبة (virtual_not_installed)">
          <table className="tbl"><thead><tr><th>الجهاز</th><th>النوع</th><th>المنطقة</th><th>العمق</th><th>الحالة</th></tr></thead><tbody>
            {d.devices.map((x) => <tr key={String(x.device_id)}><td className="font-mono">{String(x.device_id)}</td><td>{String(x.device_type_ar)}</td><td>{ZONE_AR[String(x.zone_id)]}</td>
              <td className="num">{x.depth_m == null ? "—" : `${x.depth_m} م`}</td><td><span className="chip bg-danger-pale text-danger">غير مركب</span></td></tr>)}
          </tbody></table>
          <p className="mt-2 text-xs text-muted">التقرير يخطط لـ ESP32 وحساسات رطوبة وتدفق وTDS وحرارة وصمام؛ لم يُركب أي منها، ولا يرسل النظام أوامر تشغيل.</p>
        </Panel>
        <Panel title="معاملات الدراسة المرجعية" subtitle="Saeed 2018 — جامعة الملك سعود؛ مرجع وليست حدود الموقع" actions={<OriginTag kind="reference" />}>
          <div className="max-h-72 overflow-auto"><table className="tbl"><thead><tr><th>المعامل</th><th>القيمة</th><th>الأصل</th></tr></thead><tbody>
            {d.study_parameters.map((p) => <tr key={String(p.parameter_id)}><td className="font-mono text-xs">{String(p.parameter_id)}</td><td className="num">{p.value_numeric ?? "—"} <span className="text-xs text-muted">{String(p.unit ?? "")}</span></td><td className="text-xs">{String(p.value_origin)}</td></tr>)}
          </tbody></table></div>
        </Panel>
      </div>

      <Panel title="أصل البيانات" subtitle="تصنيف كل جدول في قاعدة البيانات وفق table_catalog — للفصل بين المرصود والمرجعي والمحاكى والمشتق والناقص">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {d.provenance.map((p) => (
            <div key={p.key} className="rounded-lg border border-line p-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-base font-medium">{p.label_ar}</h3>
                {ORIGIN_KIND[p.key] && <OriginTag kind={ORIGIN_KIND[p.key]} />}
              </div>
              <p className="text-xs text-muted">{p.description_ar}</p>
              <ul className="mt-2 space-y-0.5 text-xs">
                {p.tables.map((t) => <li key={t.table} title={t.grain_ar} className="flex justify-between gap-2"><span className="font-mono">{t.table}</span><span className="num text-muted">{t.rows.toLocaleString("en")}</span></li>)}
              </ul>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="بيانات ميدانية ناقصة" subtitle="ما يلزم جمعه قبل أي ادعاء بأداء حقيقي (field_collection_plan)" actions={<OriginTag kind="missing" />}>
        <div className="overflow-x-auto"><table className="tbl min-w-[700px]"><thead><tr><th>#</th><th>المجموعة</th><th>طريقة الجمع</th><th>المسؤول</th><th>الغرض</th></tr></thead><tbody>
          {d.field_data_gaps.map((x) => <tr key={String(x.priority)}><td className="num">{String(x.priority)}</td><td>{String(x.data_group_ar)}</td><td className="text-xs">{String(x.collection_method_ar)}</td><td className="text-xs">{String(x.responsible_ar)}</td><td className="text-xs">{String(x.purpose_ar)}</td></tr>)}
        </tbody></table></div>
      </Panel>

      <Panel title="الصور الميدانية" subtitle={`${imgs.length} صورة من الملف المرفق، بنسبها الأصلية. صور HEIC عُرضت عبر نسخة JPEG محولة مع بقاء الأصل.`}>
        {g.error && <ErrorBox message={g.error} />}
        {groups.map((grp) => {
          const items = imgs.filter((i) => i.group === grp);
          return (
            <section key={grp} className="mb-5">
              <h3 className="text-base font-medium">{items[0].group_label}</h3>
              <p className="mb-2 text-xs text-muted">{items[0].group_note}</p>
              <div className="columns-2 gap-3 sm:columns-3 lg:columns-4">
                {items.map((it) => (
                  <button key={it.id} onClick={() => setOpen(imgs.indexOf(it))} className="group mb-3 block w-full break-inside-avoid overflow-hidden rounded-lg border border-line bg-white text-start">
                    <img src={`/media/${it.thumb}`} alt={`${it.group_label} — ${it.id}`} loading="lazy" width={it.width} height={it.height}
                      className="block h-auto w-full transition-transform duration-300 group-hover:scale-[1.02]" />
                    <span className="flex justify-between px-2 py-1 text-[11px] text-muted"><span className="font-mono">{it.id}</span><span>{it.original_format}{it.converted_from_heic ? " → JPEG" : ""}</span></span>
                  </button>
                ))}
              </div>
            </section>
          );
        })}
      </Panel>
      {open !== null && <Lightbox items={imgs} index={open} onClose={() => setOpen(null)} onMove={(dd) => setOpen((open + dd + imgs.length) % imgs.length)} />}
    </div>
  );
}
