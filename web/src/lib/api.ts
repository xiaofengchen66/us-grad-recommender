// Typed client for the read-only institution API in
// src/us_grad_recommender/api/. Mirrors api/schemas.py field-for-field —
// keep these in sync by hand until the backend publishes an OpenAPI-derived
// type generator; there's no codegen step yet.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Sector =
  | "public"
  | "private_nonprofit"
  | "private_for_profit"
  | "unknown";

export type CoverageTier =
  | "INDEXED"
  | "PROGRAMS_DISCOVERED"
  | "PROGRAMS_VERIFIED"
  | "ADMISSION_ENRICHED"
  | "FUNDING_ENRICHED"
  | "OUTCOME_ENRICHED";

export interface UniversitySummary {
  unitid: number;
  canonical_name: string;
  city: string | null;
  state: string | null;
  sector: Sector;
  masters_granting: boolean;
  coverage_tier: CoverageTier;
}

export type AliasType =
  | "ipeds_alias"
  | "former_name"
  | "common_abbreviation"
  | "other";

export interface UniversityAlias {
  alias: string;
  alias_type: AliasType;
  source: string;
}

export interface UniversityDetail {
  unitid: number;
  canonical_name: string;
  website: string | null;
  city: string | null;
  state: string | null;
  latitude: number | null;
  longitude: number | null;
  sector: Sector;
  highest_degree_level: number | null;
  highest_degree_label: string | null;
  carnegie_classification: number | null;
  carnegie_classification_label: string | null;
  campus_setting: number | null;
  campus_setting_label: string | null;
  masters_granting: boolean;
  masters_granting_basis: string | null;
  degree_granting: boolean | null;
  active: boolean;
  total_enrollment: number | null;
  graduate_enrollment: number | null;
  international_graduate_enrollment: number | null;
  enrollment_year: number | null;
  coverage_tier: CoverageTier;
  ipeds_year: number;
  source_dataset: string;
  last_verified_at: string;
  updated_at: string;
  aliases: UniversityAlias[];
}

export interface UniversityListResponse {
  total: number;
  limit: number;
  offset: number;
  results: UniversitySummary[];
}

export interface SearchParams {
  q?: string;
  state?: string;
  sector?: Sector;
  masters_granting?: boolean;
  limit?: number;
  offset?: number;
}

class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function buildQuery(params: SearchParams): string {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q);
  if (params.state) search.set("state", params.state);
  if (params.sector) search.set("sector", params.sector);
  if (params.masters_granting !== undefined) {
    search.set("masters_granting", String(params.masters_granting));
  }
  search.set("limit", String(params.limit ?? 25));
  search.set("offset", String(params.offset ?? 0));
  return search.toString();
}

export async function searchUniversities(
  params: SearchParams,
): Promise<UniversityListResponse> {
  const res = await fetch(`${API_BASE_URL}/universities?${buildQuery(params)}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ApiError(`Search failed: ${res.status}`, res.status);
  }
  return res.json();
}

export async function getUniversity(unitid: number): Promise<UniversityDetail | null> {
  const res = await fetch(`${API_BASE_URL}/universities/${unitid}`, {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new ApiError(`Detail fetch failed: ${res.status}`, res.status);
  }
  return res.json();
}
