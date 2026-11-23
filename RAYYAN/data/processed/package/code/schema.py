"""Explicit bilingual column definitions. Missing a definition is a build error."""
from pathlib import Path
import csv

# name | Arabic precise definition | logical type | unit | acceptable values | nullable | use
TEXT = r'''
weather_id|معرف ساعة وخلية إعادة التحليل|String|none|unique nonempty|no|ربط forcing بالتحليل
site_id|معرف ثابت للموقع|String|none|SITE01 in simulation; valid FK|no|ربط المناطق والموازنة والطقس
zone_id|معرف منطقة الري؛ قد يغيب في حادث على مستوى الموقع|String|none|Z01/Z02; valid FK|yes|الربط المكاني والتجريبي
interval_start_at|بداية فترة تراكم المطر وET0 والإشعاع؛ ليست وقت الإتاحة|Datetime|UTC ISO8601|start < interval_end_at|no|توحيد نافذة الطقس
interval_end_at|نهاية الفترة؛ المتغيرات اللحظية كالحرارة تمثل هذه اللحظة|Datetime|UTC ISO8601|hourly increasing|no|مطابقة الساعة مع forcing
temperature_c|درجة حرارة الهواء على ارتفاع2م؛ لحظية في إعادة التحليل ومتوسط24ساعة في التوقع المحاكى|Float|degC|-40..65|no|التحليل والعامل الموسمي
humidity_pct|رطوبة الهواء النسبية وليست رطوبة التربة|Float|percent|0..100|no|وصف مناخ المصدر
rain_mm|مطر متراكم في فترة الصف: ساعة/يوم/توقع24ساعة حسب الجدول|Float|mm|>=0|no|مدخل الموازنة وتقدير المطر
et0_mm|تبخر نتح مرجعي محسوب لدى المزوّد أو متوقع محاكى، متراكم في فترة الصف|Float|mm|>=0|no|حساب طلب الماء بالتكامل
solar_w_m2|متوسط الإشعاع الشمسي للساعة السابقة من إعادة التحليل|Float|W/m2|>=0|no|تفسير طقس المصدر
wind_m_s|سرعة الرياح على ارتفاع10م عند نهاية الساعة|Float|m/s|>=0|no|وصف طقس المصدر؛ لا تساوي رياح2م تلقائيًا
grid_latitude_deg|مركز خلية الطقس الذي أعادهAPI، وليس إحداثي الحساس|Float|degree WGS84|-90..90|no|توثيق الدقة المكانية
grid_longitude_deg|خط طول مركز خلية المصدر|Float|degree WGS84|-180..180|no|توثيق الدقة المكانية
available_at|وقت أول إتاحة مسجلة/محاكية للنظام؛ الطقس المرجعي متاح عند التنزيل2026 وليس تاريخ الحدث|Datetime|UTC ISO8601|>= event/issued timestamp as relevant|no|منع استخدام معلومات قبل وصولها
source_id|معرف المصدر؛ إذا تعدد يفصل بفاصلة منقوطة في التوثيق|String|none|source registry IDs|no|تتبع المصدر
product_type|نوع المنتج؛ يميز reanalysis عن synthetic_forecast|String|none|reanalysis/synthetic_forecast|no|عدم خلط الرصد بالتوقع
month|رقم شهر السنة للمتوسطات المنشورة لا شهر قياس محدد|Integer|month|1..12|no|ربط موسمية الدراسة
tmin_c|متوسط الحرارة الدنيا الشهري المنشور1985-2010|Float|degC|-40..65|no|مرجع المناخ
tmax_c|متوسط الحرارة العظمى الشهري المنشور1985-2010|Float|degC|-40..65|no|مرجع المناخ
wind_km_day|المتوسط المنشور لمسافة الرياح اليومية؛ ليس كم/ساعة|Float|km/day|>=0|no|حفظ الوحدة الأصلية للدراسة
sunshine_h_day|متوسط ساعات السطوع اليومي خلال الشهر|Float|h/day|0..24|no|مرجع المناخ
locator|رقم الجدول/الصفحة/القسم أو موقع الملف الدقيق|String|none|nonempty source locator|no|إمكانية المراجعة
eto_mm_month|ET0 الشهري المحسوب في الدراسة وفق متوسطاتها|Float|mm/month|>=0|no|حساب مرجعي منشور
kc|معامل محصول شهري اقتبسته/حسبته الدراسة؛ لا قياس نبات محلي|Float|dimensionless|0..2|no|مرجع مشروط للمحاكاة
cwr_mm_month|احتياج محصول مرجعي محسوب Kc مضروبًا فيET0 الشهري|Float|mm/month|>=0|no|مراجعة حسابات الدراسة
iwr_mm_month|احتياج ري الدراسة بعد معامل الغسل المستخدم فيها|Float|mm/month|>=0|no|مرجع حسابي مشروط
irrigation_interval_days|الفاصل المحسوب بين الريات في الدراسة وليس جدول تشغيل الموقع|Float|day|>0|no|مرجع وبيان حدود التعميم
parameter_id|اسم ثابت لمعامل منشور أو افتراض|String|none|nonempty|no|ربط المعامل بشروطه
value_numeric|القيمة الرقمية المنقولة للمعامل بوحدته المحددة|Float|see unit|finite|no|حفظ قيم المصدر
unit|وحدة القيمة كما يحددها المصدر أو التحويل|String|none|explicit unit|no|تجنب خلط المقاييس
value_origin|هل معامل الدراسة مقاس أم مقدر أم مقتبس أم محسوب|String|none|measured/estimated/adopted_literature/calculated/calculated_rounded|no|تمييز أصل الأرقام
limitation_ar|حدود صلاحية المصدر أو القيمة وصعوبة نقلها|String|none|nonempty|no|منع التعميم غير المبرر
site_name|اسم الموقع المقترح مع بيان أنه غير ممسوح|String|none|nonempty|no|تعريف النطاق
timezone|اسم منطقة الوقت وفق IANA|String|none|Asia/Riyadh|no|العرض المحلي مع تخزينUTC
weather_request_latitude|خط عرض نقطة تمثيلية مفترضة للرياض بطلبAPI؛ ليس مركز قطعة مقاس|Float|degree WGS84|-90..90|no|اختيار خلية الطقس المرجعية
weather_request_longitude|خط طول نقطة طلب الطقس التمثيلية|Float|degree WGS84|-180..180|no|اختيار خلية الطقس
coordinate_status|تصنيف مصدر الإحداثي لتجنب نسبته لمسح فعلي|String|none|assumed_representative_Riyadh_point_NOT_surveyed_plot|no|توثيق افتراض مكاني
valid_from|وقت بداية صلاحية النسخة أو نافذة التوقع/الميزانية حسب الجدول|Datetime|UTC ISO8601|< valid_to|no|ربط النسخ والوقت
valid_to|نهاية صلاحية النسخة/النافذة بصورة حصرية|Datetime|UTC ISO8601|> valid_from|no|منع تجاوز نافذة الصلاحية
area_m2|مساحة المنطقة الافتراضية؛ تحتاج قياسًا قبل التشغيل|Float|m2|>0; assumed5|no|تحويل العمق إلى حجم
plant_species|الاسم العلمي للنبات الذي اختاره المستخدم|String|none|Cynodon dactylon|no|نطاق البرمودا
cultivar|صنف البرمودا؛ غير محدد ولا نفترض صنفًا|String|none|confirmed cultivar or NULL|yes|التحقق من تجانس التجربة
irrigation_method|طريقة الري الافتراضية في المحاكاة|String|none|simulated_sprinkler|no|تفسير الكفاءة والتوزيع
trial_arm|أسلوب إدارة المنطقة في المقارنة المصممة|String|none|conventional/rayyan|no|فصل مجموعتي التجربة
profile_id|معرف نسخة خصائص التربة والنبات|String|none|unique or valid FK|no|إعادة إنتاج القرار
soil_texture|قوام التربة المفترض؛ ليس نتيجة عينة مختبر|String|none|loamy_sand_assumed|no|تفسير الافتراضات
root_depth_m|عمق منطقة الجذور الفعال المفترض في المحاكي؛ ليس عمق الحساس|Float|m|>0; assumed0.25|no|تحويل الرطوبة إلى مخزون
field_capacity_vwc|الرطوبة الحجمية عند السعة الحقلية المفترضة|Float|m3/m3|WP < FC < saturation|no|حسابTAW وحدود الري
wilting_point_vwc|الرطوبة الحجمية عند نقطة الذبول المفترضة|Float|m3/m3|0 < WP < FC|no|حساب ماء الجذور المتاح
saturation_vwc|الرطوبة الحجمية عند التشبع المفترض|Float|m3/m3|FC < saturation <1|no|فحص المدى الفيزيائي
depletion_fraction|جزء استنزافTAW قبل الإجهاد في قاعدة المحاكاة|Float|fraction|0..1 exclusive|no|حسابRAW وKs
application_efficiency|جزء جرعة الري الإجمالية الذي يدخل مدخل التربة قبل الجريان والتصريف|Float|fraction|0..1 inclusive positive|no|فصل فقد التطبيق ومنع احتسابه مرتين
nominal_flow_l_min|تدفق تصميم افتراضي لتحديد المدة المخططة|Float|L/min|>0|no|المدة=الحجم المخطط/التدفق الاسمي
response_lag_min|زمن استجابة افتراضي ثابت يضاف إلى النهاية المخططة|Integer|min|>=0; assumed120|no|تثبيت وقتTarget قبل التنفيذ
parameter_basis|مصدر الافتراضات؛ مرجع المنهج لا يثبت القيم الميدانية|String|none|nonempty|no|شفافية المعاملات
device_id|معرف الجهاز الافتراضي في تركيب ثابت|String|none|valid FK/unique|no|ربط الحساس والعداد والصمام
device_type|وظيفة الجهاز الافتراضي|String|none|soil_sensor/flow_meter/valve_relay|no|تفسير القياس
depth_m|عمق حساس التربة المفترض؛ يغيب للعداد والصمام|Float|m|>=0 or NULL|yes|تمييز العمق عن عمق الجذور
installation_status|حالة التركيب؛ كل الأجهزة بالحزمة افتراضية|String|none|virtual_not_installed|no|عدم ادعاء اتصال فعلي
calibration_id|معرف تحويل الخرج الخام إلىVWC|String|none|valid FK/unique|no|تتبع نسخة المعايرة
slope|ميل التحويل الخطي المفترض|Float|m3/m3 per ADC_count|>0;0.0001|no|value=raw*slope+intercept
intercept|مقطع التحويل الخطي المفترض|Float|m3/m3|finite;-0.1|no|تحويل الخام
raw_unit|وحدة الخرج الخام، لا وحدة رطوبة حجمية|String|none|ADC_count|no|تجنب تسمية مؤشر خامVWC
output_unit|وحدة ناتج المعايرة|String|none|m3/m3|no|تفسير القيمة
validation_rmse_vwc|خطأ نقاط تحقق مولدة وفق نفس المعادلة؛ الصفر ليس دقة جهاز|Float|m3/m3|>=0|no|عرض حدود المعايرة الاصطناعية
point_id|معرف نقطة معايرة افتراضية|String|none|unique|no|ربط الخام بالمرجع
raw_adc|الخرج الخام العددي؛ NULL عند فقد payload؛ يبقى الشاذ محفوظًا|Float|ADC_count|0..10000 or NULL;7500 injected spike|yes|التحويل وفحص الخام
reference_vwc|قيمة مرجعية لنقطة المعايرة من حقيقة المحاكي لا المختبر|Float|m3/m3|0..1|no|شرح نموذج التحويل فقط
reference_method|طريقة المرجع المقارن|String|none|simulation_oracle_not_lab|no|تمييز المعايرة الحقيقية
message_id|معرف رسالة النقل، فريد حتى عند تكرار العينة|String|none|unique or valid FK|no|حفظ التكرار بالخام
sample_id|معرف العينة الأصلية؛ يتكرر في رسائل النقل وفريد بالنظيف|String|none|nonempty;unique in clean|no|إزالة تكرار النقل
measured_at|وقت القياس الافتراضي أو نهاية دقيقة عداد التدفق؛ ليس وقت الاستلام|Datetime|UTC ISO8601|in study period;ordered within device|no|ترتيب الحدث
recorded_at|وقت استلام رسالة الخام من الجهاز الافتراضي|Datetime|UTC ISO8601|>= measured_at|no|قياس تأخر الاتصال
calibrated_original_vwc|القيمة الخام المحولة دون قص أو تعويض؛ قد تتجاوز التشبع في اختبار خطأ|Float|m3/m3|finite or NULL;may exceed physical bound|yes|حفظ الأصل بعد التحويل
usable_vwc|قيمة التحليل عند نجاح فحص المدى؛ NULL للخام المفقود أو غير الصالح|Float|m3/m3|0..saturation or NULL|yes|مدخل القرار والوسم
quality_flag|حالة صلاحية قراءة التربة بعد التحويل|String|none|ok/missing/invalid_range|no|فصل الخطأ عن حالة نادرة صحيحة
was_imputed|هل عوضت القراءة؛ جميعهاFalse في هذه الحزمة|Boolean|none|False|no|منع إخفاء القيم المعوضة
injection_id|معرف حقن خلل بيانات للاختبار|String|none|unique|no|تدقيق محاكاة الأخطاء
defect_type|نوع خلل الحقن الاصطناعي|String|none|missing_payload/out_of_range_spike/duplicate_delivery|no|اختبار المعالجة
frequency_basis|تفسير تواتر السيناريو؛ مصمم وليس معدلًا واقعيًا|String|none|nonempty|no|عدم استنتاج انتشار الأعطال
forecast_id|معرف إصدار توقع اصطناعي محفوظ|String|none|unique or valid FK|no|تثبيت توقعات وقت القرار
issued_at|وقت إصدار التوصية/الأمر/التوقع؛ يختلف عن تنفيذه وإتاحته|Datetime|UTC ISO8601|<= available_at for forecasts|no|تجميد حدود معرفة القرار
budget_id|معرف تخصيص الماء لفترة|String|none|unique or valid FK|no|ربط قيد الماء بالخطط
allocated_volume_l|إجمالي الماء المخصص للموقع ضمن نافذة اليوم، ليس مخزون خزان|Float|L|>=0|no|توزيع الماء بين المنطقتين
budget_basis|أصل الميزانية الافتراضية ونوعها|String|none|simulation_allocation_not_measured_storage|no|فصل التخصيص عن الرصيد
decision_id|معرف قرار المنطقة قبل التنفيذ|String|none|unique or valid FK|no|ربط الخطة والأمر والحدث والنتيجة
data_cutoff_at|آخر وقت يسمح فيه باستلام معلومات تدخل القرار|Datetime|UTC ISO8601|=issued_at in v1|no|فحصData Leakage
input_sample_id|معرف عينة التربة المستخدمة عند إصدار القرار؛ قد تغيب عند فقد الاتصال|String|none|valid FK or NULL|yes|تتبعFeature
action|قرار الري أو التأجيل أو طلب الفحص|String|none|irrigate/defer/inspect|no|تنفيذ القواعد
reason|سبب القرار من القواعد المحفوظة|String|none|documented rule code|no|تفسير التوصية
planned_start_at|وقت بدء الري المخطط المحفوظ قبل التنفيذ؛ NULL دون ري|Datetime|UTC ISO8601|>=issued_at or NULL|yes|الجدولة
planned_end_at|وقت نهاية الري المخطط؛ لا يبدل بالنهاية الفعلية|Datetime|UTC ISO8601|>=planned_start_at or NULL|yes|تثبيت وقتTarget
planned_volume_l|حجم خطة القرار قبل التنفيذ؛ الصفر تأجيل أو فحص|Float|L|0..80|no|Feature متاحة، لا كمية مثلى مثبتة
planned_duration_min|مدة الخطة؛ الحجم/التدفق الاسمي بعد التقريب لأسفل|Integer|min|0..40|no|التحكم والجدولة
prediction_target_at|وقت تقييم محدد مسبقًا = النهاية المخططة +120دقيقة؛ NULL دون ري|Datetime|UTC ISO8601|fixed before execution|yes|تجنب اختيار نافذة بعد رؤية النتيجة
predicted_delta_vwc|توقع تقريبي مبسط لفرق الرطوبة؛ ليس وسمًا ميدانيًا|Float|m3/m3|finite or NULL|yes|مقارنة الخطط والمتوقع باللاحق
method_version|معرف ثابت لإصدار القواعد/معادلة التوقع|String|none|documented version|no|إعادة إنتاج القرارات
candidate_id|معرف خطة بديلة مرتبطة بقرار|String|none|unique|no|مقارنة السيناريوهات
candidate_volume_l|جرعة خيار صفر/نصف/كامل من الخطة المختارة|Float|L|>=0|no|محاكاة الخيارات قبل التنفيذ
command_id|معرف أمر المتحكم|String|none|unique|no|تتبع التحكم
command_action|إجراء أمر الصمام|String|none|open/close/emergency_close|no|التسلسل التشغيلي
acknowledged_at|وقت إقرار المتحكم بالاستلام؛ ليس إثبات تدفق ماء|Datetime|UTC ISO8601|>=issued_at|no|قياس استجابة الاتصال
ack_status|حالة الإقرار الافتراضي|String|none|accepted|no|عرض استلام الأمر
physical_valve_state|وضع صمام مقاس بتغذية راجعة مستقلة؛ غير متاح هنا|String|none|open/closed/unknown or NULL|yes|عدم اختلاق إثبات وضع الصمام
evidence_kind|نوع الدليل الذي يدعم حالة التحكم|String|none|relay_ack_only_not_physical_position|no|فصل الأمر عن الحالة الفيزيائية
flow_sample_id|معرف قراءة العداد الافتراضية|String|none|unique|no|مطابقة تكامل التدفق
event_id|معرف محاولة ري منفذة ولو لم يتدفق الماء؛ قد يغيب بحادث مستوى الموقع|String|none|unique or valid FK or NULL|yes|ربط القياس والنتيجة
counter_epoch_id|حقبة عداد ثابتة؛ يتغير عند إعادة الضبط السنوية|String|none|year+zone_id|no|منع طرح قراءات قبل/بعدreset
counter_l|العداد التراكمي الافتراضي ضمن حقبة واحدة|Float|L|>=0 and nondecreasing within epoch|no|قياس حجم التنفيذ
flow_l_min|متوسط التدفق المحاكى للدقيقة السابقة؛ NULL بقراءة البداية|Float|L/min|>=0 or NULL|yes|حساب تكامل الحجم؛ الصفر صالح لفشل الماء
execution_started_at|بداية محاولة تشغيل الري وفق السجل لا إثبات الماء|Datetime|UTC ISO8601|within project period|no|تفسير التنفيذ
execution_ended_at|نهاية محاولة التشغيل الفعلية/إغلاق الطوارئ|Datetime|UTC ISO8601|>execution_started_at|no|مدة التنفيذ، ممنوع كـFeature مسبقة
flow_started_at|وقت وصول الماء الفعلي بالمحاكاة؛ NULL فيno_flow|Datetime|UTC ISO8601|>=execution_started_at or NULL|yes|إثبات الماء مستقل عن الأمر
flow_ended_at|وقت انتهاء تدفق الماء؛ NULL إذا لم يصل الماء|Datetime|UTC ISO8601|>flow_started_at or NULL|yes|مقارنة التنفيذ بالخطة
meter_start_l|قراءة العداد ببداية الحدث وحقبته|Float|L|>=0|no|حساب الحجم المقاس
meter_end_l|قراءة العداد بنهاية الحدث ضمن الحقبة نفسها|Float|L|>=meter_start_l|no|حساب الحجم
delivered_volume_l|حجم الماء المنفذ من فرق العداد أو مجاميع التقرير؛ ليس جرعة مثلى|Float|L|>=0|no|تقييم التنفيذ والتكلفة
volume_method|طريقة قياس حجم الحدث|String|none|counter_difference|no|تتبع الاشتقاق
scenario_id|معرف سيناريو عطل محقون؛ NULL للحالة العادية|String|none|valid FK or NULL|yes|تدقيق فقط، ممنوع كـFeature
event_quality|جودة نموذج العداد المحاكى، لا دقة عداد حقيقي|String|none|simulation_meter_exact_no_noise|no|تحديد حدود الاختبار
outcome_id|معرف نتيجة رية|String|none|unique|no|ربطTarget
pre_sample_id|عينةVWC الأحدث التي وصلت قبل القرار04:00 وليست قراءة مستقبلية قبل الفتح|String|none|valid FK|no|تثبيت بداية فرق الرطوبة
post_sample_ids|قائمة3معرفات عينات عندTarget±5دقائق؛ مفصولة بفاصلة منقوطة|String|none|3 valid sample IDs|no|تتبع حساب الوسم
pre_vwc|قراءةVWC المدخلة عند القرار من الحساس الممثل الافتراضي|Float|m3/m3|0..saturation|no|Feature ومرجع فرق الرطوبة
post_vwc|متوسط العينات الصالحة حول وقتTarget، يشترط2علىالأقل|Float|m3/m3|0..saturation or NULL|yes|حساب الوسم بعد التنفيذ
delta_vwc|Target = post_vwc - pre_vwc؛ فرق حجمي مطلق وليس نسبة تحسن ولا لترات مثلى|Float|m3/m3|-1..1 or NULL|yes|انحدار استجابة التربة، محاكاة فقط
post_valid_count|عدد العينات الصالحة في نافذةTarget|Integer|sample|0..3|no|التحقق من أهلية الوسم
label_available_at|وقت اكتمال استلام/حساب الوسم بعد عينات النتيجة؛ لا يستخدم كـFeature|Datetime|UTC ISO8601|>prediction_target_at|no|تقسيم زمني بلا تسرب
label_status|حالة صلاحيةTarget وحدود أصله|String|none|valid_simulation_only/missing_insufficient_post_samples|no|فصل المفقود عن صفر التغير
confounding_flags|مطر أو عطل داخل نافذة النتيجة؛ مراجعة لاحقة لا مدخل مسبق|String|none|none/rain_window plus optional injected_fault|no|تفسير اختلاف الاستجابة
protocol_version|نسخة بروتوكولTarget أو تقييم النبات؛ proxy النبات غير متحقق|String|none|SIM_SINGLE_SENSOR_V1/UNVALIDATED_SIMULATION_PROXY_NOT_PHENOTYPE|no|ثبات التقييم
balance_id|معرف موازنة جذور ليوم ومنطقة|String|none|unique|no|مطابقة المخزون والمعادلات
date_local|يوم التجميع المحليAsia/Riyadh، من00:00إلى00:00التالي|Date|local date|2024-01-01..2025-12-31|no|تجميع زمني واضح
start_storage_mm|مخزون الماء المكافئ عند بداية اليوم في منطقة الجذور|Float|mm|>=0|no|طرف موازنة التربة
gross_irrigation_mm|حجم الري المنفذ/المساحة؛ 1L/m²=1mm|Float|mm|>=0|no|مدخل موازنة التربة قبل الفواقد
application_loss_mm|فقد التطبيق = gross*(1-efficiency)|Float|mm|>=0|no|منع احتساب كل الري ماء جذور
runoff_mm|فائض الماء عن حد التسرب الافتراضي عند كل خطوة|Float|mm|>=0|no|طرف موازنة التربة
deep_drainage_mm|تصريف فوري فوق التشبع وتصريف تدريجي فوقFC|Float|mm|>=0|no|طرف موازنة التربة
actual_et_mm|ET0*Kc_effective*Ks بتكامل الدقيقة؛ قيمة محاكاة لا ليزيميتر|Float|mm|>=0|no|فاقد التبخر نتح المحاكى
end_storage_mm|مخزون نهاية اليوم بعد الموازنة|Float|mm|0..saturation*root_mm|no|استمرارية المخزون
end_vwc|مخزون نهاية اليوم/(1000*root_depth_m)|Float|m3/m3|0..saturation|no|عرض حالة المحاكي
kc_effective|Kc الشهري مضروبًا في عامل حرارة هندسي افتراضي|Float|dimensionless|0..2|no|تغذيةET وليس قياس نمو
stress_minutes|دقائقKs<0.8 معET0موجب في اليوم؛ ليست تشخيص نبات|Integer|min/day|0..1440|no|تقييم سلوك المحاكي
mass_residual_mm|المتبقي الحسابي = start+rain+gross-loss-runoff-drain-ET-end|Float|mm|abs<=1e-7 in simulation|no|اختبار الاتساق الفيزيائي
site_balance_id|معرف موازنة حدود موقع ليوم|String|none|unique|no|فصل موازنة الموقع عن التربة
starting_storage_l|مخزون الخزان الافتراضي عند بداية اليوم قبل إعادة التعبئة|Float|L|>=0|no|موازنة حدود الموقع
inlet_volume_l|حجم دخول الخزان الافتراضي خلال اليوم|Float|L|>=0|no|موازنة حدود الموقع
zone_metered_volume_l|مجموع أحجام عدادي المنطقتين في اليوم|Float|L|>=0|no|ربط الأحداث بالموقع
ending_storage_l|مخزون نهاية اليوم بعد السحب المقاس وغير المقاس في المحاكي|Float|L|>=0|no|موازنة الحدود
known_other_outlet_l|مخارج أخرى مقاسة/معروفة؛ صفر في هذا السيناريو|Float|L|>=0|no|منع تفسير كل نقص كتسرب
unaccounted_volume_l|start+inlet-end-zone-known_other؛ متبق لا يؤكد تسربًا|Float|L|finite;0 or15 by design|no|اختبار تنبيه عدم الاتزان
balance_basis|أصل موازنة الموقع وحدود عداداتها|String|none|virtual_complete_boundary_not_field_measurement|no|فصل الافتراضي من المقاس
assessment_id|معرف تقييم نبات افتراضي|String|none|unique|no|ربط التقرير الأسبوعي
assessed_at|وقت اكتمال أسبوع التقييم عند00:00اليومالتالي، وليس وقت قياس نبات فعلي|Datetime|UTC ISO8601|within project period|no|ترتيب التقييم
cover_pct|تغطية Proxy محاكية من الإجهاد والحرارة؛ ليست صورة أو قياس نبات مستقل|Float|percent|0..100|no|اختبار عرض التقرير فقط
field_health_score|درجة صحة نبات مقاسة مستقلًا؛ لا توجد في هذه الحزمة|Float|protocol_defined|NULL here|yes|فجوة التحقق الميداني
interventions|القص والتسميد والصيانة المسجلة؛ none_simulated لا يثبت غياب تدخلات واقعية|String|none|none_simulated or recorded intervention|no|فهم العوامل المربكة
scenario_type|نوع الحالة التشغيلية المصممة للاختبار|String|none|no_flow/low_flow/stuck_open/unmetered_site_withdrawal|no|تغطية المسارات النادرة
injection_rule|قاعدة اختيار الحدث أو اليوم المحقون|String|none|explicit design rule|no|إعادة الإنتاج
incident_id|معرف تنبيه ومراجعته|String|none|unique|no|تتبع الفحص
detected_at|وقت ظهور التنبيه في السيناريو، لا وقت تأكيد سببه|Datetime|UTC ISO8601|<=confirmed_at|no|تقييم تسلسل الفحص
alert_type|وصف نمط التنبيه الذي يراه المشغّل|String|none|no_flow/low_flow/unexpected_flow/unaccounted_water/stale_sensor|no|توجيه الفحص
alert_id|معرف تنبيه مشتق بالقواعد|String|none|unique|no|ربط القرار بالتنبيه
alert_value|قيمة شدة التنبيه بوحدة القاعدة:L/minللتدفق أوLللمتبقي؛NULLلتقادم الحساس|Float|see method_version|>=0 or NULL|yes|تفسير عتبة القاعدة
confirmation_status|مصدر تأكيد السبب؛ هنا حقيقة محاكاة فقط|String|none|simulation_oracle_confirmation|no|عدم ادعاء تشخيص مستقل
confirmed_cause|سبب معروف لمحرك المحاكاة فقط؛ ممنوع كـFeature قبل الحدث|String|none|simulation scenario cause|no|Labels اختبارية للأعطال
confirmed_at|وقت فحص لاحق افتراضي أكد السبب بالمحاكاة|Datetime|UTC ISO8601|>=detected_at|no|فصل الاكتشاف والتأكيد
cost_id|معرف تكلفة سيناريو لسنة ومنطقة|String|none|unique|no|ربط تقرير التكلفة
year|سنة التقرير المحلية|Integer|year|2024/2025|no|التجميع
water_tariff_sar_m3|سعر سيناريو خيالي2ر.س/م³، ليس تعرفة فعلية موثقة|Float|SAR/m3|>=0;assumed2|no|عرض حساب تكلفة مشروط
water_cost_sar|حجم منفذ/1000 مضروبًا في السعر الافتراضي|Float|SAR|>=0|no|تقرير تكلفة افتراضية
energy_kwh|طاقة مضخة مقاسة/موثقة؛ لا توجد فلا تستنتج من اللترات|Float|kWh|NULL here|yes|إظهار فجوة الطاقة
cost_basis|نوع السعر والقياس الذي تستند إليه التكلفة|String|none|fictional_scenario_rate_NOT_verified_tariff|no|عدم تقديم أسعار مختلقة كحقيقة
forecast_rain_mm|توقع المطر الاصطناعي24ساعة الذي وصل قبل القرار|Float|mm|>=0|no|Feature وقت القرار
forecast_et0_mm|توقعET0الاصطناعي24ساعة الذي وصل قبل القرار|Float|mm|>=0|no|Feature وقت القرار
doy_sin|sin(2*pi*day_of_year/365.25) من تقويم وقت القرار|Float|dimensionless|-1..1|no|تمثيل موسمي معلوم مسبقًا
doy_cos|cos(2*pi*day_of_year/365.25) من تقويم وقت القرار|Float|dimensionless|-1..1|no|تمثيل موسمي
features_available_at|أقصى وقت إتاحة بين عينة التربة وإصدار التوقع المستخدمين|Datetime|UTC ISO8601|<=issued_at|no|اختبار منع التسرب
ground_truth_basis|مصدرTarget؛ قراءات حساسات محاكاة لا حقيقة ميدانية|String|none|simulation_sensor_NOT_field_ground_truth|no|تحديد صلاحيةML
split|المجموعة الزمنية قبل التدريب|String|none|train/validation/test|no|تقييم حالات لاحقة
eligible|أهلية عينةML:True فقط معLabelمحاكاة صالح|Boolean|none|True/False|no|منع تعويضTargetالمفقود
split_limitation|قيد التعميم:نفس الموقع والمنطقتين بلا حجز موقع جديد|String|none|nonempty|no|تفسير حدود الاختبار
input_role|دور مصدر المدخل المجمد للقرار|String|none|soil_pre/forecast/plan|no|تدقيق إتاحة المدخلات
input_record_id|معرف السجل الذي قدم قيمةFeatures|String|none|valid ID by input_role|no|تتبع مصدر المدخل
input_available_at|وقت وصول سجل المدخل نفسه؛ ليس وقت حدوثه فقط|Datetime|UTC ISO8601|<=issued_at|no|اختبارLeakage
title|عنوان المصدر|String|none|nonempty|no|فهرس المراجع
publisher|الجهة الناشرة أو مولد المحاكاة|String|none|nonempty|no|تقييم موثوقية المصدر
url|رابط أصلي أو مسار كود داخلي؛ ليس رابطًا مصطنعًا|String|none|verified URL or explicit internal reference|no|إعادة الوصول للمصدر
published_at|تاريخ نشر المصدر؛ نص يبين rolling/current إن لم توجد نسخة مؤرخة|String|date or status|verified date or explicit unknown/status|no|توثيق الإصدار دون اختلاق تاريخ
accessed_at|تاريخ/وقت الوصول للمصدر عند تجهيز الحزمة|String|ISO8601 date/time|2026-11-07 or timestamp|no|توثيق الوصول
coverage|موقع وفترة ودقة المصدر التي يغطيها فعليًا|String|none|nonempty|no|تقييم الملاءمة
format_resolution|صيغة البيانات وتكرارها/دقتها المعلنة|String|none|nonempty|no|تخطيط الجمع
license_restrictions|الترخيص أو قيوده/عدم وضوحه كما تحققنا منه|String|none|explicit;no invented license|no|تحديد شروط الاستخدام
assumption_id|معرف افتراض قابل للمراجعة|String|none|unique|no|تتبع القرارات التنظيمية
assumed_value|قيمة الافتراض نصًا مع المعادلة عند الحاجة|String|see description|explicit assumption|no|إعادة التوليد
description_ar|وصف عربي للافتراض وأصله وحدوده|String|none|nonempty|no|شفافية المحاكاة
priority|ترتيب أولوية جمع البيانات الميدانية|Integer|rank|>=1|no|خطة البدء
data_group_ar|مجموعة البيانات الناقصة|String|none|nonempty|no|طلب بيانات واضح
required_columns|قائمة الحقول المطلوب جمعها فعليًا|String|none|comma separated columns|no|طلب البيانات
collection_method_ar|طريقة جمع أو قياس البيانات الناقصة|String|none|nonempty|no|تنفيذ الجمع
cadence_ar|دورية الجمع المقترحة وشروط اعتمادها|String|none|nonempty|no|تخطيط التشغيل
responsible_ar|الدور الذي يجمع أو يؤكد القياس؛ لا بيانات شخصية|String|none|nonempty|no|مسؤوليةGround Truth
purpose_ar|استخدام المجموعة في المشروع والقيود|String|none|nonempty|no|ربط الجمع بالوظائف
function_ar|وظيفة المشروع المثبتة في التقرير|String|none|nonempty|no|تقييم التغطية
tables|الجداول التي تغطي الوظيفة|String|none|semicolon separated table names|no|تتبع التغطية
data_available_ar|نوع البيانات المتاحة للوظيفة|String|none|nonempty|no|تمييز المحاكاة والمرجع
readiness_ar|مدى جاهزية البيانات وحدود استخدامها|String|none|nonempty|no|القرار التنفيذي
missing_ar|البيانات التي تحتاج استكمالًا للوظيفة|String|none|nonempty|no|خطة الاستكمال
'''

FIELDS={}
for line in TEXT.strip().splitlines():
    x=line.split("|")
    assert len(x)==7,(len(x),line)
    FIELDS[x[0]]=dict(definition_ar=x[1],data_type=x[2],unit=x[3],accepted_values=x[4],nullable=x[5],use_ar=x[6])

DERIVATIONS={
 ("study_crop","cwr_mm_month"):"SRC01 Table5 pp106-107; published Kc*ET0",
 ("study_crop","iwr_mm_month"):"SRC01 Table6 p108; published CWR/(1-0.03); original rounding preserved",
 ("study_crop","irrigation_interval_days"):"SRC01 Table8 pp110-111; RAW/(CWR/days_per_month), historical February28days",
 ("measurements_clean","calibrated_original_vwc"):"measurements_raw.raw_adc*calibrations.slope+intercept; preserve invalid original",
 ("measurements_clean","usable_vwc"):"calibrated_original_vwc if0<=value<=saturation else NULL; no clipping or imputation",
 ("event_outcomes","delta_vwc"):"mean(valid post samples at planned_end+120min +/-5min)-pre_vwc; need>=2post; simulation only",
 ("irrigation_events","delivered_volume_l"):"meter_end_l-meter_start_l within same counter_epoch_id; equals minute flow integral",
 ("cost_summary","delivered_volume_l"):"sum simulation irrigation_events.delivered_volume_l grouped by zone and local year",
 ("root_balance_daily","end_vwc"):"end_storage_mm/(1000*root_depth_m)",
 ("root_balance_daily","mass_residual_mm"):"start_storage_mm+rain_mm+gross_irrigation_mm-application_loss_mm-runoff_mm-deep_drainage_mm-actual_et_mm-end_storage_mm",
 ("site_balance_daily","unaccounted_volume_l"):"starting_storage_l+inlet_volume_l-ending_storage_l-zone_metered_volume_l-known_other_outlet_l; not a confirmed leak",
 ("plant_assessments","cover_pct"):"clip(95-30*weekly_stress_fraction-20*(1-temperature_factor),0,100); UNVALIDATED proxy; not independent plant ground truth",
}

def write_dictionary(out,tables,meta):
    rows=[]
    for name,df in tables.items():
        for c in df.columns:
            if c not in FIELDS: raise KeyError("Missing dictionary: "+name+"."+c)
            f=FIELDS[c].copy()
            if c in meta[name]["primary_key"].split(","): f["nullable"]="no"
            if c=="zone_id" and name not in ["incident_reviews","test_scenarios","rule_alerts"]: f["nullable"]="no"
            if c=="event_id" and name not in ["incident_reviews","rule_alerts"]: f["nullable"]="no"
            method=DERIVATIONS.get((name,c),meta[name]["source_id"]+"; "+meta[name]["grain_ar"]+"; definition above; code/build_dataset.py")
            rows.append(dict(table=name,column=c,**f,source_or_derivation=method,record_origin=meta[name]["data_type"]))
    path=Path(out)/"metadata/data_dictionary.csv"
    with path.open("w",encoding="utf-8",newline="") as stream:
        w=csv.DictWriter(stream,fieldnames=["table","column","definition_ar","data_type","unit","accepted_values","nullable","source_or_derivation","use_ar","record_origin"])
        w.writeheader();w.writerows(rows)
