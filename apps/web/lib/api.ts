import type {
  ApiCandidatePage,
  ApiCandidateReadModel,
  CandidateStrategy,
  CandidateSummary,
  DatasetHealthStatus,
  DatasetMode,
  EvidenceDatum,
  TopQueueSnapshot,
} from "@seekandscore/contracts";

import { topQueueSnapshot } from "./candidates";

const STRATEGIES: Record<string, CandidateStrategy> = {
  assemblage: "Land banking",
  infill: "Buildable land",
  "land-banking": "Land banking",
  "parcel-screening": "Parcel screening",
  assessor: "Parcel screening",
};

function datasetMode(value: string): DatasetMode {
  return value === "live" || value === "synthetic" || value === "mixed"
    ? value
    : "unknown";
}

function datasetStatus(page: ApiCandidatePage, mode: DatasetMode): DatasetHealthStatus {
  if (page.dataset_status) return page.dataset_status;
  if (page.partial) return "partial";
  return mode === "synthetic" ? "synthetic" : "unknown";
}

function sourceObservationFor(candidate: ApiCandidateReadModel) {
  const source = candidate.source_observation;
  if (!source) return undefined;
  const fields = source.fields ?? source;

  return {
    sourceId: source.source_id,
    sourceRecordId: source.source_record_id,
    artifactSha256: source.artifact_sha256,
    retrievedAt: source.retrieved_at,
    fields: {
      marketValueCents: fields.market_value_cents,
      appraisedValueCents: fields.appraised_value_cents,
      assessedValueCents: fields.assessed_value_cents,
      landValueCents: fields.land_value_cents,
      improvementValueCents: fields.improvement_value_cents,
      acreage: "acreage" in fields ? fields.acreage : undefined,
    },
  };
}

function observationValue(candidate: ApiCandidateReadModel): string | null {
  const source = candidate.source_observation;
  if (!source) return null;
  const fields = source.fields ?? source;
  const observed: Array<[string, number]> = [];
  if (fields.appraised_value_cents !== undefined) {
    observed.push(["Appraised", fields.appraised_value_cents]);
  }
  if (fields.assessed_value_cents !== undefined) {
    observed.push(["Assessed", fields.assessed_value_cents]);
  }
  if (fields.market_value_cents !== undefined) {
    observed.push(["Market", fields.market_value_cents]);
  }
  if (fields.land_value_cents !== undefined) {
    observed.push(["Land", fields.land_value_cents]);
  }
  if (!observed.length) return null;
  return observed
    .map(([label, cents]) => `${label} $${(cents / 100).toLocaleString("en-US")}`)
    .join(" · ");
}

function evidenceFor(candidate: ApiCandidateReadModel): EvidenceDatum[] {
  const conflictStatus =
    candidate.evidence.unresolved_conflict_count > 0 ? "conflicting" : "verified";
  const sourceObservation = candidate.source_observation;
  const observedValue = observationValue(candidate);
  const sourceLabel = sourceObservation?.source_id ?? `${candidate.county_name} parcel source`;
  const isLiveScreen = candidate.screening_only ?? Boolean(sourceObservation);

  const evidence: EvidenceDatum[] = [
    {
      id: `${candidate.id}-identity`,
      label: "Parcel identity",
      value: candidate.parcel_id,
      status: conflictStatus,
      source: candidate.synthetic
        ? `${candidate.county_name} synthetic registry`
        : sourceLabel,
      observedAt: candidate.as_of,
      detail: candidate.synthetic
        ? "Synthetic API observation used to validate the runtime contract."
        : "Official source observation; field and legal verification remain required.",
    },
    {
      id: `${candidate.id}-freshness`,
      label: candidate.synthetic ? "Fixture evidence status" : "Evidence freshness",
      value: candidate.evidence.freshness,
      status: candidate.evidence.freshness === "current" ? "verified" : "unknown",
      source: `${candidate.evidence.source_count} ${candidate.synthetic ? "synthetic fixture" : "source"} observation${candidate.evidence.source_count === 1 ? "" : "s"}`,
      observedAt: candidate.as_of,
      detail: candidate.synthetic
        ? "No production source or personal data is active."
        : "Freshness is evaluated against the configured source cadence.",
    },
  ];

  evidence.splice(1, 0, {
    id: `${candidate.id}-value`,
    label: isLiveScreen ? "Assessor value observation" : "Value range",
    value: observedValue ?? `$${candidate.value_range.low.toLocaleString("en-US")}–$${candidate.value_range.high.toLocaleString("en-US")}`,
    status: isLiveScreen ? conflictStatus : "estimated",
    source: isLiveScreen ? sourceLabel : "Synthetic comparable projection",
    observedAt: sourceObservation?.retrieved_at ?? candidate.as_of,
    detail: isLiveScreen
      ? "Published assessor values are source observations, not a platform valuation, offer, or acquisition basis."
      : "Scenario estimate; not an appraisal or offer recommendation.",
  });

  return evidence;
}

function mapCandidate(candidate: ApiCandidateReadModel): CandidateSummary {
  const evidence = evidenceFor(candidate);
  const needsIdentityReview = candidate.evidence.unresolved_conflict_count > 0;
  const sourceObservation = sourceObservationFor(candidate);
  const screeningOnly = candidate.screening_only ?? Boolean(sourceObservation);

  const summary: CandidateSummary = {
    id: candidate.id,
    rank: candidate.rank,
    previousRank: candidate.previous_rank,
    name: candidate.display_name,
    locality: candidate.locality,
    county: candidate.county_name.replace(/ County$/, ""),
    parcelId: candidate.parcel_id,
    acreage: candidate.acreage,
    strategy: screeningOnly
      ? "Parcel screening"
      : (STRATEGIES[candidate.strategy] ?? "Land banking"),
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
    screeningOnly,
    sourceObservation,
    risks: [
      {
        id: `${candidate.id}-conflicts`,
        label: needsIdentityReview ? "Evidence conflicts unresolved" : "Field verification pending",
        detail: needsIdentityReview
          ? `${candidate.evidence.unresolved_conflict_count} ${candidate.synthetic ? "synthetic fixture" : "source"} conflict${candidate.evidence.unresolved_conflict_count === 1 ? "" : "s"} require review.`
          : candidate.synthetic
            ? "Synthetic evidence is not a substitute for field or professional verification."
            : "Source observations are not a substitute for field or professional verification.",
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
        label: candidate.synthetic
          ? "Production sources disabled"
          : "Opportunity Zone status unverified",
        detail: candidate.synthetic
          ? "This record is a deterministic contract fixture, not a live investment lead."
          : "Opportunity Zone status remains unverified until a versioned spatial overlay completes.",
        severity: "watch",
      },
    ],
    outreachGate: {
      status: "blocked",
      reviewedChecks: needsIdentityReview ? 1 : 2,
      totalChecks: 5,
      blockers: [
        ...(screeningOnly
          ? ["Owner and authorized-representative data are not present"]
          : needsIdentityReview
            ? ["Responsible-party identity needs review"]
            : []),
        "No approved contact-point source",
        "Texas acquisition policy is not activated",
        "All outbound channels are disabled",
      ],
    },
  };

  if (screeningOnly && sourceObservation) {
    summary.thesis = `${candidate.thesis} Assessor values are shown only as source observations.`;
  }

  return summary;
}

export function mapApiCandidatePage(page: ApiCandidatePage): TopQueueSnapshot {
  const first = page.items[0];
  const requestedMode = datasetMode(page.dataset_mode);
  const retrievedAt = page.retrieved_at ?? null;
  const status = datasetStatus(page, requestedMode);
  const mode = status === "fallback" ? "synthetic" : requestedMode;
  const fallbackReason = status === "fallback"
    ? (page.warnings?.[0] ?? "The requested live dataset could not be served.")
    : null;
  return {
    id: `api-${page.read_model_version}`,
    label: "API candidates",
    region: "Central Texas",
    timeZone: first?.timezone ?? "UTC",
    asOf: first?.as_of ?? page.retrieved_at ?? null,
    modelVersion: `${page.read_model_version} · API contract`,
    isSynthetic: mode === "synthetic" || status === "fallback",
    provenance: {
      mode,
      status,
      retrievedAt,
      publishedAt: page.published_at ?? null,
      staleAfter: page.stale_after ?? null,
      isFallback: status === "fallback",
      fallbackReason,
      sources: (page.sources ?? []).map((source) => ({
        id: source.id,
        name: source.name,
        status: source.status,
        retrievedAt: source.retrieved_at ?? null,
        publishedAt: source.published_at ?? null,
        recordCount: source.record_count ?? null,
        detail: source.detail,
      })),
      warnings: page.warnings ?? [],
    },
    candidates: page.items.map(mapCandidate),
  };
}

function syntheticFallback(reason: string): TopQueueSnapshot {
  return {
    ...topQueueSnapshot,
    provenance: {
      ...topQueueSnapshot.provenance,
      status: "fallback",
      isFallback: true,
      fallbackReason: reason,
      warnings: [
        reason,
        "This is a deterministic synthetic fallback, not live property data.",
      ],
    },
  };
}

export async function loadTopQueueSnapshot(): Promise<TopQueueSnapshot> {
  const baseUrl = process.env.API_BASE_URL;
  if (!baseUrl) return syntheticFallback("The candidate API is not configured.");

  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/candidates?limit=25`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(3_000),
    });
    if (!response.ok) {
      return syntheticFallback(`The candidate API returned HTTP ${response.status}.`);
    }
    return mapApiCandidatePage((await response.json()) as ApiCandidatePage);
  } catch {
    return syntheticFallback("The candidate API was unavailable or timed out.");
  }
}
