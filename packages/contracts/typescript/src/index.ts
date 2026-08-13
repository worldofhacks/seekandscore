export type CandidateStrategy =
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
}

export interface TopQueueSnapshot {
  id: string;
  label: string;
  region: string;
  timeZone: string;
  asOf: string;
  modelVersion: string;
  isSynthetic: boolean;
  candidates: CandidateSummary[];
}

/** Wire contract returned by the current FastAPI synthetic read model. */
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
  synthetic: boolean;
  read_model_version: string;
}

export interface ApiCandidatePage {
  items: ApiCandidateReadModel[];
  next_cursor: string | null;
  total: number;
  dataset_mode: string;
  read_model_version: string;
}

export type QueueFilter = "all" | "new" | "moved" | "needs_review";
