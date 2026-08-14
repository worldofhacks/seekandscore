import type { ApiCandidateReadModel } from "./index";

export type ResearchStatus = "watching" | "researching" | "passed" | "archived";
export type VerificationGateKey =
  | "parcel_identity"
  | "source_freshness"
  | "opportunity_zone"
  | "underwriting"
  | "contact_prep";
export type VerificationGateStatus =
  | "satisfied"
  | "open"
  | "blocked"
  | "not_available";

export interface ApiResearchCase {
  id: string;
  organization_id: string;
  candidate_id: string;
  region_id: string;
  jurisdiction_id: string;
  parcel_id: string;
  status: ResearchStatus;
  operator_note: string | null;
  next_action: string | null;
  candidate_read_model_version: string;
  candidate_as_of: string;
  version: number;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

export interface ApiVerificationGate {
  key: VerificationGateKey;
  status: VerificationGateStatus;
  reason_code: string;
  detail: string;
  evidence_ids: string[];
}

export interface ApiCandidateDossier {
  candidate: ApiCandidateReadModel;
  region_id: string;
  gates: ApiVerificationGate[];
  research_case: ApiResearchCase | null;
  controls: {
    contact_prep_enabled: false;
    outbound_enabled: false;
  };
}

export interface ApiResearchCasePage {
  items: ApiResearchCase[];
  next_cursor: string | null;
  total: number;
}
