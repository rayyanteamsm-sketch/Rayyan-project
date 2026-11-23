// طبقة الاتصال بالخادم. الواجهة لا تحسب أي نتيجة ML أو قرار؛ كل شيء يأتي من الـAPI.

export type Action = "IRRIGATE" | "DEFER" | "CHECK_SENSOR";
export type ZoneId = "Z01" | "Z02";

export interface Reason { code: string; text_ar: string; value: number | null; threshold: number | null; kind: "decisive" | "info" | "warning"; }
export interface Thresholds {
  field_capacity_vwc: number; wilting_point_vwc: number; depletion_fraction: number; taw_mm: number; raw_mm: number;
  base_trigger_vwc: number; kc_month: number; temperature_factor: number | null; kc_decision: number;
  et_adjustment_vwc: number; trigger_vwc: number; target_vwc: number;
}
export interface DecisionOut {
  action: Action; action_ar: string; rule_code: string; rule_version: string;
  sensor: { ok: boolean; status: string; issues: Reason[] }; thresholds: Thresholds; reasons: Reason[]; warnings: string[];
}
export interface WaterPlan {
  deficit_mm: number; requested_l: number; cap_l: number; capped_l: number; daily_budget_l: number; other_zone_request_l: number;
  allocation_factor: number; volume_l: number; duration_min: number; flow_l_min: number; application_efficiency: number;
  limits_applied: string[]; explanation: string[];
}
export interface Prediction {
  available: boolean; reason?: string; model_version?: string; delta_vwc?: number; post_vwc?: number; warnings?: string[];
  linear_delta_vwc: number; linear_post_vwc: number; target_vwc?: number; note?: string;
}
export interface Recommendation {
  zone_id: ZoneId; trial_arm: string; decision: DecisionOut; water_plan: WaterPlan | null; prediction: Prediction | null;
  warnings: string[]; data_notice: string; recommendation_id?: number; valve_note?: string;
  stored_decision?: { decision_id: string; action: string; reason: string; planned_volume_l: number; planned_duration_min: number; method_version: string; issued_at_local: string };
  agreement?: { comparable: boolean; action_match: boolean; volume_match: boolean; note: string };
  inputs?: Record<string, number | string | null>;
}
export interface LastIrrigation {
  event_id: string; decision_id: string; started_local: string; delivered_volume_l: number; planned_volume_l: number;
  kind: string; status_ar: string; pre_vwc: number | null; post_vwc: number | null; delta_vwc: number | null;
}
export interface DashboardZone {
  zone_id: ZoneId; trial_arm: string; area_m2: number; plant: string; field_capacity_vwc: number; wilting_point_vwc: number;
  recommendation: Recommendation; last_irrigation: LastIrrigation | null;
  moisture_trend_30d: { d: string; v: number | null; n: number }[];
  water_30d: { delivered: number; planned: number; n: number }; water_to_date: { delivered: number; planned: number; n: number };
}
export interface Alert { alert_id: string; zone_id: string | null; event_id: string | null; alert_type: string; label_ar: string; detected_local: string; alert_value: number | null; method_version: string; confirmed_cause: string | null; confirmation_status: string | null; }
export interface Dashboard {
  date: string; data_range: { first_date: string; last_date: string; last_reading_local: string }; data_notice: string;
  system: { mode_ar: string; model_loaded: boolean; model_version: string; model_source: string; valve_control: string; daily_budget_l: number | null; counts: Record<string, number> };
  zones: DashboardZone[]; alerts: Alert[];
}
export interface WaterUsage {
  monthly: { month: string; zone_id: ZoneId; planned_l: number; delivered_l: number; events: number }[];
  totals: { zone_id: ZoneId; trial_arm: string; planned_l: number; delivered_l: number; events: number }[];
  cost: { zone_id: string; year: number; delivered_volume_l: number; water_tariff_sar_m3: number; water_cost_sar: number; cost_basis: string }[];
  simulated_stress_hours: { zone_id: string; stress_hours: number }[]; interpretation_ar: string;
}
export interface MetricRow { model_id: string; label_ar: string; split: "validation" | "test"; trained_on: string; n: number; mae: number; rmse: number; r2: number; }
export interface Metrics {
  model_version: string; trained_at: string; task: string; target: string; target_unit: string; algorithm: string; features: string[];
  forbidden_inputs: string[];
  data: { source: string; data_hash_sha256: string; checks: Record<string, unknown>; counts: Record<string, number>; label_origin: string };
  selection: { method: string; n_candidates: number; best_params: Record<string, unknown>; best_validation: { rmse: number; mae: number; r2: number }; top10: { params: Record<string, unknown>; rmse: number; r2: number }[] };
  results: MetricRow[];
  package_reproduction: { ours: Record<string, { r2: number; rmse: number; mae: number }>; package_reported: { model_id: string; evaluation_split: string; r2: number; rmse_vwc: number; mae_vwc: number }[] };
  error_analysis_test: { by_zone: Record<string, { n: number; mae: number; rmse: number; r2: number }>; by_confounding_flag: Record<string, { n: number; mae: number }>; by_month: { month: string; n: number; mae: number; mean_actual: number; mean_pred: number }[] };
  importance: { impurity: { feature: string; importance: number }[]; permutation_test: { feature: string; rmse_increase: number; std: number }[]; note: string };
  software: Record<string, string | number>; limitations: string[];
  runtime: { loaded: boolean; source: string; version: string; error: string | null };
  workbook_experiment: null | { title: string; n_features: number; rows_used: number; split_sizes: Record<string, number>; results: { model_id: string; split: string; mae: number; rmse: number; r2: number }[]; deviation_from_notebook: string; why_not_used_in_system: string; best_params: Record<string, unknown> };
}
export interface PredRow { decision_id: string; zone_id: ZoneId; split: string; actual_delta_vwc: number; predicted_delta_vwc: number; out_of_sample: number; issued_at: string; confounding_flags: string | null; }
export interface EngineValidation { decisions_compared: number; action_matches: number; volume_matches: number; action_agreement: number; volume_agreement: number; confusion: { stored: string; engine: string; n: number }[]; meaning: string; }
export interface HistoryItem {
  source: "simulation" | "app"; source_ar: string; id: string; decision_id: string | null; event_id: string | null; zone_id: ZoneId;
  time_local: string; action: Action; reason: string; method_version: string; pre_vwc: number | null; planned_volume_l: number;
  planned_duration_min: number; delivered_volume_l: number | null; post_vwc: number | null; delta_vwc: number | null; post_is_prediction?: boolean;
  ml_predicted_delta: number | null; ml_split: string | null; ml_out_of_sample: boolean | null; alerts: string[]; confounding: string | null;
  status: string; status_ar: string;
}
export interface HistoryPage { total: number; limit: number; offset: number; counts_by_action: Record<Action, number>; items: HistoryItem[]; }
export interface FlowAnalysis {
  event_id: string; decision_id: string; zone_id: ZoneId; planned_volume_l: number; delivered_volume_l: number; deviation_l: number; deviation_pct: number | null;
  planned_start_local: string; planned_end_local: string; execution_ended_local: string; nominal_flow_l_min: number; first5_avg_flow_l_min: number | null;
  detected_alerts: { type: string; label_ar: string; value: number }[]; series: { t: string; flow_l_min: number | null; meter_l: number }[]; note: string;
}
export interface HistoryDetail extends Record<string, unknown> { decision_id: string; time_local: string; action: Action; status_ar: string; flow: FlowAnalysis | null; }
export interface ScenarioResult {
  index: number; label: string; zone_id: ZoneId; decision_date: string; pre_vwc: number; volume_l: number; duration_min: number;
  forecast_rain_mm: number; forecast_et0_mm: number; forecast_temperature_c: number | null; predicted_delta_vwc: number; predicted_post_vwc: number;
  linear_delta_vwc: number; linear_post_vwc: number; target_vwc: number; trigger_vwc: number; gap_to_target_vwc: number; water_per_delta: number | null;
  model_version: string; warnings: string[]; simulation_id: number;
  sweep?: { volume_l: number; predicted_delta_vwc: number; linear_delta_vwc: number; in_training_range: boolean }[];
}
export interface SimulationOut { scenarios: ScenarioResult[]; data_notice: string; disclaimer_ar: string; linear_note_ar: string; }
export interface GalleryItem { id: string; group: string; group_label: string; group_note: string; original_file: string; original_format: string; display_original: string; converted_from_heic: boolean; web: string; thumb: string; width: number; height: number; bytes_original: number; }
export interface SiteInfo {
  site: Record<string, string | number>; zones: Record<string, string | number>[]; devices: Record<string, string | number | boolean | null>[];
  study_parameters: Record<string, string | number | null>[]; assumptions: Record<string, string>[];
  provenance: { key: string; label_ar: string; description_ar: string; tables: { table: string; rows: number; grain_ar: string }[] }[];
  field_data_gaps: Record<string, string | number>[]; function_readiness: Record<string, string>[]; sources: Record<string, string>[]; data_notice: string;
}

export interface V2Zone { zone_id: string; zone_name: string; crop: string; area_m2: number; plant_count: number; irrigation_system: string; soil_type: string; root_depth_m: number; wilting_pct: number; field_capacity_pct: number; efficiency: number; nominal_flow_L_min: number; saturation_pct_assumed: number; kc_assumed: number }
export interface V2Overview {
  zones: V2Zone[]; splits: { split: string; n: number; missing_targets: number; first: string; last: string }[];
  faults: { zone_id: string; label: string; n: number }[]; readme: { "الموضوع": string; "التوضيح": string }[];
  monthly: { zone_id: string; month: string; before_vwc: number; after_vwc: number; planned_l: number; actual_l: number }[];
  provenance: string; independence_note: string;
}
export interface V2Result { model_id: string; label_ar: string; split: string; trained_on: string; source: "computed_here" | "reported_in_file"; n: number; mae: number; rmse: number; r2: number }
export interface V2Metrics {
  model_version: string; trained_at: string; dataset: string; target: string; target_unit: string; horizon: string; algorithm: string;
  features: string[]; categorical_features: string[]; feature_descriptions_ar: Record<string, string>;
  data: { counts: Record<string, number>; checks: Record<string, unknown>; data_hash_sha256: string };
  selection: { n_candidates: number; best_params: Record<string, unknown>; best_validation: { mae: number; rmse: number; r2: number } };
  results: V2Result[]; error_analysis_test: { by_zone: Record<string, { n: number; mae: number; rmse: number; r2: number; crop: string; zone_name: string }>; by_missing_reading: Record<string, { n: number; mae: number }> };
  importance: { permutation_test: { feature: string; rmse_increase: number; std: number }[]; note: string };
  not_available: string[]; limitations: string[];
}
export interface V2Defaults { event_id: string; zone_id: string; date: string; temporal_split: string; inputs: Record<string, number | string | null>; recorded_actual_vwc_pct: number | null; recorded_actual_volume_l: number; simulated_fault_label: string; field_capacity_pct: number; wilting_pct: number }
export interface V2Prediction { model_version: string; zone_id: string; date: string; event_id: string; predicted_vwc_pct: number; before_vwc_pct: number | null; field_capacity_pct: number; wilting_pct: number; changed_inputs: Record<string, { from: unknown; to: unknown }>; inputs_used: Record<string, unknown>; warnings: string[]; recorded_actual_vwc_pct: number | null; recorded_note: string | null; run_id: number }
export interface V2PredRow { event_id: string; split: string; zone_id: string; actual_vwc_pct: number; predicted_vwc_pct: number; out_of_sample: number; feature_cutoff_at: string }

// ------------------------------------------------------------------ المحاصيل الأربع (نموذج مستقل)
export type CropZoneId = "Z001" | "Z002" | "Z003" | "Z004";
export interface CropZone extends V2Zone { p_table: number; p_source: string; taw_mm: number; training_volume_range_l: [number, number] | null }
export interface CurvePoint { volume_l: number; predicted_vwc_pct: number; water_balance_vwc_pct: number }
export interface Fao56 {
  taw_mm: number; raw_mm: number; p_table: number; p_adjusted: number; etc_mm: number; trigger_vwc_pct: number;
  depletion_mm: number | null; depletion_frac_taw?: number; rain_forecast_mm: number;
}
export interface CropWaterPlan {
  net_mm: number; volume_l: number; duration_min: number; flow_l_min: number; efficiency: number; area_m2: number;
  target_vwc_pct: number; limits_applied: string[]; formula: string;
}
export interface CropModelOut {
  version: string; predicted_vwc_no_irrigation_pct: number; predicted_vwc_with_plan_pct: number; volume_used_l: number;
  curve?: CurvePoint[]; training_volume_range_l: [number, number]; target_vwc_pct: number;
  model_min_volume_for_target_l: number | null; model_min_volume_note: string | null;
}
export interface CropRecommendation {
  zone: CropZone; date: string; decision_time: string; event_id: string; temporal_split: string;
  decision: { action: Action; rule_code: string; reasons: string[] }; fao56: Fao56; water_plan: CropWaterPlan | null;
  model: CropModelOut | null; inputs_used: Record<string, number | string | null>; changed_inputs: Record<string, { from: unknown; to: unknown }>;
  recorded_in_file: { before_vwc_pct: number | null; after_6h_vwc_pct: number | null; planned_volume_l: number; actual_volume_l: number; simulated_fault_label: string; note: string };
  warnings: string[]; method_note: string; saved_id?: number; data_notice: string;
}
export interface CropDashZone {
  zone: CropZone; decision: CropRecommendation["decision"]; fao56: Fao56; water_plan: CropWaterPlan | null; model: CropModelOut | null;
  warnings: string[]; before_vwc_pct: number | null; recorded_in_file: CropRecommendation["recorded_in_file"];
}
export interface CropDashboard {
  date: string; range: { min: string; max: string }; zones: CropDashZone[];
  trend_30d: { zone_id: string; date: string; before_vwc: number | null; after_vwc: number | null; planned_l: number; actual_l: number }[];
  usage_30d: { zone_id: string; planned_l: number; actual_l: number; irrigations: number }[];
  recent_saved: { crop_rec_id: number; created_at: string; zone_id: string; decision_date: string; source: string; action: Action; volume_l: number; predicted_vwc_pct: number | null }[];
  model: { loaded: boolean; version: string }; note: string;
}
export interface CropScenarioOut {
  label: string; volume_l: number; duration_min: number; before_vwc_pct: number | null; predicted_vwc_pct: number; water_balance_vwc_pct: number;
  change_pp: number | null; depth_mm_net: number; warnings: string[]; saved_id: number;
}
export interface CropSimulation {
  zone_id: string; crop: string; date: string; scenarios: CropScenarioOut[]; curve: CurvePoint[]; training_volume_range_l: [number, number];
  field_capacity_pct: number; wilting_pct: number; model_version: string; disclaimer_ar: string;
}
export interface CropResult { model_id: string; label_ar: string; family: string; split: string; trained_on: string; source: "computed_here" | "reported_in_file"; n: number; mae: number; rmse: number; r2: number }
export interface CropMetrics {
  model_version: string; trained_at: string; dataset: string; task: string; target: string; target_unit: string; horizon: string; algorithm: string;
  family: string; target_mode: string; params: Record<string, unknown>; features: string[]; feature_descriptions_ar: Record<string, string>;
  feature_units: Record<string, string>; forbidden_inputs: string[];
  data: { counts: Record<string, number>; checks: Record<string, unknown>; data_hash_sha256: string; label_origin: string };
  selection: { method: string; n_candidates: number; n_eligible: number; monotonic_min_pct: number;
    best: { family: string; target_mode: string; params: Record<string, unknown>; mae: number; rmse: number; r2: number; monotonic_val_pct: number };
    all: { family: string; target_mode: string; params: Record<string, unknown>; mae: number; rmse: number; r2: number; monotonic_val_pct: number }[];
    water_balance_cap_chosen_on_validation: string };
  results: CropResult[];
  headline: { deployed_test: { mae: number; rmse: number; r2: number }; persistence_test: { mae: number; rmse: number; r2: number }; water_balance_test: { mae: number; rmse: number; r2: number }; rmse_reduction_vs_persistence_pct: number };
  error_analysis_test: { by_zone: Record<string, { n: number; mae: number; rmse: number; r2: number; persistence_mae: number; crop: string; zone_name: string }>; by_missing_reading: Record<string, { n: number; mae: number }>; by_month: { month: string; n: number; mae: number }[] };
  response_check_test: { rows: number; monotonic_rows_pct: number; mean_gain_planned_vs_none_pp: number; mean_gain_more_vs_planned_pp: number };
  importance: { permutation_test: { feature: string; rmse_increase: number; std: number }[]; note: string };
  software: Record<string, string | number>; training_seconds: number; limitations: string[];
}
export interface CropHistoryItem {
  crop_rec_id: number; created_at: string; zone_id: string; crop: string; zone_name: string; base_event_id: string; decision_date: string;
  source: "recommend" | "simulation"; strategy: string; action: Action; rule_code: string; before_vwc_pct: number | null; target_vwc_pct: number | null;
  depletion_mm: number | null; raw_mm: number | null; volume_l: number; duration_min: number; predicted_vwc_pct: number | null;
  predicted_no_irrigation_vwc_pct: number | null; model_version: string | null; reasons: string[]; warnings: string[];
}
export interface ImageAnalysisItem {
  file: string; id: string; group: string; format: string; read_with: string; height: number; width: number; brightness: number; contrast: number;
  green_cover_pct: number; mean_r: number; mean_g: number; mean_b: number; images: { gray: string; green_mask: string; edges: string; resized: string };
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new ApiError(0, "network", "تعذر الاتصال بالخادم. تأكدي أن run.sh أو run.bat يعمل.");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const e = body?.error;
    const details = Array.isArray(e?.details) ? e.details.map((d: { field: string; message: string }) => `${d.field}: ${d.message}`).join(" · ") : "";
    throw new ApiError(res.status, e?.code ?? "http_error", (e?.message ?? `خطأ ${res.status}`) + (details ? ` — ${details}` : ""), e?.details);
  }
  return body as T;
}

const qs = (p: Record<string, string | number | undefined | null>) =>
  Object.entries(p).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");

export const api = {
  health: () => request<{ status: string; model: { version: string; loaded: boolean } }>("/api/health"),
  dashboard: (date?: string) => request<Dashboard>(`/api/dashboard?${qs({ date })}`),
  waterUsage: () => request<WaterUsage>("/api/water/usage"),
  recommend: (body: Record<string, unknown>) => request<Recommendation>("/api/irrigation/recommend", { method: "POST", body: JSON.stringify(body) }),
  replay: (id: string, save = false) => request<Recommendation>(`/api/irrigation/replay/${encodeURIComponent(id)}?${qs({ save: save ? "true" : undefined })}`),
  simulate: (body: Record<string, unknown>) => request<SimulationOut>("/api/simulation/run", { method: "POST", body: JSON.stringify(body) }),
  simDefaults: (date: string) => request<{ forecast: { rain_mm: number | null; et0_mm: number | null; temperature_c: number | null }; pre_vwc_by_zone: Record<string, number | null>; forecast_available: boolean }>(`/api/simulation/defaults?${qs({ date })}`),
  metrics: () => request<Metrics>("/api/model/metrics"),
  predictions: (split: string) => request<{ items: PredRow[] }>(`/api/model/predictions?${qs({ split })}`),
  engine: () => request<EngineValidation>("/api/model/decision-engine"),
  history: (p: Record<string, string | number | undefined>) => request<HistoryPage>(`/api/history?${qs(p)}`),
  historyDetail: (id: string) => request<HistoryDetail>(`/api/history/${encodeURIComponent(id)}`),
  site: () => request<SiteInfo>("/api/site"),
  gallery: () => request<{ items: GalleryItem[]; media_base: string }>("/api/site/gallery"),
  v2Overview: () => request<V2Overview>("/api/v2/overview"),
  v2Metrics: () => request<V2Metrics>("/api/v2/metrics"),
  v2Predictions: (split: string) => request<{ items: V2PredRow[] }>(`/api/v2/predictions?${qs({ split })}`),
  v2Defaults: (zone_id: string, date: string) => request<V2Defaults>(`/api/v2/defaults?${qs({ zone_id, date })}`),
  v2Predict: (body: Record<string, unknown>) => request<V2Prediction>("/api/v2/predict", { method: "POST", body: JSON.stringify(body) }),
  zones: () => request<{ items: Record<string, string | number>[] }>("/api/zones"),
  predict: (body: Record<string, unknown>) => request<{ delta_vwc: number; post_vwc: number; target_vwc: number; model_version: string; warnings: string[]; linear_post_vwc?: number }>("/api/predict", { method: "POST", body: JSON.stringify(body) }),
  cropZones: () => request<{ items: CropZone[]; range: { min: string; max: string }; model: { loaded: boolean; version: string } }>("/api/crops/zones"),
  cropDashboard: (date?: string) => request<CropDashboard>(`/api/crops/dashboard?${qs({ date })}`),
  cropRecommend: (body: Record<string, unknown>) => request<CropRecommendation>("/api/crops/recommend", { method: "POST", body: JSON.stringify(body) }),
  cropSimulate: (body: Record<string, unknown>) => request<CropSimulation>("/api/crops/simulate", { method: "POST", body: JSON.stringify(body) }),
  cropMetrics: () => request<CropMetrics>("/api/crops/metrics"),
  cropPredictions: (split: string) => request<{ items: V2PredRow[] }>(`/api/crops/predictions?${qs({ split })}`),
  cropHistory: (p: Record<string, string | number | undefined>) => request<{ total: number; items: CropHistoryItem[] }>(`/api/crops/history?${qs(p)}`),
  imageAnalysis: () => request<{ items: ImageAnalysisItem[]; summary: Record<string, unknown>; method_ar: string; source: string }>("/api/site/image-analysis"),
};
