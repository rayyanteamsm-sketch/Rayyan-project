import { useEffect, useState, type ReactNode } from "react";
import type { Action } from "../services/api";

export const DATA_NOTICE = "تعتمد نتائج النموذج الحالية على بيانات محاكاة، ولا تمثل دقة مثبتة في بيئة زراعية حقيقية.";
export const ZONE_AR: Record<string, string> = { Z01: "المنطقة الأولى", Z02: "المنطقة الثانية" };
export const ARM_AR: Record<string, string> = { conventional: "جدول تقليدي ثابت", rayyan: "قواعد ريّان" };

export const fmt = (v: number | null | undefined, d = 3) => (v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(d));
export const fmtL = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : v.toLocaleString("ar-SA-u-nu-latn", { maximumFractionDigits: d }));
export const fmtDate = (iso: string) => iso.slice(0, 10);
export const fmtTime = (iso: string) => iso.replace("T", " ").slice(0, 16);

/** جلب بيانات من الخادم مع حالة تحميل وخطأ. */
export function useApi<T>(fn: () => Promise<T>, deps: readonly unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true); setError(null);
    fn().then((d) => { if (alive) setData(d); })
      .catch((e: Error) => { if (alive) setError(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1) };
}

const ACTION_STYLE: Record<Action, string> = {
  IRRIGATE: "bg-water-pale text-water border-water/30",
  DEFER: "bg-[#E6F0EA] text-leaf-dark border-leaf/30",
  CHECK_SENSOR: "bg-ochre-pale text-ochre border-ochre/40",
};
export const ACTION_AR: Record<Action, string> = { IRRIGATE: "ري", DEFER: "تأجيل", CHECK_SENSOR: "فحص الحساس" };

export function ActionBadge({ action, size = "sm" }: { action: Action; size?: "sm" | "lg" }) {
  return (
    <span className={`chip border ${ACTION_STYLE[action]} ${size === "lg" ? "text-base px-3 py-1" : ""}`}>
      <span className="font-mono text-[.7em] opacity-70">{action}</span>{ACTION_AR[action]}
    </span>
  );
}

export function Panel({ title, subtitle, actions, children, className = "" }: { title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel p-4 md:p-5 ${className}`}>
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title && <h2 className="text-lg font-medium text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, unit, hint, tone = "ink" }: { label: string; value: ReactNode; unit?: string; hint?: ReactNode; tone?: "ink" | "water" | "leaf" | "ochre" }) {
  const c = { ink: "text-ink", water: "text-water", leaf: "text-leaf", ochre: "text-ochre" }[tone];
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className={`font-display text-2xl font-medium ${c}`}><span className="num">{value}</span>{unit && <span className="ms-1 text-sm text-muted">{unit}</span>}</div>
      {hint && <div className="text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function Loading({ label = "جارٍ التحميل…" }: { label?: string }) {
  return <div role="status" className="flex items-center gap-2 p-6 text-muted"><span className="h-3 w-3 animate-pulse rounded-full bg-water" />{label}</div>;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-danger/40 bg-danger-pale p-3 text-sm text-danger">
      <b>تعذر إكمال الطلب:</b> {message}
      {onRetry && <button className="btn btn-ghost ms-3 py-1 text-xs" onClick={onRetry}>إعادة المحاولة</button>}
    </div>
  );
}

export function Warnings({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <ul className="space-y-1 rounded-lg border border-ochre/40 bg-ochre-pale p-3 text-sm text-[#7a5212]">
      {items.map((w, i) => <li key={i}>⚠ {w}</li>)}
    </ul>
  );
}

export function OriginTag({ kind }: { kind: "simulated" | "derived" | "reference" | "observed" | "model" | "missing" }) {
  const m = {
    simulated: ["بيانات محاكاة", "bg-[#EEE8DF] text-soil"], derived: ["مشتقة من المحاكاة", "bg-[#EAEFF3] text-[#4a6274]"],
    reference: ["مرجعية", "bg-[#E8EEF6] text-[#3f5a86]"], observed: ["مرصودة منشورة", "bg-[#E6F0EA] text-leaf"],
    model: ["مخرج نموذج", "bg-water-pale text-water"], missing: ["بيانات ميدانية ناقصة", "bg-danger-pale text-danger"],
  }[kind];
  return <span className={`chip ${m[1]}`}>{m[0]}</span>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}{hint && <span className="ms-1 text-xs font-normal text-muted">{hint}</span>}</span>
      {children}
    </label>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: [T, string][] }) {
  return (
    <div role="tablist" className="inline-flex overflow-hidden rounded-lg border border-line bg-white text-sm">
      {items.map(([k, label]) => (
        <button key={k} role="tab" aria-selected={value === k} onClick={() => onChange(k)}
          className={`px-3 py-1.5 ${value === k ? "bg-leaf text-white" : "hover:bg-mist"}`}>{label}</button>
      ))}
    </div>
  );
}
