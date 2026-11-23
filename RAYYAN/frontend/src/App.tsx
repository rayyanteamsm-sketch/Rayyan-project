import { useEffect, useState, type ReactNode } from "react";
import { DATA_NOTICE } from "../components/ui";
import { api } from "../services/api";
import DashboardPage from "../pages/DashboardPage";
import DecisionPage from "../pages/DecisionPage";
import SimulationPage from "../pages/SimulationPage";
import ModelPage from "../pages/ModelPage";
import SitePage from "../pages/SitePage";
import HistoryPage from "../pages/HistoryPage";
import V2Page from "../pages/V2Page";
import ZonesPage from "../pages/ZonesPage";
import ImageAnalysisPanel from "../pages/ImageAnalysisPanel";
import { CropsDashboardPanel, CropsHistoryPanel, CropsModelPanel, CropsRecommendPanel, CropsSimulationPanel } from "../pages/CropsPanels";

type Sys = "bermuda" | "crops" | "v2";
const isCrop = (p: string | null) => !!p && /^Z00[1-4]$/.test(p);

/** مبدّل النظام داخل الصفحة: نظام البرمودا أو المحاصيل الأربع (نموذجان مستقلان). */
function SystemSwitch({ value, onChange, extra }: { value: Sys; onChange: (s: Sys) => void; extra?: [Sys, string][] }) {
  const items: [Sys, string, string][] = [["bermuda", "ثيل البرمودا", "منطقتان · rule_v1"], ["crops", "المحاصيل الأربع", "نخيل · برسيم · خضار · نجيل"],
    ...((extra ?? []).map(([k, l]) => [k, l, "للمرجع"] as [Sys, string, string]))];
  return (
    <div role="tablist" aria-label="النظام" className="mb-5 inline-flex flex-wrap gap-1 rounded-2xl border border-line bg-white/80 p-1 shadow-sm backdrop-blur">
      {items.map(([k, label, hint]) => (
        <button key={k} role="tab" aria-selected={value === k} onClick={() => onChange(k)}
          className={`rounded-xl px-4 py-2 text-start transition ${value === k ? "bg-gradient-to-l from-leaf-dark to-water text-white shadow" : "text-ink hover:bg-mist"}`}>
          <span className="block text-sm font-semibold">{label}</span><span className={`block text-[10px] ${value === k ? "text-white/80" : "text-muted"}`}>{hint}</span>
        </button>))}
    </div>
  );
}

function Switched({ initial, extra, render }: { initial: Sys; extra?: [Sys, string][]; render: (s: Sys) => ReactNode }) {
  const [sys, setSys] = useState<Sys>(initial);
  useEffect(() => setSys(initial), [initial]);
  return <><SystemSwitch value={sys} onChange={setSys} extra={extra} />{render(sys)}</>;
}

interface PageDef { key: string; label: string; hint: string; icon: string; render: (param: string | null) => ReactNode }
const PAGES: PageDef[] = [
  { key: "dashboard", label: "لوحة التحكم", hint: "الرطوبة والقرارات والاستهلاك", icon: "M3 13h8V3H3zm10 8h8V11h-8zM3 21h8v-6H3zm10-18v6h8V3z",
    render: (p) => <Switched initial={p === "crops" ? "crops" : "bermuda"} render={(s) => (s === "crops" ? <CropsDashboardPanel /> : <DashboardPage param={p} />)} /> },
  { key: "decision", label: "توصية الري", hint: "القرار وسببه والكمية والمدة", icon: "M12 2c4 6 7 9.5 7 13a7 7 0 0 1-14 0c0-3.5 3-7 7-13z",
    render: (p) => <Switched initial={isCrop(p) ? "crops" : "bermuda"} render={(s) => (s === "crops" ? <CropsRecommendPanel initialZone={isCrop(p) ? p : null} /> : <DecisionPage param={isCrop(p) ? null : p} />)} /> },
  { key: "simulation", label: "المحاكاة", hint: "سيناريوهات بنماذج ML الفعلية", icon: "M4 19V5m0 14h16M8 15l3-4 3 2 5-7",
    render: (p) => <Switched initial={p === "crops" ? "crops" : "bermuda"} render={(s) => (s === "crops" ? <CropsSimulationPanel /> : <SimulationPage param={p} />)} /> },
  { key: "model", label: "أداء النماذج", hint: "المقاييس وخطوط الأساس والأهمية", icon: "M4 20h16M7 16V9m5 7V5m5 11v-4",
    render: (p) => <Switched initial={p === "crops" ? "crops" : p === "v2" ? "v2" : "bermuda"} extra={[["v2", "النموذج الثاني الأصلي (v2)"]]}
      render={(s) => (s === "crops" ? <CropsModelPanel /> : s === "v2" ? <V2Page param={null} /> : <ModelPage param={p} />)} /> },
  { key: "zones", label: "المناطق والمحاصيل", hint: "ست مناطق ونموذج كل منها", icon: "M3 7l6-3 6 3 6-3v13l-6 3-6-3-6 3zM9 4v13m6-10v13",
    render: (p) => <ZonesPage param={p} /> },
  { key: "history", label: "السجل", hint: "القرارات والتنبؤات — بحث وتصفية", icon: "M12 8v4l3 2M3 12a9 9 0 1 0 3-6.7M3 4v4h4",
    render: (p) => <Switched initial={p === "crops" ? "crops" : "bermuda"} render={(s) => (s === "crops" ? <CropsHistoryPanel /> : <HistoryPage param={p === "crops" ? null : p} />)} /> },
  { key: "site", label: "الموقع والمعرض", hint: "المناطق والأجهزة والصور الميدانية", icon: "M4 5h16v14H4zM4 15l5-5 4 4 3-3 4 4",
    render: (p) => <div className="space-y-6"><SitePage param={p} /><ImageAnalysisPanel /></div> },
];
const ALIAS: Record<string, [string, string | null]> = { v2: ["model", "v2"], recommend: ["decision", null], performance: ["model", null], gallery: ["site", null] };

function currentRoute(): { page: string; param: string | null } {
  let [p, param] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (ALIAS[p]) { param = param ?? ALIAS[p][1] ?? undefined as unknown as string; p = ALIAS[p][0]; }
  const page = PAGES.find((x) => x.key === p)?.key ?? "dashboard";
  return { page, param: param ? decodeURIComponent(param) : null };
}

function Icon({ d }: { d: string }) {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>;
}

function StatusPill() {
  const [h, setH] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => {
    const load = () => api.health().then((r) => setH({ ok: r.status === "ok" && r.model.loaded, text: r.model.loaded ? "الخادم والنماذج تعمل" : "النموذج غير محمّل" }))
      .catch(() => setH({ ok: false, text: "لا اتصال بالخادم" }));
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, []);
  if (!h) return null;
  return <span className={`chip ${h.ok ? "bg-[#E6F0EA] text-leaf" : "bg-danger-pale text-danger"}`}><span className={`h-2 w-2 rounded-full ${h.ok ? "bg-leaf pulse-dot" : "bg-danger"}`} />{h.text}</span>;
}

export default function App() {
  const [route, setRoute] = useState(currentRoute());
  const [menu, setMenu] = useState(false);
  useEffect(() => {
    const on = () => { setRoute(currentRoute()); setMenu(false); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const current = PAGES.find((p) => p.key === route.page)!;
  useEffect(() => { document.title = `${current.label} — ريّان`; }, [route.page]);

  return (
    <div className="min-h-screen md:grid md:grid-cols-[16.5rem_1fr]">
      <aside className="sidebar text-[#E6EFE9] md:sticky md:top-0 md:h-screen md:overflow-y-auto">
        <div className="flex items-center justify-between gap-3 px-5 py-5 md:block">
          <a href="#/dashboard" className="flex items-center gap-2.5 text-white no-underline">
            {/* رمز شعار مياهثون الدائري وحده على كحلي الشعار الأصلي (frontend/assets/mayahthon-symbol.png؛ المصادر في assets/brand/).
                الإطار الفاتح الخفيف يفصل البلاطة الكحلية عن خلفية القائمة الخضراء الداكنة */}
            <img src="assets/mayahthon-symbol.png" width={192} height={192} alt="رمز شعار مياهثون"
              className="h-11 w-11 shrink-0 rounded-xl shadow-md ring-1 ring-white/25" decoding="async" />
            <span><span className="block font-display text-2xl font-bold leading-none">ريّان</span><span className="text-[11px] text-[#9FC3B3]">RAYYAN · Smart Irrigation AI</span></span>
          </a>
          <button className="btn border-white/30 px-2 py-1 text-sm text-white md:hidden" onClick={() => setMenu(!menu)} aria-expanded={menu} aria-controls="nav">القائمة</button>
        </div>
        <nav id="nav" className={`${menu ? "block" : "hidden"} px-3 pb-4 md:block`} aria-label="القائمة الرئيسية">
          {PAGES.map((p) => (
            <a key={p.key} href={`#/${p.key}`} aria-current={route.page === p.key ? "page" : undefined}
              className={`nav-item mb-1 flex items-start gap-3 rounded-xl px-3 py-2.5 no-underline ${route.page === p.key ? "nav-active" : "text-[#E6EFE9] hover:bg-white/10"}`}>
              <span className="mt-0.5 opacity-90"><Icon d={p.icon} /></span>
              <span><span className="block font-medium">{p.label}</span><span className={`block text-[11px] ${route.page === p.key ? "text-leaf-dark/70" : "text-[#9FB8AA]"}`}>{p.hint}</span></span>
            </a>
          ))}
          <div className="mt-5 space-y-1 border-t border-white/10 pt-4 text-xs">
            <a href="/api/swagger" target="_blank" rel="noreferrer" className="block rounded-lg px-3 py-1.5 text-[#B9CEC1] no-underline hover:bg-white/10">Swagger — FastAPI ↗</a>
            <a href="/api/docs" target="_blank" rel="noreferrer" className="block rounded-lg px-3 py-1.5 text-[#B9CEC1] no-underline hover:bg-white/10">توثيق الـAPI بالعربية ↗</a>
          </div>
          <div className="mx-3 mt-5 rounded-xl bg-white/5 p-3 text-[11px] leading-relaxed text-[#B9CEC1]">
            نموذجان مستقلان: <b className="text-white">البرمودا</b> (Δ الرطوبة بعد ساعتين) و<b className="text-white">المحاصيل الأربع</b> (الرطوبة بعد 6 ساعات). لا صمامات متصلة.
          </div>
        </nav>
      </aside>
      <div className="min-w-0">
        <div role="note" className="border-b border-ochre/30 bg-ochre-pale/90 px-4 py-2 text-sm text-[#6d4a12] md:px-8">
          <b className="me-1">تنبيه البيانات:</b>{DATA_NOTICE}
        </div>
        <main className="mx-auto max-w-[1320px] px-4 py-6 md:px-8">
          <header className="page-head mb-6 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-xs font-semibold tracking-wide text-water">ريّان · {current.hint}</p>
              <h1 className="text-2xl font-medium md:text-[2rem]">{current.label}</h1>
            </div>
            <StatusPill />
          </header>
          <div key={route.page} className="fade-in">{current.render(route.param)}</div>
        </main>
        <footer className="mx-auto max-w-[1320px] px-4 pb-8 text-xs text-muted md:px-8">
          RAYYAN — React + TypeScript + Tailwind · FastAPI · scikit-learn · SQLite. بيانات محاكاة: البرمودا 2024–2025 والمحاصيل الأربع 2024-10 — 2026-10. لا توجد حساسات أو صمامات متصلة؛ لا يُنفذ أي تشغيل فعلي.
        </footer>
      </div>
    </div>
  );
}
