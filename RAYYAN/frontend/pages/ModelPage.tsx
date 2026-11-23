import { useState } from "react";
import { api, type MetricRow } from "../services/api";
import { GroupedBars, HBars, LineChart, PALETTE, Scatter } from "../components/charts";
import { ErrorBox, fmt, Loading, OriginTag, Panel, Stat, Tabs, useApi } from "../components/ui";
import type { PageProps } from "./DecisionPage";

const FEAT_AR: Record<string, string> = {
  pre_vwc: "الرطوبة قبل الري", planned_volume_l: "حجم الري", planned_duration_min: "مدة الري", root_depth_m: "عمق الجذور",
  area_m2: "المساحة", forecast_rain_mm: "المطر المتوقع", forecast_et0_mm: "التبخر-النتح المتوقع", doy_sin: "الموسم (sin)", doy_cos: "الموسم (cos)",
};
const SHORT: Record<string, string> = {
  baseline_zero_change: "لا تغير", baseline_train_mean: "المتوسط", baseline_linear_rule: "المعادلة الخطية",
  rf_package_fixed: "RF إعدادات الحزمة", rf_selected_frozen: "RF المختار (2024)", rf_selected_deployed: "RF المستخدم",
};

export default function ModelPage(_: PageProps) {
  const m = useApi(() => api.metrics(), []);
  const eng = useApi(() => api.engine(), []);
  const [split, setSplit] = useState<"test" | "validation">("test");
  const [imp, setImp] = useState<"permutation" | "impurity">("permutation");
  const preds = useApi(() => api.predictions(split), [split]);
  if (m.error) return <ErrorBox message={m.error} onRetry={m.reload} />;
  if (!m.data) return <Loading />;
  const d = m.data, c = d.data.counts;
  const test = d.results.filter((r) => r.split === "test");
  const deployed = test.find((r) => r.model_id === "rf_selected_deployed")!;
  const meanBase = test.find((r) => r.model_id === "baseline_train_mean")!;
  const row = (r: MetricRow) => (
    <tr key={r.model_id + r.split} className={r.model_id === "rf_selected_deployed" ? "bg-water-pale/60 font-medium" : ""}>
      <td>{r.label_ar}</td><td>{r.split === "test" ? "اختبار" : "تحقق"}</td><td className="text-xs text-muted">{r.trained_on}</td>
      <td className="num">{r.n}</td><td className="num">{fmt(r.mae, 5)}</td><td className="num">{fmt(r.rmse, 5)}</td>
      <td className={`num ${r.r2 < 0 ? "text-danger" : ""}`}>{r.r2.toFixed(3)}</td>
    </tr>
  );
  return (
    <div className="space-y-5">
      <div className="panel grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-6">
        <Stat label="نوع النموذج" value="Random Forest" hint="RandomForestRegressor" />
        <Stat label="نوع المهمة" value="Regression" hint={`الهدف: ${d.target} (${d.target_unit})`} />
        <Stat label="بيانات التدريب" value={c.train} hint={`+ تحقق ${c.validation} = ${c.deployed_fit} للنسخة المستخدمة`} />
        <Stat label="بيانات الاختبار" value={c.test} hint="يوليو–ديسمبر 2025، لم تُلمس" />
        <Stat label="RMSE على الاختبار" value={fmt(deployed.rmse, 5)} tone="water" hint={`المتوسط: ${fmt(meanBase.rmse, 5)}`} />
        <Stat label="R² على الاختبار" value={deployed.r2.toFixed(3)} tone="water" hint={`MAE ${fmt(deployed.mae, 5)}`} />
      </div>
      <p className="text-sm text-muted">مقاييس Regression فقط (MAE وRMSE بوحدة m³/m³، وR² بلا وحدة). لا تُعرض Accuracy لأنها لا تنطبق على مهمة انحدار. الأرقام مقروءة من <span className="font-mono">ml/saved_models/metrics.json</span> كما أنتجها التدريب.</p>

      <div className="grid gap-5 lg:grid-cols-[1.25fr_1fr]">
        <Panel title="المقارنة مع خطوط الأساس" subtitle="RMSE على فترة الاختبار — الأقل أفضل" actions={<OriginTag kind="derived" />}>
          <GroupedBars categories={test.map((r) => SHORT[r.model_id])} yFormat={(v) => v.toFixed(3)} yLabel="RMSE" height={230}
            series={[{ name: "RMSE اختبار", color: PALETTE.water, values: test.map((r) => r.rmse) }]} />
          <div className="mt-3 overflow-x-auto">
            <table className="tbl min-w-[620px]"><thead><tr><th>النموذج</th><th>الفترة</th><th>تدرب على</th><th>n</th><th>MAE</th><th>RMSE</th><th>R²</th></tr></thead>
              <tbody>{d.results.map(row)}</tbody></table>
          </div>
          <p className="mt-2 text-xs text-muted">«لا تغير» يفترض Δ=0؛ «المتوسط» يتنبأ بمتوسط فترة التدريب؛ «المعادلة الخطية» هي decisions.predicted_delta_vwc التي يحسبها المحاكي وقت القرار. R² السالب يعني أسوأ من التنبؤ بالمتوسط.</p>
        </Panel>
        <Panel title="المتنبأ مقابل الفعلي" subtitle="كل نقطة رية؛ الخط المتقطع = تطابق تام"
          actions={<Tabs value={split} onChange={setSplit} items={[["test", "اختبار"], ["validation", "تحقق"]]} />}>
          {preds.error && <ErrorBox message={preds.error} />}
          {preds.data ? (
            <Scatter label="المتنبأ مقابل الفعلي" points={preds.data.items.map((p) => ({ x: p.actual_delta_vwc, y: p.predicted_delta_vwc, id: p.decision_id,
              color: p.zone_id === "Z01" ? PALETTE.ochre : PALETTE.water, extra: p.confounding_flags && p.confounding_flags !== "none" ? `إرباك: ${p.confounding_flags}` : undefined }))} />
          ) : <Loading />}
          <p className="text-xs text-muted"><span style={{ color: PALETTE.ochre }}>●</span> المنطقة الأولى (جدول ثابت 40/60 لترًا) · <span style={{ color: PALETTE.water }}>●</span> المنطقة الثانية (قواعد ريّان). {split === "validation" ? "التحقق بنموذج 2024 المجمد (خارج العينة)." : "الاختبار بالنموذج المستخدم (خارج العينة)."}</p>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="أهمية المدخلات" actions={<Tabs value={imp} onChange={setImp} items={[["permutation", "Permutation"], ["impurity", "Impurity"]]} />}
          subtitle={imp === "permutation" ? "زيادة RMSE على الاختبار عند خلط المدخل (20 تكرارًا)" : "انخفاض التباين داخل أشجار النموذج"}>
          {imp === "permutation"
            ? <HBars items={d.importance.permutation_test.map((r) => ({ label: FEAT_AR[r.feature], value: r.rmse_increase, err: r.std }))} format={(v) => v.toFixed(5)} />
            : <HBars items={d.importance.impurity.map((r) => ({ label: FEAT_AR[r.feature], value: r.importance }))} format={(v) => v.toFixed(3)} color={PALETTE.turf} />}
          <p className="mt-2 text-xs text-muted">{d.importance.note}. عمق الجذور والمساحة ثابتان في البيانات فلا أثر لهما.</p>
        </Panel>
        <Panel title="الخطأ حسب الشهر — الاختبار" subtitle="متوسط Δ الفعلي مقابل المتنبأ ومتوسط الخطأ المطلق">
          <LineChart yFormat={(v) => v.toFixed(4)} height={220} series={[
            { name: "متوسط الفعلي", color: PALETTE.soil, points: d.error_analysis_test.by_month.map((r) => ({ x: new Date(r.month + "-15"), y: r.mean_actual })) },
            { name: "متوسط المتنبأ", color: PALETTE.water, points: d.error_analysis_test.by_month.map((r) => ({ x: new Date(r.month + "-15"), y: r.mean_pred })) },
            { name: "MAE", color: PALETTE.ochre, dashed: true, points: d.error_analysis_test.by_month.map((r) => ({ x: new Date(r.month + "-15"), y: r.mae })) },
          ]} />
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
            {Object.entries(d.error_analysis_test.by_zone).map(([z, v]) => <div key={z} className="rounded bg-mist p-2">{z}: MAE <span className="num">{fmt(v.mae, 5)}</span> · R² <span className="num">{v.r2.toFixed(3)}</span> (n={v.n})</div>)}
            {Object.entries(d.error_analysis_test.by_confounding_flag).map(([k, v]) => <div key={k} className="rounded bg-mist p-2">إرباك «{k}»: MAE <span className="num">{fmt(v.mae, 5)}</span> (n={v.n})</div>)}
          </div>
        </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="معلومات التدريب">
          <table className="tbl table-fixed [&_td]:break-words [&_td:first-child]:w-28 [&_td:first-child]:text-muted"><tbody>
            <tr><td>الإصدار</td><td className="font-mono text-xs">{d.model_version}</td></tr>
            <tr><td>وقت التدريب</td><td><span className="num">{d.trained_at.replace("T", " ").replace("+00:00", "")}</span> UTC</td></tr>
            <tr><td>المصدر</td><td className="font-mono text-xs break-all" dir="ltr">{d.data.source}</td></tr>
            <tr><td>بصمة البيانات</td><td className="font-mono text-xs">{d.data.data_hash_sha256.slice(0, 24)}…</td></tr>
            <tr><td>المدخلات</td><td className="text-xs">{d.features.map((f) => FEAT_AR[f]).join("، ")}</td></tr>
            <tr><td>التقسيم</td><td className="text-xs">زمني من split_manifest دون تغيير: 2024 تدريب · يناير–يونيو 2025 تحقق · يوليو–ديسمبر 2025 اختبار</td></tr>
            <tr><td>اختيار الإعدادات</td><td className="text-xs">{d.selection.n_candidates} إعدادًا على التحقق فقط؛ الأفضل: <span className="num font-mono break-all">{Object.entries(d.selection.best_params).map(([k, v]) => `${k}=${v}`).join(", ")}</span></td></tr>
            <tr><td>إعادة إنتاج الحزمة</td><td className="text-xs">R² اختبار بإعدادات الحزمة <span className="num">{d.package_reproduction.ours.test.r2.toFixed(4)}</span> مقابل المسجل <span className="num">{d.package_reproduction.package_reported.find((x) => x.model_id === "RF_fixed_2024" && x.evaluation_split === "test")?.r2.toFixed(4)}</span></td></tr>
            <tr><td>الفحوص</td><td className="text-xs"><ul className="font-mono" dir="ltr">{Object.entries(d.data.checks).filter(([, v]) => typeof v === "boolean").map(([k, v]) => <li key={k}>{v ? "✓" : "✗"} {k}</li>)}</ul></td></tr>
            <tr><td>البرمجيات</td><td className="text-xs">Python {String(d.software.python)} · scikit-learn {String(d.software["scikit-learn"])} · seed {String(d.software.seed)}</td></tr>
            <tr><td>حالة التشغيل</td><td className="text-xs">{d.runtime.source === "joblib" ? "حُمل من joblib عند تشغيل الخادم" : `أعيد تدريبه محليًا: ${d.runtime.error}`}</td></tr>
          </tbody></table>
        </Panel>
        <div className="space-y-5">
          <Panel title="محرك قرار الري" subtitle="ليس نموذج تعلم آلي: قواعد rule_v1 من كود المحاكاة">
            {eng.data ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <Stat label="تطابق القرار مع المحاكي" value={`${eng.data.action_matches}/${eng.data.decisions_compared}`} tone="leaf" />
                  <Stat label="تطابق الكمية" value={`${eng.data.volume_matches}/${eng.data.decisions_compared}`} tone="leaf" />
                </div>
                <p className="mt-2 text-xs text-muted">{eng.data.meaning}</p>
              </>
            ) : eng.error ? <ErrorBox message={eng.error} /> : <Loading />}
          </Panel>
          {d.workbook_experiment && (
            <Panel title="تجربة ثانوية: مصنف التدريب" subtitle={`منهج الـNotebook المرفق · ${d.workbook_experiment.n_features} مدخلًا · ${d.workbook_experiment.rows_used} صفًا`}>
              <table className="tbl"><thead><tr><th>النموذج</th><th>الفترة</th><th>RMSE</th><th>R²</th></tr></thead><tbody>
                {d.workbook_experiment.results.map((r) => <tr key={r.model_id + r.split}><td>{r.model_id === "random_forest" ? "Random Forest" : "المتوسط"}</td><td>{r.split === "test" ? "اختبار" : "إجهاد"}</td><td className="num">{fmt(r.rmse, 5)}</td><td className="num">{r.r2.toFixed(3)}</td></tr>)}
              </tbody></table>
              <p className="mt-2 text-xs text-muted">{d.workbook_experiment.deviation_from_notebook} {d.workbook_experiment.why_not_used_in_system}</p>
            </Panel>
          )}
        </div>
      </div>
      <Panel title="حدود النموذج">
        <ul className="list-disc space-y-1 ps-5 text-sm">{d.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Panel>
    </div>
  );
}
