// تحليل الصور الميدانية: يعرض مخرجات image_processing (رمادي، قناع أخضر، حواف، مؤشر الغطاء الأخضر) دون إعادة معالجة.
import { useState } from "react";
import { api, type ImageAnalysisItem } from "../services/api";
import { HBars } from "../components/charts";
import { ErrorBox, Loading, Panel, Tabs, useApi } from "../components/ui";

type View = "resized" | "green_mask" | "edges" | "gray";
const GROUP_AR: Record<string, string> = { rabigh_kaec: "مجلد «صور برابغ ومدينة الملك عبدالله»", unlabeled: "صور دون تحديد موقع" };

export default function ImageAnalysisPanel() {
  const { data, error, reload } = useApi(() => api.imageAnalysis(), []);
  const [view, setView] = useState<View>("green_mask");
  const [open, setOpen] = useState<ImageAnalysisItem | null>(null);
  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!data) return <Loading />;
  const s = data.summary as { processed?: number; images_found?: number; originals_unchanged?: boolean; heic_backend?: string };
  return (
    <Panel title="تحليل الصور الميدانية (معالجة الصور كمصفوفات NumPy)"
      subtitle={`${s.processed ?? 0} من ${s.images_found ?? 0} صورة · الأصول سليمة: ${s.originals_unchanged ? "نعم (بصمة SHA-256)" : "غير معروف"} · المصدر: ${data.source}`}
      actions={<Tabs value={view} onChange={setView} items={[["resized", "الصورة"], ["green_mask", "قناع الأخضر"], ["edges", "الحواف"], ["gray", "رمادي"]]} />}>
      <p className="mb-3 rounded-lg border border-ochre/40 bg-ochre-pale p-2 text-xs text-[#6d4a12]">{data.method_ar} الصور مرجع بصري ولم تُستخدم في تدريب أي نموذج، ولا تُنسب لمناطق المحاصيل.</p>
      <div className="grid gap-5 lg:grid-cols-[1fr_300px]">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
          {data.items.map((it) => (
            <button key={it.file} onClick={() => setOpen(it)} className="lift group overflow-hidden rounded-xl border border-line bg-white text-start">
              <div className="aspect-square bg-ink"><img src={it.images[view]} alt={`${it.id} — ${view}`} loading="lazy" className="h-full w-full object-contain" /></div>
              <div className="p-2 text-xs"><div className="flex justify-between"><b className="font-mono">{it.id.slice(0, 12)}</b><span className="num text-leaf">{it.green_cover_pct.toFixed(1)}%</span></div>
                <div className="mt-1 h-1.5 rounded bg-mist"><div className="h-full rounded bg-turf" style={{ width: `${it.green_cover_pct}%` }} /></div>
                <div className="mt-1 text-[10px] text-muted">{GROUP_AR[it.group] ?? it.group} · {it.format}</div></div>
            </button>))}
        </div>
        <div>
          <h4 className="mb-2 text-sm font-semibold">مؤشر الغطاء الأخضر لكل صورة</h4>
          <HBars format={(v) => `${v.toFixed(1)}%`} color="#7FA66A" items={[...data.items].sort((a, b) => b.green_cover_pct - a.green_cover_pct).map((i) => ({ label: i.id, value: i.green_cover_pct, note: i.file }))} />
        </div>
      </div>
      {open && (
        <div role="dialog" aria-modal="true" aria-label={open.id} className="fixed inset-0 z-50 grid place-items-center bg-ink/70 p-4" onClick={() => setOpen(null)}>
          <div className="max-h-[92vh] w-full max-w-5xl overflow-auto rounded-2xl bg-paper p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 flex items-center justify-between"><b className="font-mono">{open.file}</b><button className="btn btn-ghost py-1" onClick={() => setOpen(null)}>إغلاق ✕</button></div>
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">{(["resized", "green_mask", "edges", "gray"] as View[]).map((v) => (
              <figure key={v} className="m-0"><img src={open.images[v]} alt={v} className="w-full rounded-lg bg-ink object-contain" /><figcaption className="mt-1 text-center text-xs text-muted">{{ resized: "موحدة 512", green_mask: "قناع الأخضر", edges: "حواف Sobel", gray: "رمادي" }[v]}</figcaption></figure>))}</div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-sm md:grid-cols-5">
              {[["الأبعاد", `${open.width}×${open.height}`], ["الغطاء الأخضر", `${open.green_cover_pct.toFixed(2)}%`], ["السطوع", open.brightness.toFixed(1)], ["التباين", open.contrast.toFixed(1)], ["RGB متوسط", `${open.mean_r.toFixed(0)}/${open.mean_g.toFixed(0)}/${open.mean_b.toFixed(0)}`]].map(([k, v]) => (
                <div key={k} className="rounded-lg bg-mist p-2"><div className="text-[11px] text-muted">{k}</div><div className="num font-medium">{v}</div></div>))}
            </div>
            <p className="mt-2 text-xs text-muted">طريقة القراءة: {open.read_with}</p>
          </div>
        </div>)}
    </Panel>
  );
}
