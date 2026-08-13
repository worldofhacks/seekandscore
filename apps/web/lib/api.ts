import type {
  ApiCandidatePage,
  ApiCandidateReadModel,
  CandidateStrategy,
  CandidateSummary,
  EvidenceDatum,
  TopQueueSnapshot,
} from "@seekandscore/contracts";

import { topQueueSnapshot } from "./candidates";

const STRATEGIES: Record<string, CandidateStrategy> = {
  assemblage: "Land banking",
  infill: "Buildable land",
  "land-banking": "Land banking",
};

function evidenceFor(candidate: ApiCandidateReadModel): EvidenceDatum[] {
  const conflictStatus =
    candidate.evidence.unresolved_conflict_count > 0 ? "conflicting" : "verified";

  return [
    {
      id: `${candidate.id}-identity`,
      label: "Parcel identity",
      value: candidate.parcel_id,
      status: conflictStatus,
      source: `${candidate.county_name} synthetic registry`,
      observedAt: candidate.as_of,
      detail: "Synthetic API observation used to validate the runtime contract.",
    },
    {
      id: `${candidate.id}-value`,
      label: "Value range",
      value: `$${candidate.value_range.low.toLocaleString()}–$${candidate.value_range.high.toLocaleString()}`,
      status: "estimated",
      source: "Synthetic comparable projection",
      observedAt: candidate.as_of,
      detail: "Scenario estimate; not an appraisal or offer recommendation.",
    },
    {
      id: `${candidate.id}-freshness`,
      label: "Evidence freshness",
      value: candidate.evidence.freshness,
      status: candidate.evidence.freshness === "current" ? "verified" : "unknown",
      source: `${candidate.evidence.source_count} synthetic source observations`,
      observedAt: candidate.as_of,
      detail: "No production source or personal data is active.",
    },
  ];
}

function mapCandidate(candidate: ApiCandidateReadModel): CandidateSummary {
  const evidence = evidenceFor(candidate);
  const needsIdentityReview = candidate.evidence.unresolved_conflict_count > 0;

  return {
    id: candidate.id,
    rank: candidate.rank,
    previousRank: candidate.previous_rank,
    name: candidate.display_name,
    locality: candidate.locality,
    county: candidate.county_name.replace(/ County$/, ""),
    parcelId: candidate.parcel_id,
    acreage: candidate.acreage,
    strategy: STRATEGIES[candidate.strategy] ?? "Land banking",
    queueState: candidate.queue_state,
    overallScore: candidate.opportunity_score,
    confidence: candidate.confidence,
    valueRange: candidate.value_range,
    likelyBasis: candidate.likely_basis,
    thesis: candidate.thesis,
    nextAction: candidate.next_action,
    newSinceLastReview: candidate.previous_rank === null,
    materialChange: candidate.material_change,
    evidence,
    risks: [
      {
        id: `${candidate.id}-conflicts`,
        label: needsIdentityReview ? "Evidence conflicts unresolved" : "Field verification pending",
        detail: needsIdentityReview
          ? `${candidate.evidence.unresolved_conflict_count} synthetic conflicts require review.`
          : "Synthetic evidence is not a substitute for field or professional verification.",
        severity: needsIdentityReview ? "elevated" : "watch",
      },
      {
        id: `${candidate.id}-title`,
        label: "Title review not complete",
        detail: "No title, survey, legal, tax, or environmental conclusion is represented.",
        severity: "watch",
      },
      {
        id: `${candidate.id}-source`,
        label: "Production sources disabled",
        detail: "This record is a deterministic contract fixture, not a live investment lead.",
        severity: "watch",
      },
    ],
    outreachGate: {
      status: "blocked",
      reviewedChecks: needsIdentityReview ? 1 : 2,
      totalChecks: 5,
      blockers: [
        ...(needsIdentityReview ? ["Responsible-party identity needs review"] : []),
        "No approved contact-point source",
        "Texas acquisition policy is not activated",
        "All outbound channels are disabled",
      ],
    },
  };
}

export function mapApiCandidatePage(page: ApiCandidatePage): TopQueueSnapshot {
  const first = page.items[0];
  return {
    id: `api-${page.read_model_version}`,
    label: "API candidates",
    region: "Central Texas",
    timeZone: first?.timezone ?? "UTC",
    asOf: first?.as_of ?? new Date(0).toISOString(),
    modelVersion: `${page.read_model_version} · API contract`,
    isSynthetic: page.dataset_mode === "synthetic",
    candidates: page.items.map(mapCandidate),
  };
}

export async function loadTopQueueSnapshot(): Promise<TopQueueSnapshot> {
  const baseUrl = process.env.API_BASE_URL;
  if (!baseUrl) return topQueueSnapshot;

  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/candidates?limit=25`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(3_000),
    });
    if (!response.ok) return topQueueSnapshot;
    return mapApiCandidatePage((await response.json()) as ApiCandidatePage);
  } catch {
    return topQueueSnapshot;
  }
}
