// رسوم تفاعلية بـ d3 (المقاييس والأشكال) مرسومة عبر React كـ SVG، مع تلميح عند المرور.
import { useMemo, useRef, useState, type ReactNode } from "react";
import { scaleBand, scaleLinear, scaleTime } from "d3-scale";
import { area, curveMonotoneX, line } from "d3-shape";
import { extent, max, min } from "d3-array";

export const PALETTE = { water: "#1F7AA8", leaf: "#2F6B4F", turf: "#7FA66A", ochre: "#B97A22", soil: "#8A6A45", muted: "#8FA39A", slate: "#5B7186" };

interface Tip { x: number; y: number; content: ReactNode }
function Tooltip({ tip, width }: { tip: Tip | null; width: number }) {
  if (!tip) return null;
  const left = Math.min(Math.max(tip.x, 70), width - 70);
  return (
    <div className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md border border-line bg-white/95 px-2 py-1 text-xs shadow-sm"
      style={{ left: `${(left / width) * 100}%`, top: tip.y - 8 }}>{tip.content}</div>
  );
}

function useSvgPoint(width: number) {
  const ref = useRef<SVGSVGElement | null>(null);
  const toLocal = (clientX: number) => {
    const r = ref.current!.getBoundingClientRect();
    return ((clientX - r.left) / r.width) * width;
  };
  return { ref, toLocal };
}

// ------------------------------------------------------------------ خطوط زمنية
export interface Series { name: string; color: string; points: { x: Date; y: number | null }[]; dashed?: boolean; width?: number }
export function LineChart({ series, height = 240, yDomain, refLines = [], yFormat = (v: number) => v.toFixed(3), yLabel, bands = [] }: {
  series: Series[]; height?: number; yDomain?: [number, number]; yLabel?: string;
  refLines?: { y: number; label: string; color: string; dashed?: boolean }[]; yFormat?: (v: number) => string;
  bands?: { from: Date; to: Date; label: string; color: string }[];
}) {
  const W = 760, H = height, m = { t: 14, r: 16, b: 28, l: 54 };
  const all = series.flatMap((s) => s.points.filter((p) => p.y !== null)) as { x: Date; y: number }[];
  const { ref, toLocal } = useSvgPoint(W);
  const [hover, setHover] = useState<number | null>(null);
  const xs = useMemo(() => {
    const [a, b] = extent(all, (p) => p.x) as [Date, Date];
    return scaleTime().domain([a ?? new Date(), b ?? new Date()]).range([m.l, W - m.r]);
  }, [series]);
  const ys = useMemo(() => {
    const lo = yDomain?.[0] ?? Math.min(min(all, (p) => p.y) ?? 0, ...refLines.map((r) => r.y));
    const hi = yDomain?.[1] ?? Math.max(max(all, (p) => p.y) ?? 1, ...refLines.map((r) => r.y));
    const pad = (hi - lo) * 0.08 || 0.01;
    return scaleLinear().domain([yDomain ? lo : lo - pad, yDomain ? hi : hi + pad]).range([H - m.b, m.t]).nice();
  }, [series, yDomain, refLines]);
  const xTicks = xs.ticks(6);
  const spanDays = (xs.domain()[1].getTime() - xs.domain()[0].getTime()) / 864e5;
  const tickFmt = (t: Date) => (spanDays < 70 ? t.toISOString().slice(5, 10) : t.toISOString().slice(0, 7));
  const dates = series[0]?.points.map((p) => p.x) ?? [];
  const onMove = (e: { clientX: number }) => {
    const x = xs.invert(toLocal(e.clientX)).getTime();
    let best = 0, bd = Infinity;
    dates.forEach((d, i) => { const dd = Math.abs(d.getTime() - x); if (dd < bd) { bd = dd; best = i; } });
    setHover(best);
  };
  const tip: Tip | null = hover === null || !dates[hover] ? null : {
    x: xs(dates[hover]), y: m.t + 10,
    content: (<div><div className="num font-medium">{dates[hover].toISOString().slice(0, 10)}</div>
      {series.map((s) => <div key={s.name} style={{ color: s.color }}>{s.name}: <span className="num">{s.points[hover]?.y == null ? "—" : yFormat(s.points[hover].y as number)}</span></div>)}</div>),
  };
  return (
    <div className="relative">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" style={{ direction: "ltr" }} onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img" aria-label={series.map((s) => s.name).join("، ")}>
        {bands.map((b, i) => <g key={i}><rect x={xs(b.from)} y={m.t} width={Math.max(1, xs(b.to) - xs(b.from))} height={H - m.t - m.b} fill={b.color} /><text x={xs(b.from) + 4} y={m.t + 11} fontSize="10" fill="#55685F">{b.label}</text></g>)}
        {ys.ticks(5).map((t) => <g key={t}><line x1={m.l} x2={W - m.r} y1={ys(t)} y2={ys(t)} stroke="#E3EAE5" /><text x={m.l - 6} y={ys(t) + 4} fontSize="11" textAnchor="end" fill="#55685F">{yFormat(t)}</text></g>)}
        {xTicks.map((t) => <text key={t.getTime()} x={xs(t)} y={H - 8} fontSize="11" textAnchor="middle" fill="#55685F">{tickFmt(t)}</text>)}
        {yLabel && <text x={12} y={m.t + 4} fontSize="10" fill="#55685F">{yLabel}</text>}
        {refLines.map((r) => <g key={r.label}><line x1={m.l} x2={W - m.r} y1={ys(r.y)} y2={ys(r.y)} stroke={r.color} strokeDasharray={r.dashed ? "6 4" : undefined} strokeWidth="1.5" /><text x={W - m.r - 4} y={ys(r.y) - 4} fontSize="10.5" textAnchor="end" fill={r.color} fontWeight="600">{r.label}</text></g>)}
        {series.map((s) => {
          const d = line<{ x: Date; y: number | null }>().defined((p) => p.y !== null).x((p) => xs(p.x)).y((p) => ys(p.y as number)).curve(curveMonotoneX)(s.points);
          return <path key={s.name} d={d ?? ""} fill="none" stroke={s.color} strokeWidth={s.width ?? 2} strokeDasharray={s.dashed ? "5 4" : undefined} />;
        })}
        {hover !== null && dates[hover] && <line x1={xs(dates[hover])} x2={xs(dates[hover])} y1={m.t} y2={H - m.b} stroke="#13302A" strokeOpacity=".25" />}
        {hover !== null && series.map((s) => s.points[hover]?.y != null && <circle key={s.name} cx={xs(s.points[hover].x)} cy={ys(s.points[hover].y as number)} r="3.5" fill={s.color} stroke="#fff" />)}
      </svg>
      <Tooltip tip={tip} width={W} />
      <Legend items={series.map((s) => ({ label: s.name, color: s.color, dashed: s.dashed }))} />
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      {items.map((i) => <span key={i.label} className="inline-flex items-center gap-1.5"><span className="inline-block h-0 w-4 border-t-2" style={{ borderColor: i.color, borderTopStyle: i.dashed ? "dashed" : "solid" }} />{i.label}</span>)}
    </div>
  );
}

// ------------------------------------------------------------------ أعمدة مجمعة
export function GroupedBars({ categories, series, height = 240, yFormat = (v: number) => v.toFixed(0), yLabel, highlight }: {
  categories: string[]; series: { name: string; color: string; values: (number | null)[] }[]; height?: number;
  yFormat?: (v: number) => string; yLabel?: string; highlight?: string;
}) {
  const W = 760, H = height, m = { t: yLabel ? 24 : 14, r: 12, b: 34, l: 58 };
  const [hover, setHover] = useState<number | null>(null);
  const x0 = scaleBand<string>().domain(categories).range([m.l, W - m.r]).padding(0.22);
  const x1 = scaleBand<string>().domain(series.map((s) => s.name)).range([0, x0.bandwidth()]).padding(0.08);
  const vals = series.flatMap((s) => s.values.filter((v): v is number => v !== null));
  const lo = Math.min(0, min(vals) ?? 0), hi = Math.max(0, max(vals) ?? 1);
  const ys = scaleLinear().domain([lo, hi]).range([H - m.b, m.t]).nice();
  const every = Math.ceil(categories.length / 12);
  const tip: Tip | null = hover === null ? null : {
    x: (x0(categories[hover]) ?? 0) + x0.bandwidth() / 2, y: m.t + 10,
    content: <div><div className="font-medium">{categories[hover]}</div>{series.map((s) => <div key={s.name} style={{ color: s.color }}>{s.name}: <span className="num">{s.values[hover] == null ? "—" : yFormat(s.values[hover] as number)}</span></div>)}</div>,
  };
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" style={{ direction: "ltr" }} onMouseLeave={() => setHover(null)} role="img" aria-label={yLabel ?? "أعمدة"}>
        {ys.ticks(5).map((t) => <g key={t}><line x1={m.l} x2={W - m.r} y1={ys(t)} y2={ys(t)} stroke={t === 0 ? "#9fb0a7" : "#E3EAE5"} /><text x={m.l - 6} y={ys(t) + 4} fontSize="11" textAnchor="end" fill="#55685F">{yFormat(t)}</text></g>)}
        {yLabel && <text x={10} y={11} fontSize="10" fill="#55685F">{yLabel}</text>}
        {categories.map((c, i) => (
          <g key={c} onMouseEnter={() => setHover(i)}>
            <rect x={x0(c)} y={m.t} width={x0.bandwidth()} height={H - m.t - m.b} fill={hover === i ? "#EEF3EF" : c === highlight ? "#F3F7F4" : "transparent"} />
            {series.map((s) => s.values[i] != null && (
              <rect key={s.name} x={(x0(c) ?? 0) + (x1(s.name) ?? 0)} width={x1.bandwidth()}
                y={ys(Math.max(0, s.values[i] as number))} height={Math.abs(ys(s.values[i] as number) - ys(0))} fill={s.color} rx="2" />
            ))}
            {i % every === 0 && <text x={(x0(c) ?? 0) + x0.bandwidth() / 2} y={H - 12} fontSize="10.5" textAnchor="middle" fill="#55685F">{c}</text>}
          </g>
        ))}
      </svg>
      <Tooltip tip={tip} width={W} />
      <Legend items={series.map((s) => ({ label: s.name, color: s.color }))} />
    </div>
  );
}

// ------------------------------------------------------------------ تبعثر: المتنبأ مقابل الفعلي
export function Scatter({ points, height = 360, label = "", xLabel = "الفعلي في المحاكاة (Δ رطوبة)" }: {
  points: { x: number; y: number; color: string; id: string; extra?: string }[]; height?: number; label?: string; xLabel?: string;
}) {
  const W = 460, H = height, m = { t: 12, r: 14, b: 40, l: 56 };
  const [hover, setHover] = useState<number | null>(null);
  const vals = points.flatMap((p) => [p.x, p.y]);
  const lo = (min(vals) ?? 0) - 0.002, hi = (max(vals) ?? 0.04) + 0.002;
  const xs = scaleLinear().domain([lo, hi]).range([m.l, W - m.r]).nice();
  const ys = scaleLinear().domain(xs.domain()).range([H - m.b, m.t]);
  const p = hover === null ? null : points[hover];
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" style={{ direction: "ltr" }} role="img" aria-label={label}>
        {xs.ticks(5).map((t) => <g key={t}><line x1={m.l} x2={W - m.r} y1={ys(t)} y2={ys(t)} stroke="#E3EAE5" /><line y1={m.t} y2={H - m.b} x1={xs(t)} x2={xs(t)} stroke="#F0F4F1" />
          <text x={m.l - 6} y={ys(t) + 4} fontSize="10.5" textAnchor="end" fill="#55685F">{t.toFixed(3)}</text><text x={xs(t)} y={H - m.b + 15} fontSize="10.5" textAnchor="middle" fill="#55685F">{t.toFixed(3)}</text></g>)}
        <line x1={xs(xs.domain()[0])} y1={ys(xs.domain()[0])} x2={xs(xs.domain()[1])} y2={ys(xs.domain()[1])} stroke={PALETTE.ochre} strokeDasharray="5 4" />
        {points.map((pt, i) => <circle key={pt.id} cx={xs(pt.x)} cy={ys(pt.y)} r={hover === i ? 6 : 3.6} fill={pt.color} fillOpacity={hover === i ? 1 : 0.62}
          stroke={hover === i ? "#13302A" : "none"} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} style={{ cursor: "pointer" }} />)}
        <text x={(W + m.l) / 2} y={H - 4} fontSize="11.5" textAnchor="middle" fill="#13302A">{xLabel}</text>
        <text transform={`translate(13 ${(H - m.b) / 2}) rotate(-90)`} fontSize="11.5" textAnchor="middle" fill="#13302A">المتنبأ به</text>
      </svg>
      {p && <Tooltip width={W} tip={{ x: xs(p.x), y: 24, content: <div><div className="num font-medium">{p.id}</div><div>الفعلي <span className="num">{p.x.toFixed(4)}</span></div><div>المتنبأ <span className="num">{p.y.toFixed(4)}</span></div><div>الخطأ <span className="num">{(p.y - p.x).toFixed(4)}</span></div>{p.extra && <div className="text-muted">{p.extra}</div>}</div> }} />}
    </div>
  );
}

// ------------------------------------------------------------------ أعمدة أفقية
export function HBars({ items, format = (v: number) => v.toFixed(4), color = PALETTE.leaf }: {
  items: { label: string; value: number; err?: number; note?: string }[]; format?: (v: number) => string; color?: string;
}) {
  const hi = max(items, (i) => i.value + (i.err ?? 0)) ?? 1;
  return (
    <div className="space-y-1.5">
      {items.map((it, k) => (
        <div key={it.label} className="grid grid-cols-[9rem_1fr_5.5rem] items-center gap-2 text-sm" title={it.note}>
          <span className="truncate">{it.label}</span>
          <div className="relative h-4 rounded bg-[#EEF2EF]">
            <div className="absolute inset-y-0 right-0 rounded" style={{ width: `${Math.max(0.5, (Math.max(0, it.value) / hi) * 100)}%`, background: k === 0 ? "#1E4A36" : color, transition: "width .6s" }} />
            {it.err ? <div className="absolute top-1/2 h-px bg-ink/60" style={{ right: `${(Math.max(0, it.value - it.err) / hi) * 100}%`, width: `${(2 * it.err / hi) * 100}%` }} /> : null}
          </div>
          <span className="num text-xs text-muted">{format(it.value)}</span>
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ منحنى التدفق لرية
export function FlowChart({ series, nominal, plannedEnd, height = 200 }: {
  series: { t: string; flow_l_min: number | null }[]; nominal: number; plannedEnd: string; height?: number;
}) {
  const W = 760, H = height, m = { t: 12, r: 14, b: 28, l: 48 };
  const pts = series.filter((s) => s.flow_l_min !== null).map((s) => ({ x: new Date(s.t), y: s.flow_l_min as number }));
  if (!pts.length) return <p className="text-sm text-muted">لا توجد قراءات تدفق.</p>;
  const xs = scaleTime().domain(extent(pts, (p) => p.x) as [Date, Date]).range([m.l, W - m.r]);
  const ys = scaleLinear().domain([0, Math.max(nominal * 1.25, max(pts, (p) => p.y) ?? 1)]).range([H - m.b, m.t]);
  const a = area<{ x: Date; y: number }>().x((p) => xs(p.x)).y0(ys(0)).y1((p) => ys(p.y))(pts);
  const pe = xs(new Date(plannedEnd));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" style={{ direction: "ltr" }} role="img" aria-label="منحنى التدفق">
      {ys.ticks(4).map((t) => <g key={t}><line x1={m.l} x2={W - m.r} y1={ys(t)} y2={ys(t)} stroke="#E3EAE5" /><text x={m.l - 6} y={ys(t) + 4} fontSize="10.5" textAnchor="end" fill="#55685F">{t}</text></g>)}
      {xs.ticks(6).map((t) => <text key={t.getTime()} x={xs(t)} y={H - 8} fontSize="10.5" textAnchor="middle" fill="#55685F">{t.toISOString().slice(11, 16)}</text>)}
      <path d={a ?? ""} fill="#8CC9E6" fillOpacity=".55" stroke={PALETTE.water} strokeWidth="1.5" />
      <line x1={m.l} x2={W - m.r} y1={ys(nominal)} y2={ys(nominal)} stroke={PALETTE.leaf} strokeDasharray="5 4" />
      <text x={W - m.r} y={ys(nominal) - 4} fontSize="10.5" textAnchor="end" fill={PALETTE.leaf}>التدفق الاسمي {nominal} ل/د</text>
      <line x1={m.l} x2={W - m.r} y1={ys(nominal * 0.7)} y2={ys(nominal * 0.7)} stroke={PALETTE.ochre} strokeDasharray="2 3" />
      <text x={m.l + 4} y={ys(nominal * 0.7) - 4} fontSize="10" fill={PALETTE.ochre}>حد التدفق المنخفض 70٪</text>
      {pe >= m.l && pe <= W - m.r && <g><line x1={pe} x2={pe} y1={m.t} y2={H - m.b} stroke="#B0432A" strokeDasharray="4 3" /><text x={pe - 4} y={m.t + 10} fontSize="10.5" textAnchor="end" fill="#B0432A">نهاية الخطة</text></g>}
    </svg>
  );
}

// ------------------------------------------------------------------ منحنى استجابة: الكمية ← الرطوبة المتوقعة (محور x رقمي)
export function ResponseCurve({ series, height = 280, refLines = [], band, markers = [], xLabel = "كمية الري (لتر)", yLabel = "الرطوبة بعد 6 ساعات %" }: {
  series: { name: string; color: string; points: { x: number; y: number }[]; dashed?: boolean }[]; height?: number;
  refLines?: { y: number; label: string; color: string; dashed?: boolean }[]; band?: { from: number; to: number; label: string };
  markers?: { x: number; y: number; label: string; color: string }[]; xLabel?: string; yLabel?: string;
}) {
  const W = 760, H = height, m = { t: 18, r: 18, b: 40, l: 56 };
  const pts = series.flatMap((s) => s.points);
  const { ref, toLocal } = useSvgPoint(W);
  const [hover, setHover] = useState<number | null>(null);
  const xMax = Math.max(max(pts, (p) => p.x) ?? 1, ...markers.map((k) => k.x), band?.to ?? 0);
  const ys0 = [...pts.map((p) => p.y), ...refLines.map((r) => r.y), ...markers.map((k) => k.y)];
  const lo = min(ys0) ?? 0, hi = max(ys0) ?? 1, pad = (hi - lo) * 0.1 || 1;
  const xs = scaleLinear().domain([0, xMax]).range([m.l, W - m.r]).nice();
  const ys = scaleLinear().domain([lo - pad, hi + pad]).range([H - m.b, m.t]).nice();
  const base = series[0]?.points ?? [];
  const onMove = (e: { clientX: number }) => {
    const x = xs.invert(toLocal(e.clientX));
    let best = 0, bd = Infinity;
    base.forEach((p, i) => { const d = Math.abs(p.x - x); if (d < bd) { bd = d; best = i; } });
    setHover(best);
  };
  const fmtX = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k` : v.toFixed(0));
  return (
    <div className="relative">
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" style={{ direction: "ltr" }} onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img" aria-label={yLabel}>
        {band && <g><rect x={xs(band.from)} y={m.t} width={Math.max(1, xs(Math.min(band.to, xs.domain()[1])) - xs(band.from))} height={H - m.t - m.b} fill="#1F7AA80F" />
          <text x={xs(band.from) + 6} y={m.t + 12} fontSize="10.5" fill="#1F7AA8">{band.label}</text></g>}
        {ys.ticks(5).map((t) => <g key={t}><line x1={m.l} x2={W - m.r} y1={ys(t)} y2={ys(t)} stroke="#E3EAE5" /><text x={m.l - 6} y={ys(t) + 4} fontSize="11" textAnchor="end" fill="#55685F">{t.toFixed(1)}</text></g>)}
        {xs.ticks(7).map((t) => <text key={t} x={xs(t)} y={H - 22} fontSize="11" textAnchor="middle" fill="#55685F">{fmtX(t)}</text>)}
        <text x={(W + m.l) / 2} y={H - 5} fontSize="11.5" textAnchor="middle" fill="#13302A">{xLabel}</text>
        <text x={12} y={m.t - 4} fontSize="10" fill="#55685F">{yLabel}</text>
        {refLines.map((r) => <g key={r.label}><line x1={m.l} x2={W - m.r} y1={ys(r.y)} y2={ys(r.y)} stroke={r.color} strokeDasharray={r.dashed ? "6 4" : undefined} strokeWidth="1.5" />
          <text x={W - m.r - 4} y={ys(r.y) - 4} fontSize="10.5" textAnchor="end" fill={r.color} fontWeight="600">{r.label}</text></g>)}
        {series.map((s) => {
          const d = line<{ x: number; y: number }>().x((p) => xs(p.x)).y((p) => ys(p.y)).curve(curveMonotoneX)(s.points);
          const a = area<{ x: number; y: number }>().x((p) => xs(p.x)).y0(H - m.b).y1((p) => ys(p.y)).curve(curveMonotoneX)(s.points);
          return <g key={s.name}>{!s.dashed && <path d={a ?? ""} fill={s.color} opacity="0.07" />}<path d={d ?? ""} fill="none" stroke={s.color} strokeWidth={s.dashed ? 1.6 : 2.6} strokeDasharray={s.dashed ? "5 4" : undefined} /></g>;
        })}
        {markers.map((k, i) => <g key={i}><circle cx={xs(k.x)} cy={ys(k.y)} r="6.5" fill={k.color} stroke="#fff" strokeWidth="2" />
          <text x={xs(k.x)} y={ys(k.y) - 11} fontSize="10.5" textAnchor="middle" fill={k.color} fontWeight="700">{k.label}</text></g>)}
        {hover !== null && base[hover] && <line x1={xs(base[hover].x)} x2={xs(base[hover].x)} y1={m.t} y2={H - m.b} stroke="#13302A" strokeOpacity=".25" />}
        {hover !== null && series.map((s) => s.points[hover] && <circle key={s.name} cx={xs(s.points[hover].x)} cy={ys(s.points[hover].y)} r="3.5" fill={s.color} stroke="#fff" />)}
      </svg>
      {hover !== null && base[hover] && <Tooltip width={W} tip={{ x: xs(base[hover].x), y: m.t + 10, content: (
        <div><div className="num font-medium">{base[hover].x.toLocaleString("en", { maximumFractionDigits: 0 })} L</div>
          {series.map((s) => <div key={s.name} style={{ color: s.color }}>{s.name}: <span className="num">{s.points[hover]?.y.toFixed(2)}%</span></div>)}</div>) }} />}
      <Legend items={series.map((s) => ({ label: s.name, color: s.color, dashed: s.dashed }))} />
    </div>
  );
}
