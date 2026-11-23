const vw = document.documentElement.clientWidth;
const out = [];
for (const el of document.querySelectorAll("body *")) {
  const r = el.getBoundingClientRect();
  if (r.width > 0 && (r.right > vw + 1 || r.left < -1)) {
    // keep only the deepest offenders (children that do not overflow themselves)
    const kids = [...el.children].some((c) => { const k = c.getBoundingClientRect(); return k.right > vw + 1 || k.left < -1; });
    if (!kids) out.push({ tag: el.tagName, cls: String(el.className?.baseVal ?? el.className).slice(0, 90), left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width), text: (el.textContent || "").trim().slice(0, 40) });
  }
}
return { vw, scrollW: document.documentElement.scrollWidth, n: out.length, offenders: out.slice(0, 15) };
