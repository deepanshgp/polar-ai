// POLAR-AI v2 TypeScript types

export type DataMode = 'live' | 'demo' | 'near_real_time' | 'latest_available' | 'stale' | 'offline' | 'unknown' | 'real' | 'unavailable'
export type RiskCategory = 'low' | 'moderate' | 'high' | 'extreme'
export type AlertLevel = 'INFO' | 'WARNING' | 'DANGER' | 'CRITICAL'

// ── Freshness ─────────────────────────────────────────────────────────────────

export interface FreshnessInfo {
  source_id: string
  source_name: string
  status: string            // LIVE | NEAR_REAL_TIME | LATEST_AVAILABLE | STALE | OFFLINE | DEMO
  status_label: string
  status_color: string      // green | yellow | orange | red | amber | gray
  last_updated: string | null
  age_seconds: number | null
  age_human: string
  mode: string
  source: string
  record_count: number | null
  is_real: boolean
  last_error: string | null
  data_mode?: string
}

export interface SystemStatus {
  total: number
  live: number
  near_real_time: number
  demo: number
  offline: number
  sources: FreshnessInfo[]
  effective_data_mode: string
  credentials: Record<string, boolean | string>
}

// ── Health ────────────────────────────────────────────────────────────────────
export interface HealthStatus {
  status: string
  timestamp: string
  version: string
  database: string
  postgis: boolean
  data_mode: string
  llm_available: boolean
  llm_provider: string
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export interface DashboardStats {
  sea_ice_coverage_pct: number
  sea_ice_extent_km2: number
  active_icebergs: number
  high_risk_icebergs: number
  current_risk_score: number
  current_risk_category: string
  sea_ice_risk: number
  iceberg_risk: number
  weather_risk: number
  ocean_risk: number
  avg_wind_speed_ms: number
  avg_sst_celsius: number
  vessel_status: string
  vessel_lat: number
  vessel_lon: number
  vessel_speed_knots: number
  vessel_heading_deg: number
  vessel_data_mode: string
  vessel_name: string
  forecast_accuracy: ForecastAccuracy[]
  system_status: SystemStatus
  effective_data_mode: string
  unread_alerts: number
  data_mode: string
  last_updated: string
}

export interface ForecastAccuracy {
  horizon: string
  mae: number
  rmse: number
  skill_score: number
}

// ── Sea Ice ───────────────────────────────────────────────────────────────────
export interface GridPoint {
  latitude: number
  longitude: number
  concentration: number
  ice_category: string
}

export interface SeaIceCurrentData {
  timestamp: string
  grid_points: GridPoint[]
  coverage_pct: number
  extent_km2: number
  source: string
  data_mode: string
  freshness?: FreshnessInfo
  is_real: boolean
}

export interface SeaIceForecast {
  generated_at: string
  valid_time: string
  horizon_hours: number
  grid_points: any[]
  model_name: string
  overall_confidence: number
  mae: number
  rmse: number
  data_mode: string
}

export interface HistoryPoint {
  date: string
  coverage_pct: number
  extent_km2: number
  anomaly_pct?: number
}

// ── Icebergs ──────────────────────────────────────────────────────────────────
export interface Iceberg {
  id: string
  iceberg_name: string
  latitude: number
  longitude: number
  length_km: number
  width_km: number
  area_km2: number
  drift_speed_kmh: number
  drift_direction_deg: number
  risk_level: 'low' | 'medium' | 'high' | 'critical'
  status: string
  last_observed_at: string
  data_mode: string
  is_real?: boolean
  source?: string
}

export interface IcebergPosition {
  observed_at: string
  latitude: number
  longitude: number
  speed_kmh: number
  direction_deg: number
  confidence: number
}

export interface IcebergDetail extends Iceberg {
  source: string
  positions: IcebergPosition[]
  freshness?: FreshnessInfo
}

export interface TrajectoryPoint {
  horizon_hours: number
  valid_time: string
  latitude: number
  longitude: number
  uncertainty_km: number
  confidence: number
}

export interface IcebergTrajectory {
  iceberg_id: string
  iceberg_name: string
  current_lat: number
  current_lon: number
  predicted_at: string
  trajectory: TrajectoryPoint[]
  model_name: string
  closest_approach_km: number | null
  closest_approach_time: string | null
  data_mode: string
}

// ── Satellite ─────────────────────────────────────────────────────────────────
export interface SatelliteProduct {
  product_id: string
  collection: string
  acquisition_time: string
  publication_time: string
  platform: string
  instrument: string
  product_type: string
  polarization: string
  orbit_direction: string
  footprint: any   // GeoJSON geometry
  bbox: number[]
  thumbnail_url: string
  source: string
  data_mode: string
}

// ── Vessel ────────────────────────────────────────────────────────────────────
export interface VesselPosition {
  mmsi: string
  imo: string
  vessel_name: string
  latitude: number
  longitude: number
  speed_knots: number
  course_deg: number
  heading_deg: number
  navigation_status: string
  timestamp: string
  age_seconds: number
  source: string
  is_real: boolean
  data_mode: string
  status_label: string  // 'LIVE' | 'DEMO'
}

// ── Weather ───────────────────────────────────────────────────────────────────
export interface WeatherPoint {
  latitude: number
  longitude: number
  wind_speed_ms: number
  wind_direction_deg: number
  air_temp_celsius: number
  sea_level_pressure_hpa: number
  precipitation_mm: number
  weather_risk_score: number
  source: string
  is_real?: boolean
}

// ── Ocean ─────────────────────────────────────────────────────────────────────
export interface OceanPoint {
  latitude: number
  longitude: number
  current_speed_ms: number
  current_direction_deg: number
  current_u_ms: number
  current_v_ms: number
  sea_surface_temp_celsius: number | null
  significant_wave_height_m: number
  ocean_risk_score: number
  source: string
  is_real?: boolean
}

// ── Routes ────────────────────────────────────────────────────────────────────
export interface RouteWaypoint {
  sequence: number
  latitude: number
  longitude: number
  sea_ice_concentration: number
  wind_speed_ms: number
  local_risk_score: number
  estimated_arrival: string
}

export interface Route {
  id: string
  route_type: string
  origin_name: string
  destination_name: string
  waypoints: RouteWaypoint[]
  total_distance_km: number
  estimated_duration_hours: number
  estimated_fuel_tonnes: number
  fuel_efficiency_index: number
  overall_risk_score: number
  sea_ice_risk_score: number
  iceberg_risk_score: number
  weather_risk_score: number
  ocean_risk_score: number
  risk_category: string
  max_ice_concentration: number
  avg_ice_concentration: number
  iceberg_intersections: number
  risk_factors: string[]
  recommendations: string[]
  data_mode: string
}

export interface RouteComparison {
  generated_at: string
  origin_name: string
  destination_name: string
  routes: Route[]
  recommended_route_type: string
  recommendation_reason: string
  data_mode: string
}

export interface RiskResult {
  latitude: number
  longitude: number
  total_risk_score: number
  risk_category: string
  sea_ice_risk: number
  iceberg_risk: number
  weather_risk: number
  ocean_risk: number
  risk_factors: Array<{ text: string; source: string }>
  recommendations: string[]
  data_mode: string
}

// ── Alerts ────────────────────────────────────────────────────────────────────
export interface NavAlert {
  id: string
  alert_type: string
  level: AlertLevel
  title: string
  message: string
  data: Record<string, any>
  created_at: string
  age_seconds: number
  acknowledged: boolean
}

// ── Agent ─────────────────────────────────────────────────────────────────────
export interface AgentResponse {
  question: string
  response: string
  tools_used: string[]
  data_mode: string
  llm_provider: string
  timestamp: string
}

// ── Simulation ────────────────────────────────────────────────────────────────
export interface SimulationEvent {
  step: number
  message: string
  is_alert: boolean
}

export interface SimulationState {
  running: boolean
  step: number
  time_offset_hours: number
  vessel: { latitude: number; longitude: number; heading_deg: number; speed_knots: number }
  icebergs: Iceberg[]
  route_status: string
  risk_score: number
  risk_category: string
  events: SimulationEvent[]
  scenario_complete: boolean
  data_mode: string
}

// ── Data Sources ──────────────────────────────────────────────────────────────
export interface DataSource extends FreshnessInfo {
  url: string
  variables: string[]
  resolution: string
  format: string
  credential_required: string
}
