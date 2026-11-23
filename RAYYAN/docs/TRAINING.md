# طريقة تدريب النماذج

> تعتمد نتائج النموذج الحالية على بيانات محاكاة، ولا تمثل دقة مثبتة في بيئة زراعية حقيقية.

## ما الذي يُدرَّب وما الذي لا يُدرَّب

| المكوّن | النوع | لماذا |
|---|---|---|
| استجابة رطوبة التربة `delta_vwc` | **Random Forest Regression** — يُدرَّب | الهدف كمية متصلة لها Labels محاكاة صالحة (769 عملية)، كما في `MODEL_CARD_AR.md` بالحزمة. |
| قرار الري IRRIGATE / DEFER / CHECK_SENSOR | **محرك قواعد** — لا يُدرَّب | لا توجد Labels مستقلة تثبت صحة القرار. القرارات المحفوظة نفسها ناتجة عن قواعد `rule_v1` في `build_dataset.py`؛ تدريب مصنف عليها يعني تعلّم القواعد بطريقة أقل شفافية. |
| كمية المياه | **معادلة إعادة الملء** — لا تُدرَّب | `README_AR.md` بالحزمة: «لا تحتاج توصية اللترات إلى ML مبدئيًا». اللترات المنفذة ليست Label لجرعة مثلى. |

## التشغيل

```bash
python scripts/prepare_data.py                    # مرة واحدة: فك الملف الأصلي والتحقق من البصمات ونسخ القاعدة
python ml/training/train_response_model.py        # التدريب والتقييم وحفظ النموذج (~40 ثانية)
python ml/training/train_workbook_experiment.py   # التجربة الثانوية على مصنف التدريب (~15 ثانية)
python ml/evaluation/validate_decision_engine.py  # التحقق من محرك القرار
python ml/evaluation/build_model_card.py          # توليد MODEL_CARD.md من النتائج
python ml/training/train_v2_model.py              # النموذج الثاني — مجموعة v2 (~60 ثانية)، انظري docs/V2_DATASET.md
python ml/evaluation/build_v2_model_card.py
```
أو كل ذلك بأمر واحد: `python scripts/run.py --setup-only --rebuild`.

## البيانات

المصدر: قاعدة `data/database/rayyan.sqlite` (نسخة تطوير مطابقة لقاعدة الحزمة)، الجداول:

- `ml_features` — 770 صفًا، المدخلات المجمدة وقت القرار.
- `ml_targets` — 770 صفًا، `delta_vwc` ووقت إتاحة الوسم وحالته.
- `split_manifest` — 770 صفًا، `split` و`eligible`.
- `decisions.predicted_delta_vwc` — التقريب الخطي الذي حسبه المحاكي وقت القرار، يُستخدم **خط أساس** فقط.

الربط `decision_id` واحد-لواحد بين الجداول الثلاثة (يُفحص بـ `validate="1:1"`). يُستبعد صف واحد: `eligible=False` ووسم ناقص.

## المدخلات (9 فقط، من Model Card الحزمة)

`pre_vwc`، `planned_volume_l`، `planned_duration_min`، `root_depth_m`، `area_m2`، `forecast_rain_mm`، `forecast_et0_mm`، `doy_sin`، `doy_cos`.

ممنوع إدخاله لأنه يُعرف بعد القرار أو معرّف: `delivered_volume_l`، `actual_end`، `post_vwc`، `delta_vwc`، `scenario_id`، `confirmed_cause`، الطقس المتحقق، `decision_id`، `zone_id`، `issued_at`، `input_sample_id`، `forecast_id`، `features_available_at`.

## فحوص منع التسرب (تُنفَّذ قبل التدريب، والتدريب يتوقف إن فشل أي منها)

1. لا تقاطع بين قائمة المدخلات والقائمة الممنوعة.
2. `features_available_at ≤ issued_at` لكل صف.
3. آخر `label_available_at` في التدريب قبل أول قرار في التحقق.
4. آخر `label_available_at` في التحقق قبل أول قرار في الاختبار.
5. لا قيم مفقودة في مدخلات الصفوف المؤهلة.

## التقسيم الزمني (دون تغيير)

| الجزء | الفترة | العدد |
|---|---|---:|
| تدريب | 2024-01-01 — 2024-12-30 | 384 |
| تحقق | 2025-01-01 — 2025-06-30 | 183 |
| اختبار | 2025-07-01 — 2025-12-31 | 202 |

## اختيار الإعدادات — على التحقق فقط

شبكة `n_estimators ∈ {200, 400}` × `max_depth ∈ {None, 6, 10}` × `min_samples_leaf ∈ {1, 3, 5}` × `max_features ∈ {1.0, 0.6, sqrt}` (54 إعدادًا) + إعداد الحزمة الثابت (80، 8، 4) = 55 مرشحًا. كل مرشح يُدرَّب على 2024 ويُقيَّم بـ RMSE على التحقق. الفائز: `n_estimators=400, max_depth=6, min_samples_leaf=3, max_features=1.0`. **بيانات الاختبار لا تدخل أي خطوة من هذا.**

## النماذج الناتجة

- `rf_selected_frozen`: الإعداد الفائز مدرب على 2024 فقط.
- `rf_selected_deployed`: نفس الإعداد مدرب على 2024 + يناير–يونيو 2025 (567 عملية) — **هذا ما يستخدمه النظام**، لأنه يستخدم كل البيانات المتاحة قبل فترة الاختبار.
- `rf_package_fixed`: إعادة إنتاج تجربة الحزمة للتحقق من سلامة القراءة.

## المخرجات (`ml/saved_models/`)

| الملف | المحتوى |
|---|---|
| `response_model.joblib` | النموذج + قائمة المدخلات + نطاقات التدريب (لتحذيرات الاستقراء) + الإصدار والبذرة |
| `metrics.json` | كل المقاييس والفحوص والاختيار وتحليل الخطأ والأهمية — مصدر كل رقم في الواجهة |
| `predictions.csv` + جدول `app_model_predictions` | تنبؤ لكل عملية مؤهلة مع علامة خارج/داخل العينة |
| `MODEL_CARD.md` | بطاقة النموذج المولدة آليًا |
| `workbook_experiment.json` | التجربة الثانوية |
| `decision_engine_validation.json` | نتيجة التحقق من المحرك |

## قابلية إعادة الإنتاج

- البذرة `20261107` من `config.json` بالحزمة، وبصمة SHA-256 للبيانات المستخدمة محفوظة في `metrics.json`.
- اختبار `tests/integration/test_fresh_start.py` يعيد كل شيء من الملف الأصلي في مجلد فارغ ويتحقق أن المقاييس تطابق المحفوظة حتى دقة الفاصلة العائمة (`rel=1e-9`).
- الإصدارات المختبرة في `requirements.txt`. إن تعذر تحميل `joblib` بإصدار مختلف من scikit-learn، يعيد الخادم تدريب النموذج تلقائيًا بالإعدادات المحفوظة ويعلن ذلك في `/api/health` (الحقل `source = retrained_local`).

## التجربة الثانوية (منهج الـNotebook المرفق)

`Untitled19.ipynb` يدرب RandomForest وXGBoost على ورقة `VWC_Response` في مصنف التدريب (23 مدخلًا من `Data_Dictionary`، 1,272 صفًا، فترات train/validation/test/stress_test). أعدنا المنهج نفسه بـ RandomForest فقط لأن XGBoost غير مثبت في بيئة التطوير. هذا المصنف **لا يُستخدم في النظام** لأن معرّفاته (`DRAY…`) لا ترتبط بقاعدة SQLite، ومعاملات المناطق فيه (تدفق 1 ل/د، أحجام 9.5/39/45 لترًا، أهداف 0.105/0.145) تختلف عن الحزمة (2 ل/د، 16–80 لترًا، FC 0.15).
