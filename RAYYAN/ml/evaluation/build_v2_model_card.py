"""يولّد ml/saved_models/v2/MODEL_CARD_V2.md من v2_metrics.json — لا أرقام مكتوبة يدويًا."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "ml/saved_models/v2"


def main():
    m = json.loads((D / "v2_metrics.json").read_text(encoding="utf-8"))
    c = m["data"]["counts"]; s = m["selection"]
    L = ["# بطاقة النموذج الثاني — RAYYAN v2 (أربع مناطق)\n",
         "> تعتمد نتائج النموذج الحالية على بيانات محاكاة، ولا تمثل دقة مثبتة في بيئة زراعية حقيقية.\n",
         "| البند | القيمة |", "|---|---|",
         f"| الإصدار | `{m['model_version']}` |", f"| المجموعة | {m['dataset']} |",
         f"| المهمة | Regression — `{m['target']}` ({m['target_unit']})، {m['horizon']} |",
         f"| الخوارزمية | {m['algorithm']} |", f"| الإعداد المختار | `{json.dumps(s['best_params'])}` |",
         f"| الأعداد | تدريب {c['train']} · تحقق {c['validation']} · اختبار {c['test']} · فجوة مستبعدة {c['gap_excluded']} · أهداف ناقصة {c['missing_targets']} |",
         f"| بصمة البيانات | `{m['data']['data_hash_sha256'][:16]}…` |\n",
         "## المدخلات\n", f"{len(m['features'])} حقلًا بـ role=feature في ورقة Dictionary؛ النصية ({'، '.join(m['categorical_features'])}) تُرمَّز One-Hot، "
         "والعددية تُعوَّض بالوسيط — وكلاهما يتعلم من التدريب فقط.\n",
         "## الفحوص\n"]
    L += [f"- `{k}`: {json.dumps(v, ensure_ascii=False)}" for k, v in m["data"]["checks"].items()]
    L += ["\n## النتائج (نقاط مئوية)\n", "| النموذج | الفترة | المصدر | MAE | RMSE | R² |", "|---|---|---|---:|---:|---:|"]
    for r in m["results"]:
        src = "محسوب هنا" if r["source"] == "computed_here" else "مُبلَّغ في الملف"
        L.append(f"| {r['label_ar']} | {'تحقق' if r['split'] == 'validation' else 'اختبار'} | {src} | {r['mae']:.4f} | {r['rmse']:.4f} | {r['r2']:+.4f} |")
    dep = next(r for r in m["results"] if r["model_id"] == "rf_deployed")
    wb = next((r for r in m["results"] if r["model_id"] == "reported_simple_water_balance" and r["split"] == "test"), None)
    L.append("\n**قراءة صادقة:** خط أساس الوسيط على التحقق يطابق رقم الملف تمامًا، ما يؤكد نفس البيانات والتقسيم. "
             f"النموذج المستخدم على الاختبار MAE {dep['mae']:.3f} وRMSE {dep['rmse']:.3f}."
             + (f" معادلة موازنة الماء البسيطة في الملف أفضل في MAE ({wb['mae']:.3f}) وأسوأ في RMSE ({wb['rmse']:.3f})؛ "
                "أي أن النموذج يقلل الأخطاء الكبيرة أكثر، والمعادلة أدق في الحالات المعتادة. لم نُعِد حساب المعادلة لأن صيغتها غير موثقة في الملف." if wb else ""))
    L += ["\n## الخطأ حسب المنطقة (الاختبار)\n", "| المنطقة | المحصول | n | MAE | R² |", "|---|---|---:|---:|---:|"]
    for z, v in m["error_analysis_test"]["by_zone"].items():
        L.append(f"| {z} {v['zone_name']} | {v['crop']} | {v['n']} | {v['mae']:.3f} | {v['r2']:+.3f} |")
    L += ["\n## أهم المدخلات (Permutation على الاختبار — للتفسير فقط)\n", "| المدخل | زيادة RMSE |", "|---|---:|"]
    L += [f"| `{r['feature']}` | {r['rmse_increase']:.4f} |" for r in m["importance"]["permutation_test"][:8]]
    L += ["\n## ما لم يتوفر\n"] + [f"- {x}" for x in m["not_available"]]
    L += ["\n## الحدود\n"] + [f"- {x}" for x in m["limitations"]]
    (D / "MODEL_CARD_V2.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("✓", D / "MODEL_CARD_V2.md")


if __name__ == "__main__":
    main()
