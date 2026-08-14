import type { CandidateAppliedFilters } from "@seekandscore/contracts";

export const CANDIDATE_PAGE_SIZE = 50;

export type CandidateSearchParams = Record<
  string,
  string | string[] | undefined
>;

export interface CandidateQuery extends CandidateAppliedFilters {
  cursor: string | null;
}

const EMPTY_FILTERS: CandidateAppliedFilters = {
  q: null,
  city: null,
  minAcres: null,
  maxAcres: null,
};

function firstValue(value: string | string[] | undefined): string | null {
  const candidate = Array.isArray(value) ? value[0] : value;
  const trimmed = candidate?.trim();
  return trimmed ? trimmed : null;
}

function nonNegativeNumber(value: string | null): number | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

export function parseCandidateQuery(
  params: CandidateSearchParams,
): CandidateQuery {
  return {
    q: firstValue(params.q),
    city: firstValue(params.city),
    minAcres: nonNegativeNumber(firstValue(params.min_acres)),
    maxAcres: nonNegativeNumber(firstValue(params.max_acres)),
    cursor: firstValue(params.cursor),
  };
}

export function candidateFiltersFromQuery(
  query?: CandidateQuery,
): CandidateAppliedFilters {
  if (!query) return { ...EMPTY_FILTERS };
  return {
    q: query.q,
    city: query.city,
    minAcres: query.minAcres,
    maxAcres: query.maxAcres,
  };
}

function appendFilters(
  params: URLSearchParams,
  filters: CandidateAppliedFilters,
) {
  if (filters.q) params.set("q", filters.q);
  if (filters.city) params.set("city", filters.city);
  if (filters.minAcres !== null) {
    params.set("min_acres", String(filters.minAcres));
  }
  if (filters.maxAcres !== null) {
    params.set("max_acres", String(filters.maxAcres));
  }
}

export function buildCandidateApiQuery(query: CandidateQuery): string {
  const params = new URLSearchParams({ limit: String(CANDIDATE_PAGE_SIZE) });
  appendFilters(params, query);
  if (query.cursor) params.set("cursor", query.cursor);
  return params.toString();
}

export function buildCandidateExplorerHref(
  filters: CandidateAppliedFilters,
  cursor: string,
): string {
  const params = new URLSearchParams();
  appendFilters(params, filters);
  params.set("cursor", cursor);
  return `/?${params.toString()}`;
}

export function hasCandidateFilters(
  filters: CandidateAppliedFilters,
): boolean {
  return Boolean(
    filters.q ||
      filters.city ||
      filters.minAcres !== null ||
      filters.maxAcres !== null,
  );
}
