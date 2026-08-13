import type {
  ApiCandidatePage,
  ApiCandidateReadModel,
  CandidateStrategy,
  CandidateSummary,
  DatasetHealthStatus,
  EvidenceDatum,
  TopQueueSnapshot,
} from "@seekandscore/contracts";

const STRATEGIES: Record<string, CandidateStrategy> = {
  assemblage: "Land banking",
  infill: "Buildable land",
  "land-banking": "Land banking",
  "parcel-screening": "Parcel screening",
  assessor: "Parcel screening",
};

function datasetStatus(page: ApiCandidatePage): DatasetHealthStatus {
  if (page.partial) return "partial";
  if (
    page.dataset_status === "current" ||
    page.dataset_status === "stale" ||
    page.dataset_status === "partial" ||
    page.dataset_status === "error"
  ) {
    return page.dataset_status;
  }
  return "unknown";
}

function rightsDisplayDisabled(page: ApiCandidatePage): boolean {
  if (page.dataset_mode !== "live") return false;
  const warningText = (page.warnings ?? []).join(" ").toLocaleLowerCase();
  return (
    warningText.includes("display is disabled") ||
    warningText.includes("display rights") ||
    warningText.includes("rights review") ||
    warningText.includes("not approved for display")
  );
}

function sourceProvenance(page: ApiCandidatePage) {
  return (page.sources ?? []).map((source) => ({
    id: source.id,
    name: source.name,
    status: source.status,
    retrievedAt: source.retrieved_at ?? null,
    publishedAt: source.published_at ?? null,
    recordCount: source.record_count ?? null,
    detail: source.detail,
  }));
}

function isCandidatePage(value: unknown): value is ApiCandidatePage {
  if (!value || typeof value !== "object") return false;
  const page = value as Partial<ApiCandidatePage>;
  return (
    Array.isArray(page.items) &&
    typeof page.dataset_mode === "string" &&
    typeof page.read_model_version === "string"
  );
}

function emptyLiveSnapshot(
  reason: string,
  status: Extract<DatasetHealthStatus, "error" | "rights_disabled" | "unavailable">,
  page?: ApiCandidatePage,
  preserveLiveProvenance = false,
): TopQueueSnapshot {
  const isLiveResponse = page?.dataset_mode === "live";
  const livePage = isLiveResponse ? page : undefined;
  return {
    id: page ? `api-${page.read_model_version}-empty` : "live-api-unavailable",
    label: "Verified live candidates",
    region: "Central Texas",
    timeZone: "America/Chicago",
    asOf: preserveLiveProvenance ? (livePage?.retrieved_at ?? null) : null,
    modelVersion: "Live candidate contract · no publishable dataset",
    provenance: {
      mode: isLiveResponse ? "live" : "unknown",
      status,
      retrievedAt:
        preserveLiveProvenance ? (livePage?.retrieved_at ?? null) : null,
      publishedAt:
        preserveLiveProvenance ? (livePage?.published_at ?? null) : null,
      staleAfter:
        preserveLiveProvenance ? (livePage?.stale_after ?? null) : null,
      statusDetail: reason,
      sources: preserveLiveProvenance && livePage ? sourceProvenance(livePage) : [],
      warnings:
        preserveLiveProvenance && livePage && status !== "unavailable"
          ? (livePage.warnings ?? []).filter((warning) => warning !== reason)
          : [],
    },
    candidates: [],
  };
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
      source: sourceLabel,
      observedAt: candidate.as_of,
      detail: "Official source observation; field and legal verification remain required.",
    },
    {
      id: `${candidate.id}-freshness`,
      label: "Evidence freshness",
      value: candidate.evidence.freshness,
      status: candidate.evidence.freshness === "current" ? "verified" : "unknown",
      source: `${candidate.evidence.source_count} source observation${candidate.evidence.source_count === 1 ? "" : "s"}`,
      observedAt: candidate.as_of,
      detail: "Freshness is evaluated against the configured source cadence.",
    },
  ];

  evidence.splice(1, 0, {
    id: `${candidate.id}-value`,
    label: isLiveScreen ? "Assessor value observation" : "Source value observation",
    value: observedValue ?? "Not supplied",
    status: observedValue ? conflictStatus : "unknown",
    source: sourceLabel,
    observedAt: sourceObservation?.retrieved_at ?? candidate.as_of,
    detail: observedValue
      ? "Published assessor values are source observations, not a platform valuation, offer, or acquisition basis."
      : "No verified source value was supplied; the console does not substitute an estimate.",
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
          ? `${candidate.evidence.unresolved_conflict_count} source conflict${candidate.evidence.unresolved_conflict_count === 1 ? "" : "s"} require review.`
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
        label: "Opportunity Zone status unverified",
        detail: "Opportunity Zone status remains unverified until a versioned spatial overlay completes.",
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
  if (page.dataset_mode !== "live") {
    return emptyLiveSnapshot(
      "The candidate API did not return a verified live dataset. No records were displayed.",
      "unavailable",
      page,
    );
  }

  if (rightsDisplayDisabled(page)) {
    return emptyLiveSnapshot(
      page.warnings?.[0] ?? "Live source observations are not approved for public display.",
      "rights_disabled",
      page,
      true,
    );
  }

  const status = datasetStatus(page);
  if (status !== "current" && status !== "stale" && status !== "partial") {
    return emptyLiveSnapshot(
      status === "error"
        ? (page.warnings?.[0] ?? "The live candidate dataset reported an error.")
        : "The live candidate API did not report a publishable dataset status. No records were displayed.",
      status === "error" ? "error" : "unavailable",
      page,
      true,
    );
  }

  const first = page.items[0];
  return {
    id: `api-${page.read_model_version}`,
    label: "Verified live candidates",
    region: "Central Texas",
    timeZone: first?.timezone ?? "UTC",
    asOf: first?.as_of ?? page.retrieved_at ?? null,
    modelVersion: `${page.read_model_version} · API contract`,
    provenance: {
      mode: "live",
      status,
      retrievedAt: page.retrieved_at ?? null,
      publishedAt: page.published_at ?? null,
      staleAfter: page.stale_after ?? null,
      statusDetail: page.warnings?.[0] ?? null,
      sources: sourceProvenance(page),
      warnings: page.warnings ?? [],
    },
    candidates: page.items.map(mapCandidate),
  };
}

export async function loadTopQueueSnapshot(): Promise<TopQueueSnapshot> {
  const baseUrl = process.env.API_BASE_URL;
  if (!baseUrl) {
    return emptyLiveSnapshot("The live candidate API is not configured.", "error");
  }

  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, "")}/v1/candidates?limit=25`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(3_000),
    });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      if (isCandidatePage(body)) return mapApiCandidatePage(body);
      return emptyLiveSnapshot(
        `The live candidate API returned HTTP ${response.status}.`,
        "error",
      );
    }
    return mapApiCandidatePage((await response.json()) as ApiCandidatePage);
  } catch {
    return emptyLiveSnapshot("The live candidate API was unavailable or timed out.", "error");
  }
}
