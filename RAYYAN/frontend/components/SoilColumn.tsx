import { useEffect, useId, useState } from "react";
import { fmt } from "./ui";

/**
 * مقطع تربة يظهر فيه مستوى الماء. كل المستويات تأتي من الخادم:
 * current = رطوبة وقت القرار، predicted = تنبؤ النموذج بعد الري، target = السعة الحقلية، trigger = عتبة القرار.
 * يتحرك الماء بانتقال CSS عند تغير القيم الحقيقية، لا بحركة ثابتة.
 */
interface Props {
  current: number | null; target: number; trigger?: number; predicted?: number | null;
  wilting?: number; max?: number; label?: string; compact?: boolean;
  /** القيم نسب مئوية (المحاصيل الأربع) بدل m³/m³ (البرمودا) */
  pct?: boolean;
}

export default function SoilColumn({ current, target, trigger, predicted = null, wilting, max: maxIn, label, compact = false, pct = false }: Props) {
  const max = maxIn ?? (pct ? 50 : 0.2);
  const step = pct ? 5 : 0.05;
  const lbl = (v: number) => (pct ? `${v.toFixed(1)}%` : v.toFixed(3));
  const uid = useId().replace(/:/g, "");
  const W = 150, top = 34, bot = compact ? 300 : 380, H = bot - top, x0 = 54, x1 = 54 + 92;
  const y = (v: number) => bot - Math.max(0, Math.min(v, max)) / max * H;
  // المستوى الحقيقي يُرسم مباشرة (يظهر حتى لو لم تعمل الحركة)، وانتقال CSS يحرّك الماء عند كل تغيير في القيم.
  // عند أول ظهور يرتفع العمود بحركة grow (CSS) من القاع.
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);
  const c0 = current ?? 0;
  const cy = y(c0), py = predicted != null ? y(Math.max(predicted, c0)) : cy;
  const ticks = Array.from({ length: Math.floor(max / step + 1e-9) + 1 }, (_, i) => +(i * step).toFixed(2));
  const f = (v: number | null | undefined) => (pct ? (v == null ? "—" : `${v.toFixed(1)}%`) : fmt(v));
  const desc = `رطوبة حالية ${f(current)}، الهدف ${f(target)}` + (trigger !== undefined ? `، العتبة ${f(trigger)}` : "") + (predicted != null ? `، المتوقعة بعد الري ${f(predicted)}` : "");

  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W + 40} ${bot + 14}`} className="block h-auto w-full" role="img" aria-label={desc} style={{ direction: "ltr" }}>
        <defs>
          <pattern id={`g${uid}`} width="12" height="12" patternUnits="userSpaceOnUse">
            <rect width="12" height="12" fill="#A88A62" />
            <circle cx="3" cy="3" r="1.2" fill="#7E6141" /><circle cx="9" cy="8" r="0.9" fill="#C9AE86" /><circle cx="10" cy="2" r="0.7" fill="#6E5236" />
          </pattern>
          <linearGradient id={`w${uid}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#2A8CBF" stopOpacity="0.85" /><stop offset="1" stopColor="#155F86" stopOpacity="0.92" />
          </linearGradient>
          <clipPath id={`c${uid}`}><rect x={x0} y={top} width={x1 - x0} height={H} rx="10" /></clipPath>
        </defs>
        <rect x={x0} y={top} width={x1 - x0} height={H} rx="10" fill={`url(#g${uid})`} />
        <g clipPath={`url(#c${uid})`}>
          {/* الماء المتوقع بعد الري — فاتح، فوق الحالي */}
          <g className={mounted ? "water-grow" : undefined} style={{ transformOrigin: `0 ${bot}px` }}>
            <rect className="water-rise" x={x0} width={x1 - x0} y={py} height={Math.max(0, cy - py)} fill="#8CC9E6" opacity="0.9" />
            {/* الماء الحالي */}
            <rect className="water-rise" x={x0} width={x1 - x0} y={cy} height={Math.max(0, bot - cy)} fill={`url(#w${uid})`} />
          </g>
          {current !== null && (
            <path className="water-surface" d={`M${x0 - 40} 0 q10 -3 20 0 t20 0 t20 0 t20 0 t20 0 t20 0 t20 0 t20 0 t20 0`}
              transform={`translate(0 ${cy})`} stroke="#BFE3F3" strokeWidth="1.5" fill="none" opacity="0.8" style={{ transition: "transform 1.1s" }} />
          )}
        </g>
        {/* العشب */}
        {Array.from({ length: 20 }, (_, i) => {
          const bx = x0 + 3 + i * 4.6, h = 11 + ((i * 7) % 11);
          return <path key={i} d={`M${bx} ${top + 2} q${(i % 3) - 1} ${-h / 2} ${i % 2 ? 3 : -3} ${-h}`} stroke={i % 4 ? "#7FA66A" : "#2F6B4F"} strokeWidth="2" fill="none" strokeLinecap="round" />;
        })}
        {/* المحور */}
        {ticks.map((t) => (
          <g key={t}><line x1={x1 + 2} x2={x1 + 6} y1={y(t)} y2={y(t)} stroke="#55685F" /><text x={x1 + 9} y={y(t) + 4} fontSize="10" fill="#55685F">{pct ? `${t}%` : t.toFixed(2)}</text></g>
        ))}
        {wilting !== undefined && <line x1={x0} x2={x1} y1={y(wilting)} y2={y(wilting)} stroke="#5f4a33" strokeDasharray="2 3" />}
        <line x1={x0 - 8} x2={x1 + 2} y1={y(target)} y2={y(target)} stroke="#2F6B4F" strokeWidth="2.5" />
        <text x={x0 - 11} y={y(target) + 4} fontSize="11" fontWeight="700" fill="#2F6B4F" textAnchor="end">{lbl(target)}</text>
        {trigger !== undefined && <>
          <line x1={x0 - 8} x2={x1 + 2} y1={y(trigger)} y2={y(trigger)} stroke="#B97A22" strokeWidth="2.2" strokeDasharray="6 4" />
          <text x={x0 - 11} y={y(trigger) + 4} fontSize="11" fontWeight="700" fill="#B97A22" textAnchor="end">{lbl(trigger)}</text>
        </>}
        {current !== null ? (
          <text x={(x0 + x1) / 2} y={Math.min(bot - 8, y(current) + 20)} textAnchor="middle" fontSize="15" fontWeight="700" fill="#fff">{lbl(current)}</text>
        ) : (
          <text x={(x0 + x1) / 2} y={top + H / 2} textAnchor="middle" fontSize="13" fontWeight="700" fill="#fff">لا قراءة</text>
        )}
        {predicted != null && current !== null && predicted > current && (
          <text x={(x0 + x1) / 2} y={Math.max(top + 14, y(predicted) - 5)} textAnchor="middle" fontSize="12" fontWeight="700" fill="#155F86">{lbl(predicted)}</text>
        )}
      </svg>
      <figcaption className="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5 text-[11px] text-muted">
        {label && <span className="col-span-2 font-medium text-ink">{label}</span>}
        <span><i className="me-1 inline-block h-1.5 w-3 rounded bg-[#1F7AA8] align-middle" />الحالية</span>
        <span><i className="me-1 inline-block h-1.5 w-3 rounded bg-water-light align-middle" />المتوقعة بعد الري</span>
        <span><i className="me-1 inline-block h-1 w-3 rounded bg-leaf align-middle" />الهدف (FC)</span>
        {trigger !== undefined ? <span><i className="me-1 inline-block h-0.5 w-3 border-t-2 border-dashed border-ochre align-middle" />عتبة الري</span>
          : wilting !== undefined && <span><i className="me-1 inline-block h-0.5 w-3 border-t-2 border-dotted border-soil align-middle" />نقطة الذبول</span>}
      </figcaption>
    </figure>
  );
}
