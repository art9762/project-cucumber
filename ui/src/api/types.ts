/**
 * FROZEN API CONTRACT.
 *
 * These interfaces mirror the pydantic schemas in the analysis backend exactly:
 *   analysis/analysis/api/category_schemas.py
 *   analysis/analysis/api/score_schemas.py
 *   analysis/analysis/api/research_schemas.py
 *   analysis/analysis/api/search_schemas.py
 *   analysis/analysis/api/schemas.py  (HealthResponse)
 *
 * Field names and nullability match the Python source. Do not rename fields —
 * feature agents import these types as the single source of truth. Python
 * `X | None` maps to TS `X | null`; pydantic UUIDs are serialised as strings.
 */

// ---------------------------------------------------------------------------
// Health  (api/schemas.py :: HealthResponse)
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: string; // "ok" | "degraded"
  database: boolean;
  trinity_configured: boolean;
}

// ---------------------------------------------------------------------------
// Categories  (api/category_schemas.py)
// ---------------------------------------------------------------------------

/** Flat category node — used by GET /categories/pending. */
export interface CategoryOut {
  id: string;
  slug: string;
  title: string;
  parent_id: string | null;
  approved: boolean;
}

/** Recursive tree node — used by GET /categories. */
export interface CategoryTreeNode {
  id: string;
  slug: string;
  title: string;
  approved: boolean;
  children: CategoryTreeNode[];
}

/** POST /classify run result (mirrors ClassifyStats). */
export interface ClassifyRunOut {
  seen: number;
  classified: number;
  suggested: number;
  failed: number;
  errors: string[];
}

/** POST /categories/{id}/approve response. */
export interface ApproveResponse {
  ok: boolean;
  id: string;
  approved: boolean;
}

/** POST /categories/{id}/reject response. */
export interface RejectResponse {
  ok: boolean;
  id: string;
}

// ---------------------------------------------------------------------------
// Scores  (api/score_schemas.py)
// ---------------------------------------------------------------------------

/** A single tierlist row — GET /tierlist. */
export interface TierItemOut {
  item_id: string;
  title: string;
  url: string;
  category_id: string | null;
  tier: string | null;
  coefficient: number | null;
  scores: Record<string, number> | null;
}

/** Full score for a single item — GET /items/{id}/score. */
export interface ItemScoreOut {
  item_id: string;
  title: string;
  url: string;
  category_id: string | null;
  tier: string | null;
  coefficient: number | null;
  scores: Record<string, number> | null;
  model_used: string | null;
}

/** POST /score run result (mirrors ScoreStats). */
export interface ScoreRunOut {
  seen: number;
  scored: number;
  escalated: number;
  failed: number;
  tier_counts: Record<string, number>;
  errors: string[];
}

// ---------------------------------------------------------------------------
// Research  (api/research_schemas.py)
// ---------------------------------------------------------------------------

/** A competitor / similar solution embedded inside ItemResearchOut. */
export interface CompetitorOut {
  name: string;
  url: string | null;
  note: string | null;
}

/** Full web-research result for one item — GET /items/{id}/research. */
export interface ItemResearchOut {
  item_id: string;
  title: string;
  url: string;
  summary: string | null;
  competitors: CompetitorOut[];
  sources: string[];
  maturity_signal: number | null;
  potential_signal: number | null;
  model_used: string | null;
}

/** POST /research run result (mirrors ResearchStats). */
export interface ResearchRunOut {
  seen: number;
  researched: number;
  competitors_found: number;
  failed: number;
  errors: string[];
}

// ---------------------------------------------------------------------------
// Search & Embeddings  (api/search_schemas.py)
// ---------------------------------------------------------------------------

/**
 * Semantic search hit — POST /search AND GET /items/{id}/competitors.
 * NOTE: the competitors endpoint returns this SearchHitOut shape, NOT the
 * CompetitorOut shape (CompetitorOut only appears nested in ItemResearchOut).
 */
export interface SearchHitOut {
  item_id: string;
  title: string;
  url: string;
  distance: number;
  similarity: number;
  tier: string | null;
  coefficient: number | null;
  category_id: string | null;
}

/** POST /embed run result (mirrors EmbedStats). */
export interface EmbedRunOut {
  seen: number;
  embedded: number;
  failed: number;
  model: string | null;
  dim: number | null;
  errors: string[];
}

/** Request body for POST /search. */
export interface SearchQueryIn {
  query: string;
  limit: number;
}

// ---------------------------------------------------------------------------
// Query param shapes (not pydantic models, but part of the HTTP contract)
// ---------------------------------------------------------------------------

/** Query params for GET /tierlist. */
export interface TierlistFilters {
  tier?: string;
  category_id?: string;
  limit?: number;
}

/** Query params for GET /research. */
export interface ResearchListFilters {
  has_competitors?: boolean;
  limit?: number;
}

/** Query params for POST /research. */
export interface RunResearchParams {
  limit?: number;
  min_tier?: string;
  min_coefficient?: number;
}

/** Optional limit param shared by POST /classify, POST /score, POST /embed. */
export interface RunLimitParams {
  limit?: number;
}

// ---------------------------------------------------------------------------
// Auth contract (endpoints built by the backend auth agent in parallel).
// Assumed shape: /auth/me, /auth/login, /auth/logout.
// ---------------------------------------------------------------------------

/** Authenticated user — returned by GET /auth/me and POST /auth/login. */
export interface AuthUser {
  username: string;
  role: string;
}

/** Request body for POST /auth/login. */
export interface LoginRequest {
  username: string;
  password: string;
}

// ---------------------------------------------------------------------------
// Collect  (api/collect_schemas.py)
// ---------------------------------------------------------------------------

export interface CollectStats {
  fetched: number;
  inserted: number;
  updated: number;
  skipped: number;
}

export interface CollectJobOut {
  id: string;
  source: string;
  status: string; // "queued" | "running" | "success" | "failed"
  since: string | null;
  cursor: string | null;
  stats: CollectStats;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface CollectorSourcesOut {
  sources: string[];
}

export interface ScheduleOut {
  schedules: Record<string, string>;
}

export interface ScheduleUpdateRequest {
  cron: string;
}
