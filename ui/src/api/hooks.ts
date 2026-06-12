/**
 * TanStack Query hooks for every analysis API endpoint.
 *
 * Read endpoints → useQuery hooks. Action endpoints (the POST runs) →
 * useMutation hooks that invalidate the relevant read caches on success.
 * All query keys live in the `queryKeys` object so feature agents can
 * invalidate them consistently.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";

import { apiFetch, get, post } from "./client";
import type {
  ApproveResponse as ApproveResult,
  CategoryOut,
  CategoryTreeNode,
  ClassifyRunOut,
  CollectJobOut,
  CollectorSourcesOut,
  EmbedRunOut,
  HealthResponse,
  ItemResearchOut,
  ItemScoreOut,
  RejectResponse as RejectResult,
  ResearchListFilters,
  ResearchRunOut,
  RunLimitParams,
  RunResearchParams,
  ScheduleOut,
  ScheduleUpdateRequest,
  ScoreRunOut as ScoreRunOutResult,
  SearchHitOut,
  SearchQueryIn,
  TierItemOut,
  TierlistFilters,
} from "./types";

// ---------------------------------------------------------------------------
// Query keys — single source for cache invalidation.
// ---------------------------------------------------------------------------

export const queryKeys = {
  health: ["health"] as const,
  categories: ["categories"] as const,
  categoriesPending: ["categories", "pending"] as const,
  tierlist: (filters: TierlistFilters = {}) => ["tierlist", filters] as const,
  itemScore: (id: string) => ["items", id, "score"] as const,
  research: (filters: ResearchListFilters = {}) => ["research", filters] as const,
  itemResearch: (id: string) => ["items", id, "research"] as const,
  competitors: (id: string, limit?: number) =>
    ["items", id, "competitors", limit ?? 10] as const,
  collectSources: ["collect", "sources"] as const,
  collectJob: (id: string) => ["collect", "jobs", id] as const,
  collectSchedule: ["collect", "schedule"] as const,
} as const;

// ---------------------------------------------------------------------------
// Reads
// ---------------------------------------------------------------------------

/** GET /health */
export function useHealth(): UseQueryResult<HealthResponse> {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => get<HealthResponse>("/health", undefined, signal),
    refetchInterval: 30_000,
  });
}

/** GET /categories — full nested tree. */
export function useCategories(): UseQueryResult<CategoryTreeNode[]> {
  return useQuery({
    queryKey: queryKeys.categories,
    queryFn: ({ signal }) =>
      get<CategoryTreeNode[]>("/categories", undefined, signal),
  });
}

/** GET /categories/pending — flat moderation queue. */
export function usePendingCategories(): UseQueryResult<CategoryOut[]> {
  return useQuery({
    queryKey: queryKeys.categoriesPending,
    queryFn: ({ signal }) =>
      get<CategoryOut[]>("/categories/pending", undefined, signal),
  });
}

/** GET /tierlist?tier=&category_id=&limit= */
export function useTierlist(
  filters: TierlistFilters = {},
): UseQueryResult<TierItemOut[]> {
  return useQuery({
    queryKey: queryKeys.tierlist(filters),
    queryFn: ({ signal }) =>
      get<TierItemOut[]>(
        "/tierlist",
        {
          tier: filters.tier,
          category_id: filters.category_id,
          limit: filters.limit,
        },
        signal,
      ),
  });
}

/** GET /items/{id}/score */
export function useItemScore(
  itemId: string | undefined,
): UseQueryResult<ItemScoreOut> {
  return useQuery({
    queryKey: queryKeys.itemScore(itemId ?? ""),
    enabled: Boolean(itemId),
    queryFn: ({ signal }) =>
      get<ItemScoreOut>(`/items/${itemId}/score`, undefined, signal),
  });
}

/** GET /research?has_competitors=&limit= */
export function useResearchList(
  filters: ResearchListFilters = {},
): UseQueryResult<ItemResearchOut[]> {
  return useQuery({
    queryKey: queryKeys.research(filters),
    queryFn: ({ signal }) =>
      get<ItemResearchOut[]>(
        "/research",
        { has_competitors: filters.has_competitors, limit: filters.limit },
        signal,
      ),
  });
}

/** GET /items/{id}/research */
export function useItemResearch(
  itemId: string | undefined,
): UseQueryResult<ItemResearchOut> {
  return useQuery({
    queryKey: queryKeys.itemResearch(itemId ?? ""),
    enabled: Boolean(itemId),
    queryFn: ({ signal }) =>
      get<ItemResearchOut>(`/items/${itemId}/research`, undefined, signal),
  });
}

/** GET /items/{id}/competitors?limit= — returns SearchHitOut rows. */
export function useCompetitors(
  itemId: string | undefined,
  limit = 10,
): UseQueryResult<SearchHitOut[]> {
  return useQuery({
    queryKey: queryKeys.competitors(itemId ?? "", limit),
    enabled: Boolean(itemId),
    queryFn: ({ signal }) =>
      get<SearchHitOut[]>(`/items/${itemId}/competitors`, { limit }, signal),
  });
}

// ---------------------------------------------------------------------------
// Mutations / actions
// ---------------------------------------------------------------------------

/** POST /search — semantic search. Body { query, limit }. */
export function useSearch(): UseMutationResult<
  SearchHitOut[],
  unknown,
  SearchQueryIn
> {
  return useMutation({
    mutationFn: (body: SearchQueryIn) =>
      post<SearchHitOut[]>("/search", body),
  });
}

/** POST /classify — run classification pass. */
export function useRunClassify(): UseMutationResult<
  ClassifyRunOut,
  unknown,
  RunLimitParams | void
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: RunLimitParams | void) =>
      post<ClassifyRunOut>("/classify", undefined, {
        limit: params ? params.limit : undefined,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.categories });
      void qc.invalidateQueries({ queryKey: queryKeys.categoriesPending });
    },
  });
}

/** POST /score — run scoring pass. */
export function useRunScore(): UseMutationResult<
  ScoreRunOutResult,
  unknown,
  RunLimitParams | void
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: RunLimitParams | void) =>
      post<ScoreRunOutResult>("/score", undefined, {
        limit: params ? params.limit : undefined,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tierlist"] });
    },
  });
}

/** POST /research — run web-research pass. */
export function useRunResearch(): UseMutationResult<
  ResearchRunOut,
  unknown,
  RunResearchParams | void
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: RunResearchParams | void) =>
      post<ResearchRunOut>("/research", undefined, {
        limit: params ? params.limit : undefined,
        min_tier: params ? params.min_tier : undefined,
        min_coefficient: params ? params.min_coefficient : undefined,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["research"] });
    },
  });
}

/** POST /embed — run embedding pass. */
export function useRunEmbed(): UseMutationResult<
  EmbedRunOut,
  unknown,
  RunLimitParams | void
> {
  return useMutation({
    mutationFn: (params: RunLimitParams | void) =>
      post<EmbedRunOut>("/embed", undefined, {
        limit: params ? params.limit : undefined,
      }),
  });
}

/** POST /categories/{id}/approve */
export function useApproveCategory(): UseMutationResult<
  ApproveResult,
  unknown,
  string
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      post<ApproveResult>(`/categories/${id}/approve`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.categories });
      void qc.invalidateQueries({ queryKey: queryKeys.categoriesPending });
    },
  });
}

/** POST /categories/{id}/reject */
export function useRejectCategory(): UseMutationResult<
  RejectResult,
  unknown,
  string
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => post<RejectResult>(`/categories/${id}/reject`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.categories });
      void qc.invalidateQueries({ queryKey: queryKeys.categoriesPending });
    },
  });
}

// ---------------------------------------------------------------------------
// Collect hooks
// ---------------------------------------------------------------------------

/** GET /collect/sources */
export function useCollectorSources(): UseQueryResult<CollectorSourcesOut> {
  return useQuery({
    queryKey: queryKeys.collectSources,
    queryFn: ({ signal }) =>
      get<CollectorSourcesOut>("/collect/sources", undefined, signal),
  });
}

/** POST /collect/jobs — kick off a manual collect run. */
export function useRunCollect(): UseMutationResult<
  CollectJobOut,
  unknown,
  { source: string }
> {
  return useMutation({
    mutationFn: (body: { source: string }) =>
      post<CollectJobOut>("/collect/jobs", body),
  });
}

const ACTIVE_STATUSES = new Set(["queued", "running"]);

/** GET /collect/jobs/{id} — polls while queued/running, stops on success/failed. */
export function useCollectJob(
  jobId: string | null,
): UseQueryResult<CollectJobOut> {
  return useQuery({
    queryKey: queryKeys.collectJob(jobId ?? ""),
    enabled: !!jobId,
    queryFn: ({ signal }) =>
      get<CollectJobOut>(`/collect/jobs/${jobId}`, undefined, signal),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && !ACTIVE_STATUSES.has(status) ? false : 1500;
    },
  });
}

/** GET /collect/schedule */
export function useCollectorSchedule(): UseQueryResult<ScheduleOut> {
  return useQuery({
    queryKey: queryKeys.collectSchedule,
    queryFn: ({ signal }) =>
      get<ScheduleOut>("/collect/schedule", undefined, signal),
  });
}

/** PUT /collect/schedule/{source} — set or clear a cron schedule. */
export function useUpdateSchedule(): UseMutationResult<
  ScheduleOut,
  unknown,
  { source: string; cron: string }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ source, cron }: { source: string; cron: string }) =>
      apiFetch<ScheduleOut>(`/collect/schedule/${source}`, {
        method: "PUT",
        body: { cron } satisfies ScheduleUpdateRequest,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.collectSchedule });
    },
  });
}
