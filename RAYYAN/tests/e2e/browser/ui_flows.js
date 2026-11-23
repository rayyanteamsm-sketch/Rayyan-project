// اختبار واجهة شامل داخل المتصفح: كل الصفحات والتبويبات، ثم تفاعلات حقيقية مع الخادم.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, info = "") => results.push({ name, ok: !!ok, info: String(info).slice(0, 140) });
const waitFor = async (fn, ms = 15000) => { const t = Date.now(); while (Date.now() - t < ms) { try { const v = fn(); if (v) return v; } catch { } await sleep(150); } return null; };
const go = async (hash) => { location.hash = hash; await sleep(300); };
const text = () => document.querySelector("main")?.innerText ?? "";
const noError = () => !document.querySelector('[role="alert"]');
const clickTab = async (label) => { const b = [...document.querySelectorAll('[role="tab"]')].find((x) => x.innerText.includes(label)); b?.click(); await sleep(300); return !!b; };

// 1) كل صفحة وكل نظام يُحمَّل دون رسالة خطأ
const pages = [["#/dashboard", "ثيل البرمودا", "Z02"], ["#/dashboard", "المحاصيل الأربع", "نخيل"], ["#/decision", "ثيل البرمودا", "المنطقة"],
  ["#/decision", "المحاصيل الأربع", "لماذا هذا القرار"], ["#/simulation", "ثيل البرمودا", "سيناريو"], ["#/simulation", "المحاصيل الأربع", "منحنى الاستجابة"],
  ["#/model", "ثيل البرمودا", "RMSE"], ["#/model", "المحاصيل الأربع", "Feature Importance"], ["#/model", "النموذج الثاني الأصلي", "Random Forest"],
  ["#/zones", null, "بيانات نخيل"], ["#/history", "ثيل البرمودا", "D20"], ["#/history", "المحاصيل الأربع", "سجلًا"], ["#/site", null, "تحليل الصور الميدانية"]];
for (const [hash, tab, expect] of pages) {
  await go(hash);
  if (tab) await clickTab(tab);
  const ok = await waitFor(() => text().includes(expect) && !document.querySelector('[role="status"]'));
  check(`page ${hash} ${tab ?? ""}`, ok && noError(), ok ? "" : text().slice(0, 140));
}

// 2) توصية المحاصيل: زر «أصدري التوصية واحفظيها» يحفظ في SQLite ويظهر رقم الحفظ
await go("#/decision/Z002");
await waitFor(() => text().includes("لماذا هذا القرار"));
const before = (await (await fetch("/api/crops/history?limit=1")).json()).total;
const rain = [...document.querySelectorAll("label")].find((l) => l.innerText.includes("مطر متوقع"))?.querySelector("input");
const setVal = (el, v) => { const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set; s.call(el, v); el.dispatchEvent(new Event("input", { bubbles: true })); };
setVal(rain, "50");
await sleep(200);
[...document.querySelectorAll("button")].find((b) => b.innerText.includes("أصدري التوصية"))?.click();
const savedChip = await waitFor(() => /حُفظت في السجل #\d+/.exec(text())?.[0]);
const after = (await (await fetch("/api/crops/history?limit=1")).json()).total;
check("crop recommend saves via UI", savedChip && after === before + 1, `${savedChip} total ${before}->${after}`);
check("rain 50mm defers (rule)", text().includes("المطر المتوقع (50 مم) يغطي") || text().includes("تأجيل"), text().match(/المطر المتوقع[^\n]{0,60}/)?.[0]);

// 3) محاكاة المحاصيل: إضافة سيناريو وتشغيل
await go("#/simulation"); await clickTab("المحاصيل الأربع");
await waitFor(() => text().includes("منحنى الاستجابة"));
[...document.querySelectorAll("button")].find((b) => b.innerText.includes("+ سيناريو"))?.click(); await sleep(200);
const nBefore = (await (await fetch("/api/crops/history?source=simulation&limit=1")).json()).total;
[...document.querySelectorAll("button")].find((b) => b.innerText.includes("شغّلي المحاكاة"))?.click();
const four = await waitFor(() => (text().match(/محفوظ #\d+/g) || []).length === 4 && text().match(/محفوظ #\d+/g));
const nAfter = (await (await fetch("/api/crops/history?source=simulation&limit=1")).json()).total;
check("crop simulation 4 scenarios saved", four && nAfter === nBefore + 4, `${nBefore}->${nAfter}`);

// 4) السجل: البحث والتصفية تعيد نتائج من الخادم
await go("#/history"); await clickTab("المحاصيل الأربع");
await waitFor(() => text().includes("سجلًا"));
const sel = [...document.querySelectorAll("label")].find((l) => l.innerText.startsWith("المصدر"))?.querySelector("select");
sel.value = "recommend"; sel.dispatchEvent(new Event("change", { bubbles: true }));
const filtered = await waitFor(() => { const rows = [...document.querySelectorAll("tbody tr")].filter((r) => r.cells.length > 5); return rows.length && rows.every((r) => r.innerText.includes("توصية")) && rows.length; });
check("crop history filter by source", filtered, filtered);

// 5) توصية البرمودا عبر الواجهة (نموذج البرمودا) تحفظ في app_recommendations
await go("#/decision"); await clickTab("ثيل البرمودا");
await waitFor(() => document.querySelector("form"));
const bBefore = (await (await fetch("/api/history?source=app&limit=1")).json()).total;
const submit = [...document.querySelectorAll("form button")].find((b) => b.type !== "button" && /أصدر|احسب|قرار/.test(b.innerText));
submit?.click();
const bDone = await waitFor(async () => false, 10);
await sleep(4000);
const bAfter = (await (await fetch("/api/history?source=app&limit=1")).json()).total;
check("bermuda recommend saves via UI", bAfter === bBefore + 1, `${submit?.innerText} ${bBefore}->${bAfter}`);

// 6) المناطق: اختيار منطقة برمودا وتشغيل نموذجها
await go("#/zones/Z02");
const berm = await waitFor(() => text().includes("تنبؤ نموذج البرمودا") && text().includes("التغير المتوقع"));
check("zones: bermuda zone runs bermuda model", berm);
await go("#/zones/Z004");
check("zones: crop zone runs crops model", await waitFor(() => text().includes("بيانات نجيل") && text().includes("المتوقعة بعد 6 ساعات")));

// 7) المعرض: الصور الأصلية ومخرجات المعالجة تُحمَّل فعلًا
await go("#/site");
await waitFor(() => text().includes("تحليل الصور الميدانية"));
await sleep(1500);
const imgs = [...document.querySelectorAll("main img")];
await Promise.all(imgs.map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; setTimeout(r, 4000); }))));
const broken = imgs.filter((i) => i.complete && i.naturalWidth === 0 && !i.loading?.includes("lazy"));
check("gallery + processed images load", imgs.length >= 12 && broken.length === 0, `imgs ${imgs.length}, broken ${broken.length}`);

return { passed: results.filter((r) => r.ok).length, total: results.length, failed: results.filter((r) => !r.ok) };
