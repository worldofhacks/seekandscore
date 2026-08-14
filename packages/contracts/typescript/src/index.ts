export type CandidateStrategy =
  | "Parcel screening"
  | "Buildable land"
  | "Lifestyle"
  | "Distress"
  | "Airport parking"
  | "Event parking"
  | "Land banking"
  | "Auction"
  | "Opportunity Zone";

export type CandidateQueueState = "new" | "research" | "watching" | "ready";

export type EvidenceStatus =
  | "verified"
  | "estimated"
  | "stale"
  | "conflicting"
  | "unknown";

export type RiskSeverity = "critical" | "elevated" | "watch";

export type OutreachGateStatus = "blocked" | "needs_review" | "ready";

export type DatasetMode = "live" | "unknown";

export type DatasetHealthStatus =
  | "current"
  | "stale"
  | "partial"
  | "error"
  | "rights_disabled"
  | "unavailable"
  | "unknown";

export type DataSourceStatus = "current" | "stale" | "error" | "unavailable" | "unknown";

export interface MoneyRange {
  low: number;
  high: number;
}

export interface EvidenceDatum {
  id: string;
  label: string;
  value: string;
  status: EvidenceStatus;
  source: string;
  observedAt: string;
  detail?: string;
}

export interface CandidateRisk {
  id: string;
  label: string;
  detail: string;
  severity: RiskSeverity;
}

export interface OutreachGate {
  status: OutreachGateStatus;
  reviewedChecks: number;
  totalChecks: number;
  blockers: string[];
}

export interface CandidateSummary {
  id: string;
  rank: number;
  previousRank: number | null;
  name: string;
  locality: string;
  county: string;
  parcelId: string;
  acreage: number;
  strategy: CandidateStrategy;
  queueState: CandidateQueueState;
  overallScore: number;
  confidence: number;
  valueRange: MoneyRange;
  likelyBasis: number;
  thesis: string;
  nextAction: string;
  newSinceLastReview: boolean;
  materialChange: string | null;
  risks: CandidateRisk[];
  evidence: EvidenceDatum[];
  outreachGate: OutreachGate;
  screeningOnly?: boolean;
  sourceObservation?: SourceObservation;
}

export interface SourceObservationFields {
  marketValueCents?: number;
  appraisedValueCents?: number;
  assessedValueCents?: number;
  landValueCents?: number;
  improvementValueCents?: number;
  acreage?: number;
}

export interface SourceObservation {
  sourceId: string;
  sourceRecordId: string;
  artifactSha256: string;
  retrievedAt: string;
  fields: SourceObservationFields;
}

export interface DataSourceProvenance {
  id: string;
  name: string;
  status: DataSourceStatus;
  retrievedAt: string | null;
  publishedAt: string | null;
  recordCount: number | null;
  detail?: string;
}

export interface DatasetProvenance {
  mode: DatasetMode;
  status: DatasetHealthStatus;
  retrievedAt: string | null;
  publishedAt: string | null;
  staleAfter: string | null;
  statusDetail: string | null;
  sources: DataSourceProvenance[];
  warnings: string[];
}

export interface CandidateAppliedFilters {
  q: string | null;
  city: string | null;
  minAcres: number | null;
  maxAcres: number | null;
}

export interface CandidateCohortPage {
  cohortTotal: number;
  filteredTotal: number;
  nextCursor: string | null;
  appliedFilters: CandidateAppliedFilters;
}

export interface TopQueueSnapshot {
  id: string;
  label: string;
  region: string;
  timeZone: string;
  asOf: string | null;
  modelVersion: string;
  provenance: DatasetProvenance;
  cohort: CandidateCohortPage;
  candidates: CandidateSummary[];
}

/** Wire contract returned by the FastAPI candidate read model. */
export interface ApiEvidenceSummary {
  source_count: number;
  unresolved_conflict_count: number;
  freshness: string;
}

export interface ApiCandidateReadModel {
  id: string;
  display_name: string;
  locality: string;
  parcel_id: string;
  candidate_kind: "parcel" | "assemblage";
  parcel_count: number;
  jurisdiction_id: string;
  county_name: string;
  state_name: string;
  timezone: string;
  strategy: string;
  rank: number;
  previous_rank: number | null;
  queue_state: CandidateQueueState;
  opportunity_score: number;
  confidence: number;
  acreage: number;
  value_range: MoneyRange;
  likely_basis: number;
  thesis: string;
  opportunity_zone_status: "effective" | "outside" | "review";
  next_action: string;
  material_change: string | null;
  evidence: ApiEvidenceSummary;
  as_of: string;
  read_model_version: string;
  screening_only?: boolean;
  source_observation?: {
    source_id: string;
    source_record_id: string;
    artifact_sha256: string;
    retrieved_at: string;
    fields?: {
      market_value_cents?: number;
      appraised_value_cents?: number;
      assessed_value_cents?: number;
      land_value_cents?: number;
      improvement_value_cents?: number;
      acreage?: number;
    };
    market_value_cents?: number;
    appraised_value_cents?: number;
    assessed_value_cents?: number;
    land_value_cents?: number;
    improvement_value_cents?: number;
  };
}

export interface ApiDataSourceProvenance {
  id: string;
  name: string;
  status: DataSourceStatus;
  retrieved_at?: string | null;
  published_at?: string | null;
  record_count?: number | null;
  detail?: string;
}

export interface ApiCandidateAppliedFilters {
  q: string | null;
  city: "DEL VALLE" | "MANOR" | null;
  min_acres: number | null;
  max_acres: number | null;
}

export interface ApiCandidatePage {
  items: ApiCandidateReadModel[];
  next_cursor: string | null;
  total: number;
  cohort_total: number;
  applied_filters: ApiCandidateAppliedFilters;
  dataset_mode: string;
  read_model_version: string;
  dataset_status?: string;
  retrieved_at?: string | null;
  published_at?: string | null;
  stale_after?: string | null;
  partial?: boolean;
  sources?: ApiDataSourceProvenance[];
  warnings?: string[];
}

export type QueueFilter = "all" | "new" | "moved" | "needs_review";

export type {
  ApiCandidateDossier,
  ApiResearchCase,
  ApiResearchCasePage,
  ApiVerificationGate,
  ResearchStatus,
  VerificationGateKey,
  VerificationGateStatus,
} from "./research";
