-- جداول التطبيق فقط. جداول الحزمة الأصلية (36 + 3 توثيق) لا تُعدَّل.
-- كل جدول هنا يبدأ بـ app_ ليبقى منفصلًا عن بيانات المحاكاة الأصلية.
PRAGMA foreign_keys = ON;

-- سجل كل طلب HTTP يصل إلى الـAPI
CREATE TABLE IF NOT EXISTS app_requests (
    request_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT    NOT NULL,              -- UTC ISO8601
    method        TEXT    NOT NULL,
    path          TEXT    NOT NULL,
    query         TEXT,
    status_code   INTEGER NOT NULL,
    duration_ms   REAL    NOT NULL,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS ix_app_requests_created ON app_requests(created_at);

-- توصيات الري التي يصدرها التطبيق (من المستخدم أو من إعادة تشغيل قرار محفوظ)
CREATE TABLE IF NOT EXISTS app_recommendations (
    recommendation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT    NOT NULL,
    request_id          INTEGER REFERENCES app_requests(request_id),
    zone_id             TEXT    NOT NULL REFERENCES zones(zone_id),
    profile_id          TEXT    NOT NULL REFERENCES zone_profiles(profile_id),
    source              TEXT    NOT NULL CHECK (source IN ('user_input','dashboard_latest','replay_decision')),
    based_on_decision_id TEXT   REFERENCES decisions(decision_id),
    decision_time_local TEXT,
    pre_vwc             REAL,
    sensor_status       TEXT    NOT NULL,
    action              TEXT    NOT NULL CHECK (action IN ('IRRIGATE','DEFER','CHECK_SENSOR')),
    rule_code           TEXT    NOT NULL,
    reasons_json        TEXT    NOT NULL,
    trigger_vwc         REAL,
    target_vwc          REAL,
    requested_volume_l  REAL,
    suggested_volume_l  REAL    NOT NULL DEFAULT 0,
    duration_min        INTEGER NOT NULL DEFAULT 0,
    budget_l            REAL,
    predicted_delta_vwc REAL,
    predicted_post_vwc  REAL,
    model_version       TEXT,
    warnings_json       TEXT    NOT NULL DEFAULT '[]',
    inputs_json         TEXT    NOT NULL,
    data_origin         TEXT    NOT NULL DEFAULT 'user_or_simulation_input_NOT_field_sensor'
);
CREATE INDEX IF NOT EXISTS ix_app_rec_zone ON app_recommendations(zone_id, created_at);

-- سيناريوهات المحاكاة التي شغلها المستخدم
CREATE TABLE IF NOT EXISTS app_simulations (
    simulation_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT    NOT NULL,
    request_id          INTEGER REFERENCES app_requests(request_id),
    zone_id             TEXT    NOT NULL REFERENCES zones(zone_id),
    label               TEXT,
    pre_vwc             REAL    NOT NULL,
    volume_l            REAL    NOT NULL,
    duration_min        REAL    NOT NULL,
    decision_date       TEXT    NOT NULL,
    forecast_rain_mm    REAL    NOT NULL,
    forecast_et0_mm     REAL    NOT NULL,
    predicted_delta_vwc REAL    NOT NULL,
    predicted_post_vwc  REAL    NOT NULL,
    linear_delta_vwc    REAL,
    model_version       TEXT    NOT NULL,
    warnings_json       TEXT    NOT NULL DEFAULT '[]',
    data_origin         TEXT    NOT NULL DEFAULT 'model_output_from_simulation_training_NOT_measurement'
);
CREATE INDEX IF NOT EXISTS ix_app_sim_zone ON app_simulations(zone_id, created_at);

-- تنبؤات المستخدم على النموذج الثاني (مجموعة v2، أربع مناطق). يرتبط بجداول v2_ المستوردة.
CREATE TABLE IF NOT EXISTS app_v2_runs (
    run_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at          TEXT    NOT NULL,
    request_id          INTEGER REFERENCES app_requests(request_id),
    zone_id             TEXT    NOT NULL REFERENCES v2_zones(zone_id),
    base_event_id       TEXT    NOT NULL REFERENCES v2_ml_ready(event_id),
    changed_inputs_json TEXT    NOT NULL,
    predicted_vwc_pct   REAL    NOT NULL,
    model_version       TEXT    NOT NULL,
    warnings_json       TEXT    NOT NULL DEFAULT '[]',
    data_origin         TEXT    NOT NULL DEFAULT 'model_output_from_v2_simulation_NOT_measurement'
);

-- ===================== المحاصيل الأربع (نخيل، برسيم، خضار، نجيل) — مضافة في الإصدار 2 =====================
-- توصيات الري المحفوظة للمحاصيل الأربع: قرار FAO-56 + تنبؤ نموذج المحاصيل. ترتبط بسجل اليوم في v2_ml_ready.
CREATE TABLE IF NOT EXISTS app_crop_recommendations (
    crop_rec_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at           TEXT    NOT NULL,
    request_id           INTEGER REFERENCES app_requests(request_id),
    zone_id              TEXT    NOT NULL REFERENCES v2_zones(zone_id),
    base_event_id        TEXT    NOT NULL REFERENCES v2_ml_ready(event_id),
    decision_date        TEXT    NOT NULL,
    source               TEXT    NOT NULL CHECK (source IN ('recommend','simulation')),
    strategy             TEXT    NOT NULL,
    action               TEXT    NOT NULL CHECK (action IN ('IRRIGATE','DEFER','CHECK_SENSOR')),
    rule_code            TEXT    NOT NULL,
    before_vwc_pct       REAL,
    target_vwc_pct       REAL,
    trigger_vwc_pct      REAL,
    depletion_mm         REAL,
    raw_mm               REAL,
    volume_l             REAL    NOT NULL DEFAULT 0,
    duration_min         REAL    NOT NULL DEFAULT 0,
    predicted_vwc_pct    REAL,
    predicted_no_irrigation_vwc_pct REAL,
    model_version        TEXT,
    reasons_json         TEXT    NOT NULL DEFAULT '[]',
    warnings_json        TEXT    NOT NULL DEFAULT '[]',
    inputs_json          TEXT    NOT NULL,
    data_origin          TEXT    NOT NULL DEFAULT 'model_and_fao56_on_simulated_v2_data_NOT_field'
);
CREATE INDEX IF NOT EXISTS ix_app_crop_rec_zone ON app_crop_recommendations(zone_id, created_at);
