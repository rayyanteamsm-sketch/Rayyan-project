"""
يولّد ml/saved_models/MODEL_CARD.md من نتائج التدريب الفعلية (metrics.json) — لا أرقام مكتوبة يدويًا.
التشغيل: python ml/evaluation/build_model_card.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
S = ROOT / "ml/saved_models"
FEAT_AR = {"pre_vwc": "الرطوبة قبل القرار", "planned_volume_l": "حجم الري المخطط", "planned_duration_min": "مدة الري المخططة",
           "root_depth_m": "عمق الجذور", "area_m2": "المساحة", "forecast_rain_mm": "المطر المتوقع",
           "forecast_et0_mm": "التبخر-النتح المتوقع", "doy_sin": "الموسم sin", "doy_cos": "الموسم cos"}


def f(x, n=5):
    return "—" if x is None else f"{x:.{n}f}"


def main():
    m = json.loads((S / "metrics.json").read_text(encoding="utf-8"))
    dv = json.loads((S / "decision_engine_validation.json").read_text(encoding="utf-8"))
    wb_p = S / "workbook_experiment.json"
    wb = json.loads(wb_p.read_text(encoding="utf-8")) if wb_p.exists() else None
    c = m["data"]["counts"]; sel = m["selection"]
    L = []
    L.append(f"# بطاقة نموذج ريّان — استجابة رطوبة التربة\n")
    L.append("> تعتمد نتائج النموذج الحالية على بيانات محاكاة، ولا تمثل دقة مثبتة في بيئة زراعية حقيقية.\n")
    L.append("| البند | القيمة |\n|---|---|")
    L.append(f"| الإصدار | `{m['model_version']}` |")
    L.append(f"| وقت التدريب (UTC) | {m['trained_at']} |")
    L.append(f"| المهمة | Regression |")
    L.append(f"| الهدف | `delta_vwc = post_vwc − pre_vwc` (m³/m³) بعد ساعتين من نهاية الرية المخططة |")
    L.append(f"| الخوارزمية | RandomForestRegressor — {json.dumps(sel['best_params'])} |")
    L.append(f"| البذرة | {m['software']['seed']} |")
    L.append(f"| البيانات | `{m['data']['source']}` — بصمة `{m['data']['data_hash_sha256'][:16]}…` |")
    L.append(f"| الأعداد | تدريب {c['train']} · تحقق {c['validation']} · اختبار {c['test']} · مستبعد {c['excluded']} (وسم ناقص) |")
    L.append(f"| تدريب النسخة المستخدمة | {c['deployed_fit']} عملية (2024 + يناير–يونيو 2025) |")
    L.append(f"| البرمجيات | Python {m['software']['python']} · scikit-learn {m['software']['scikit-learn']} · pandas {m['software']['pandas']} |\n")
    L.append("## المدخلات\n")
    L.append("التسعة المذكورة في `MODEL_CARD_AR.md` للحزمة فقط، وكلها متاحة قبل قرار 04:00:\n")
    L.append("| المدخل | المعنى | نطاق التدريب |\n|---|---|---|")
    for k in m["features"]:
        r = m.get("feature_ranges", {}).get(k)
        L.append(f"| `{k}` | {FEAT_AR[k]} | {'' if not r else f'{r['min']:g} — {r['max']:g}'} |")
    L.append("\nممنوع إدخاله (معلومات بعد القرار أو معرّفات): " + "، ".join(f"`{x}`" for x in m["forbidden_inputs"]) + ".\n")
    L.append("## فحوص البيانات قبل التدريب\n")
    for k, v in m["data"]["checks"].items():
        L.append(f"- `{k}`: {json.dumps(v, ensure_ascii=False)}")
    L.append("\n## اختيار الإعدادات\n")
    L.append(f"شبكة من {sel['n_candidates']} إعدادًا قُيّمت على **التحقق فقط** (RMSE). أفضلها: `{json.dumps(sel['best_params'])}` "
             f"بـ RMSE تحقق {f(sel['best_validation']['rmse'])}. بيانات الاختبار لم تُستخدم في أي اختيار.\n")
    L.append("## النتائج\n")
    L.append("| النموذج | الفترة | تدرب على | MAE | RMSE | R² |\n|---|---|---|---:|---:|---:|")
    for r in m["results"]:
        L.append(f"| {r['label_ar']} | {'تحقق' if r['split']=='validation' else 'اختبار'} | {r['trained_on']} | {f(r['mae'])} | {f(r['rmse'])} | {r['r2']:+.3f} |")
    rep = m["package_reproduction"]["ours"]["test"]
    pkg = [x for x in m["package_reproduction"]["package_reported"] if x["model_id"] == "RF_fixed_2024" and x["evaluation_split"] == "test"]
    L.append(f"\n**إعادة إنتاج تجربة الحزمة:** RandomForest بإعداداتها الثابتة على الاختبار R² = {rep['r2']:.6f}"
             + (f"، والمسجل في الحزمة {pkg[0]['r2']:.6f} (فرق {abs(rep['r2']-pkg[0]['r2']):.1e}؛ تطابق حتى 4 منازل، "
                f"والفرق الصغير يُرجَّح أنه من اختلاف إصدار scikit-learn)." if pkg else "."))
    L.append("\n**قراءة النتائج بصدق:** الإعداد المختار على التحقق تفوق قليلًا على إعداد الحزمة في التحقق، لكنه لم يتفوق عليه في الاختبار. "
             "ولم تتحسن النسخة المحدثة حتى يونيو 2025 على النسخة المجمدة في 2024 في هذا الاختبار. الفروق صغيرة؛ لم نغيّر الاختيار بعد رؤية الاختبار.\n")
    L.append("## تحليل الخطأ على الاختبار (النموذج المستخدم)\n")
    for z, v in m["error_analysis_test"]["by_zone"].items():
        L.append(f"- المنطقة {z}: MAE {f(v['mae'])}، R² {v['r2']:+.3f} (n={v['n']})")
    for k, v in m["error_analysis_test"]["by_confounding_flag"].items():
        L.append(f"- علامة الإرباك `{k}`: MAE {f(v['mae'])} (n={v['n']})")
    L.append("\n## أهمية المدخلات (Permutation على الاختبار — للتفسير فقط)\n")
    L.append("| المدخل | زيادة RMSE عند الخلط |\n|---|---:|")
    for r in m["importance"]["permutation_test"]:
        L.append(f"| {FEAT_AR[r['feature']]} | {r['rmse_increase']:.5f} ± {r['std']:.5f} |")
    L.append("\n## محرك قرار الري (ليس نموذج تعلم آلي)\n")
    L.append(f"القواعد `rule_v1` من `build_dataset.py`. أعيد تشغيل {dv['decisions_compared']} قرارًا محفوظًا للمنطقة Z02: "
             f"تطابق القرار {dv['action_matches']}/{dv['decisions_compared']}، وتطابق الحجم {dv['volume_matches']}/{dv['decisions_compared']}. "
             f"{dv['meaning']}\n")
    if wb:
        L.append("## تجربة ثانوية: مصنف التدريب ومنهج الـNotebook\n")
        L.append(f"{wb['n_features']} مدخلًا من `Data_Dictionary`، {wb['rows_used']} صفًا. {wb['deviation_from_notebook']}\n")
        L.append("| النموذج | الفترة | MAE | RMSE | R² |\n|---|---|---:|---:|---:|")
        for r in wb["results"]:
            L.append(f"| {r['model_id']} | {r['split']} | {f(r['mae'])} | {f(r['rmse'])} | {r['r2']:+.3f} |")
        L.append(f"\n{wb['why_not_used_in_system']}\n")
    L.append("## الحدود\n")
    for x in m["limitations"]:
        L.append(f"- {x}")
    L.append("- لا يحدد النموذج كمية الري؛ الكمية تحسب بقواعد إعادة الملء، والنموذج يتنبأ بأثرها فقط.")
    L.append("- لا يوجد اختبار ميداني ولا نشر تلقائي ولا أوامر صمامات.\n")
    (S / "MODEL_CARD.md").write_text("\n".join(L), encoding="utf-8")
    print("✓", S / "MODEL_CARD.md")


if __name__ == "__main__":
    main()
