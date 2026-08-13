import type { CandidateSummary, QueueFilter } from "@seekandscore/contracts";

export function formatMoneyCompact(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: value >= 1_000_000 ? 2 : 0,
  }).format(value);
}

export function rankMovement(
  candidate: Pick<CandidateSummary, "rank" | "previousRank">,
): number | null {
  if (candidate.previousRank === null) return null;
  return candidate.previousRank - candidate.rank;
}

export function filterCandidates(
  candidates: CandidateSummary[],
  filter: QueueFilter,
  search: string,
): CandidateSummary[] {
  const query = search.trim().toLocaleLowerCase();

  return candidates.filter((candidate) => {
    const filterMatches =
      filter === "all" ||
      (filter === "new" && candidate.newSinceLastReview) ||
      (filter === "moved" && (rankMovement(candidate) ?? 0) !== 0) ||
      (filter === "needs_review" && candidate.queueState === "research");

    if (!filterMatches) return false;
    if (!query) return true;

    return [
      candidate.name,
      candidate.locality,
      candidate.county,
      candidate.parcelId,
      candidate.strategy,
    ].some((value) => value.toLocaleLowerCase().includes(query));
  });
}
