"""
اختبارات واجهة في متصفح حقيقي (Playwright + Chromium): كل شاشة تفتح دون أخطاء، والأزرار تؤدي وظيفة،
والقيم المعروضة تطابق الـAPI. تُتخطى تلقائيًا إن لم يتوفر Playwright أو متصفح.
"""
import json
import os
import shutil
import urllib.request

import pytest

pw = pytest.importorskip("playwright.sync_api")
NOTICE = "تعتمد نتائج النموذج الحالية على بيانات محاكاة، ولا تمثل دقة مثبتة في بيئة زراعية حقيقية."


def _chrome():
    for p in (os.environ.get("RAYYAN_CHROME"), "/usr/bin/google-chrome", shutil.which("chromium"), shutil.which("google-chrome"),
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if p and os.path.exists(p):
            return p
    return None


@pytest.fixture(scope="module")
def page(server):
    with pw.sync_playwright() as p:
        exe = _chrome()
        try:
            browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if exe else p.chromium.launch()
        except Exception as e:  # لا متصفح متاح
            pytest.skip(f"لا يوجد متصفح لاختبارات الواجهة: {e}")
        pg = browser.new_page(viewport={"width": 1366, "height": 900})
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" and "fonts.g" not in m.text else None)
        pg.base = server
        yield pg
        browser.close()


def api(page, path):
    with urllib.request.urlopen(page.base + path) as r:
        return json.loads(r.read())


def go(page, route):
    page.goto(f"{page.base}/#/{route}")
    page.wait_for_load_state("networkidle")
    # انتظار اكتمال التحميل الفعلي: لا مؤشر «جارٍ التحميل» داخل الصفحة
    page.wait_for_selector("main h1", timeout=15000)
    page.wait_for_function("document.querySelectorAll('main [role=status]').length === 0", timeout=15000)


@pytest.mark.parametrize("route,title", [("dashboard", "لوحة التحكم"), ("decision", "توصية الري"), ("simulation", "المحاكاة"),
                                         ("model", "أداء النماذج"), ("zones", "المناطق والمحاصيل"), ("site", "الموقع والمعرض"),
                                         ("history", "السجل"), ("v2", "أداء النماذج")])  # v2: اسم بديل يفتح تبويب النموذج الثاني
def test_every_screen_loads_with_notice(page, route, title):
    go(page, route)
    assert page.locator("h1").inner_text() == title
    assert NOTICE in page.locator("[role=note]").inner_text()
    assert page.locator("html").get_attribute("dir") == "rtl"
    assert page.errors == [], page.errors


def test_dashboard_soil_column_uses_backend_values(page):
    go(page, "dashboard")
    d = api(page, "/api/dashboard")
    z2 = next(z for z in d["zones"] if z["zone_id"] == "Z02")
    label = page.locator("svg[aria-label^='رطوبة حالية']").nth(1).get_attribute("aria-label")
    assert f"{z2['recommendation']['inputs']['pre_vwc']:.3f}" in label
    assert f"{z2['recommendation']['prediction']['post_vwc']:.3f}" in label
    # تغيير اليوم يعيد الطلب ويغير القيم
    page.fill("input[type=date]", "2024-07-15")
    page.wait_for_load_state("networkidle")
    d2 = api(page, "/api/dashboard?date=2024-07-15")
    v = d2["zones"][0]["recommendation"]["inputs"]["pre_vwc"]
    page.wait_for_function(f"document.querySelector(\"svg[aria-label^='رطوبة حالية']\").getAttribute('aria-label').includes('{v:.3f}')")
    page.click("button[aria-label='اليوم التالي']")
    page.wait_for_function("document.querySelector('input[type=date]').value === '2024-07-16'", timeout=10000)
    page.click("button[aria-label='اليوم السابق']")
    page.wait_for_function("document.querySelector('input[type=date]').value === '2024-07-15'", timeout=10000)


def test_decision_presets_and_form(page):
    go(page, "decision")
    page.wait_for_selector("text=كيف حُسبت العتبة")
    headline = "main span.text-5xl"
    page.click("button:has-text('حساس معطل')")
    page.wait_for_function(f"document.querySelector('{headline}')?.textContent === 'فحص الحساس'")
    page.click("button:has-text('مطر قادم')")
    page.wait_for_function(f"document.querySelector('{headline}')?.textContent === 'تأجيل'")
    page.click("button:has-text('صيف جاف')")
    page.wait_for_function(f"document.querySelector('{headline}')?.textContent === 'ري'")
    assert page.locator("main >> text=مدة التشغيل").first.is_visible()
    page.click("button:has-text('من المحاكاة')")
    page.wait_for_timeout(500)
    page.click("button:has-text('احسبي التوصية')")
    page.wait_for_load_state("networkidle")
    assert "حُفظت برقم" in page.content()
    assert page.errors == []


def test_decision_replay_route(page):
    go(page, "decision/D20250315Z02")
    page.wait_for_selector("text=مقارنة بقرار المحاكي المحفوظ")
    assert page.locator("main span.text-5xl").inner_text() == "فحص الحساس"
    assert "مطابق تمامًا" in page.content()


def test_simulation_compare_and_add(page):
    go(page, "simulation")
    page.wait_for_selector("text=مقارنة السيناريوهات")
    rows = page.locator("text=مقارنة السيناريوهات >> xpath=ancestor::section//tbody/tr")
    assert rows.count() == 3
    page.click("button:has-text('+ سيناريو')")
    page.locator("input[aria-label='الكمية']").last.fill("70")
    page.click("button:has-text('شغّلي المحاكاة')")
    page.wait_for_selector("tbody b:has-text('سيناريو 4')", timeout=15000)
    assert page.locator("tbody b").count() == 4
    assert "منحنى الاستجابة" in page.content()


def test_model_page_shows_real_metrics_no_accuracy(page):
    go(page, "model")
    m = api(page, "/api/model/metrics")
    dep = next(r for r in m["results"] if r["model_id"] == "rf_selected_deployed")
    body = page.locator("main").inner_text()
    assert f"{dep['rmse']:.5f}" in body and f"{dep['r2']:.3f}" in body
    assert "Accuracy" not in "".join(page.locator(".text-xs.text-muted").all_inner_texts()[:6])
    page.click("button[role=tab]:has-text('تحقق')")
    page.wait_for_function("document.querySelectorAll(\"svg[aria-label='المتنبأ مقابل الفعلي'] circle\").length === 183", timeout=10000)
    page.click("button[role=tab]:has-text('Impurity')")
    assert "انخفاض التباين" in page.locator("main").inner_text()


def test_history_filter_and_detail(page):
    go(page, "history")
    page.select_option("select >> nth=1", "Z02")
    page.select_option("select >> nth=2", "CHECK_SENSOR")
    page.select_option("select >> nth=0", "simulation")
    page.click("button:has-text('تطبيق')")
    page.wait_for_function("document.querySelectorAll('tbody tr').length === 1", timeout=10000)
    page.locator("tbody tr").first.click()
    page.wait_for_selector("[role=dialog]")
    assert "D20250315Z02" in page.locator("[role=dialog]").inner_text()
    page.click("[role=dialog] button:has-text('إغلاق')")
    page.click("button:has-text('مسح')")
    page.wait_for_load_state("networkidle")
    page.click("nav[aria-label='الصفحات'] >> text=التالي")
    page.wait_for_load_state("networkidle")
    assert "صفحة 2" in page.locator("main").inner_text()


def test_site_gallery_images_and_lightbox(page):
    go(page, "site")
    page.wait_for_selector("text=الصور الميدانية")
    for _ in range(12):
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(120)
    page.wait_for_timeout(800)
    loaded = page.evaluate("[...document.querySelectorAll('main img')].filter(i => i.complete && i.naturalWidth > 0).length")
    assert loaded == 24  # 12 صورة أصلية في المعرض + 12 صورة معالجة في قسم تحليل الصور
    page.locator("button:has(img)").first.click()
    page.wait_for_selector("[role=dialog] img")
    assert page.evaluate("document.querySelector('[role=dialog] img').naturalWidth") > 1000
    page.keyboard.press("Escape")
    assert page.locator("[role=dialog]").count() == 0


def test_mobile_layout_menu(page):
    page.set_viewport_size({"width": 390, "height": 844})
    go(page, "dashboard")
    page.click("button:has-text('القائمة')")
    page.click("#nav a[href='#/history']")
    page.wait_for_load_state("networkidle")
    assert page.locator("h1").inner_text() == "السجل"
    page.set_viewport_size({"width": 1366, "height": 900})


def test_v2_page_whatif(page):
    go(page, "v2")
    page.wait_for_selector("text=جرّبي النموذج الثاني")
    m = api(page, "/api/v2/metrics")
    dep = next(r for r in m["results"] if r["model_id"] == "rf_deployed")
    assert f"{dep['r2']:.3f}" in page.locator("main").inner_text()
    assert page.locator("svg[aria-label='v2 المتنبأ مقابل الفعلي'] circle").count() == 433
    page.wait_for_selector("text=المسجلة في الملف")
    vol = page.locator("label:has-text('الكمية المخططة') input")
    vol.fill("0")
    page.click("button:has-text('احسبي الرطوبة بعد 6 ساعات')")
    page.wait_for_selector("text=المدخلات المغيّرة")
    assert "planned_volume_L" in page.locator("main").inner_text()
    page.select_option("select", "Z001")
    page.wait_for_function("document.querySelector('main').innerText.includes('E') && !document.querySelector('main').innerText.includes('المدخلات المغيّرة')", timeout=10000)
    assert page.errors == [], page.errors
