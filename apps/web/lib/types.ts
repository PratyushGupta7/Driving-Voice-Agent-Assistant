export type TokenResponse = {
  server_url: string;
  participant_token: string;
  room_name: string;
};

export type AgentEvent = {
  seq: number;
  session_id: string;
  type: string;
  monotonic_ms: number;
  wall_time: string;
  payload: Record<string, unknown>;
};

export type TranscriptLine = {
  id: string;
  role: "driver" | "agent";
  text: string;
  partial: boolean;
};

export type ProviderMap = Record<string, string>;

export type MissionConstraints = {
  category: string;
  maximum_detour_minutes: number | null;
  parking_required: boolean;
  avoid_tolls: boolean;
  landmark_query?: string | null;
  destination_query?: string | null;
  origin_query?: string | null;
  brand_query?: string | null;
  prefer_along?: "start" | "end" | null;
};

export type PlaceCandidate = {
  id?: string;
  name: string;
  area: string;
  category?: string;
  parking?: string;
  detour_minutes?: number | null;
  lat?: number | null;
  lng?: number | null;
  verified?: boolean;
  reasons?: string[];
  opening_hours?: string | null;
  brand?: string | null;
  progress?: number | null;
};

export type RouteSnapshot = {
  origin_name: string;
  destination_name: string;
  origin_lat: number;
  origin_lng: number;
  dest_lat: number;
  dest_lng: number;
  geometry: number[][];
  via_geometry?: number[][];
  duration_s?: number | null;
  distance_m?: number | null;
  eta_minutes?: number | null;
  distance_km?: number | null;
  avoid_tolls?: boolean;
  provider?: string;
  toll_compare_minutes?: number | null;
  summary?: string;
};

export type VersionEntry = {
  version: number;
  summary: string;
  epoch: number;
};

export type MissionSnapshot = {
  session_id: string;
  mission_id: string | null;
  mission_version: number;
  output_epoch: number;
  output_gate: string;
  status: string;
  constraints: MissionConstraints | null;
  selected?: PlaceCandidate | null;
  alternatives?: PlaceCandidate[];
  geo_mode?: string;
  version_log?: VersionEntry[];
  last_revision?: string | null;
  last_barrier_ms?: number | null;
  route?: RouteSnapshot | null;
};

export type ToolRow = {
  id: string;
  phase: string;
  kind: string;
  decision: string;
  mission_version: number;
  output_epoch: number;
  delay_ms?: number;
  delay_s?: number;
  name?: string | null;
  area?: string | null;
  error?: string;
  provider?: string;
  label?: string;
};
