import type {
  ApiCandidateDossier,
  ApiResearchCase,
  ResearchStatus,
} from "@seekandscore/contracts";

export interface ResearchCaseCreateInput {
  status?: ResearchStatus;
  operator_note?: string | null;
  next_action?: string | null;
}

export interface ResearchCasePatchInput {
  status?: ResearchStatus;
  operator_note?: string | null;
  next_action?: string | null;
}

export type ResearchErrorCode =
  | "unauthorized"
  | "conflict"
  | "stale"
  | "unavailable"
  | "not_found"
  | "invalid"
  | "unknown";

export class ResearchRequestError extends Error {
  readonly status: number;
  readonly code: ResearchErrorCode;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ResearchRequestError";
    this.status = status;
    this.code = errorCode(status);
    this.detail = detail;
  }
}

function errorCode(status: number): ResearchErrorCode {
  if (status === 401 || status === 403) return "unauthorized";
  if (status === 409) return "conflict";
  if (status === 412) return "stale";
  if (status === 404) return "not_found";
  if (status === 502 || status === 503 || status === 504) return "unavailable";
  if (status === 400 || status === 415 || status === 422 || status === 428) {
    return "invalid";
  }
  return "unknown";
}

function problemDetail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

function isResearchCase(value: unknown): value is ApiResearchCase {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<ApiResearchCase>;
  return (
    typeof item.id === "string" &&
    typeof item.candidate_id === "string" &&
    typeof item.candidate_read_model_version === "string" &&
    typeof item.updated_at === "string" &&
    typeof item.version === "number" &&
    Number.isInteger(item.version) &&
    item.version >= 1 &&
    (item.status === "watching" ||
      item.status === "researching" ||
      item.status === "passed" ||
      item.status === "archived") &&
    (item.operator_note === null || typeof item.operator_note === "string") &&
    (item.next_action === null || typeof item.next_action === "string")
  );
}

function isVerificationGate(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const gate = value as Record<string, unknown>;
  const validKey =
    gate.key === "parcel_identity" ||
    gate.key === "source_freshness" ||
    gate.key === "opportunity_zone" ||
    gate.key === "underwriting" ||
    gate.key === "contact_prep";
  const validStatus =
    gate.status === "satisfied" ||
    gate.status === "open" ||
    gate.status === "blocked" ||
    gate.status === "not_available";
  return (
    validKey &&
    validStatus &&
    typeof gate.reason_code === "string" &&
    typeof gate.detail === "string" &&
    Array.isArray(gate.evidence_ids) &&
    gate.evidence_ids.every((evidenceId) => typeof evidenceId === "string")
  );
}

function isCandidateDossier(
  value: unknown,
  candidateId: string,
): value is ApiCandidateDossier {
  if (!value || typeof value !== "object") return false;
  const dossier = value as Partial<ApiCandidateDossier>;
  const candidate = dossier.candidate;
  const controls = dossier.controls;
  return (
    Boolean(candidate) &&
    typeof candidate === "object" &&
    candidate?.id === candidateId &&
    Array.isArray(dossier.gates) &&
    dossier.gates.every(isVerificationGate) &&
    Boolean(controls) &&
    typeof controls === "object" &&
    typeof controls?.contact_prep_enabled === "boolean" &&
    typeof controls?.outbound_enabled === "boolean" &&
    (dossier.research_case === null || isResearchCase(dossier.research_case))
  );
}

async function responseBody(response: Response): Promise<unknown> {
  const raw = await response.text();
  if (!raw) return null;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

async function requestJson(
  url: string,
  init: RequestInit,
): Promise<{ body: unknown; etag: string | null }> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...init.headers,
      },
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ResearchRequestError(502, "The private research service is unavailable.");
  }

  const body = await responseBody(response);
  if (!response.ok) {
    throw new ResearchRequestError(
      response.status,
      problemDetail(body, `Saved research returned HTTP ${response.status}.`),
    );
  }
  return { body, etag: response.headers.get("etag") };
}

export async function getCandidateDossier(
  candidateId: string,
  signal?: AbortSignal,
): Promise<ApiCandidateDossier> {
  const { body } = await requestJson(
    `/api/research/candidates/${encodeURIComponent(candidateId)}`,
    { method: "GET", signal },
  );
  if (!isCandidateDossier(body, candidateId)) {
    throw new ResearchRequestError(502, "The research service returned an invalid dossier.");
  }
  return body;
}

export async function createResearchCase(
  candidateId: string,
  input: ResearchCaseCreateInput = { status: "watching" },
): Promise<ApiResearchCase> {
  const { body } = await requestJson(
    `/api/research/candidates/${encodeURIComponent(candidateId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  if (!isResearchCase(body) || body.candidate_id !== candidateId) {
    throw new ResearchRequestError(
      502,
      "The research service returned an invalid saved case.",
    );
  }
  return body;
}

export async function updateResearchCase(
  researchCase: Pick<ApiResearchCase, "id" | "version" | "candidate_id">,
  input: ResearchCasePatchInput,
): Promise<ApiResearchCase> {
  const { body } = await requestJson(
    `/api/research/cases/${encodeURIComponent(researchCase.id)}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "If-Match": `"${researchCase.version}"`,
      },
      body: JSON.stringify(input),
    },
  );
  if (
    !isResearchCase(body) ||
    body.id !== researchCase.id ||
    body.candidate_id !== researchCase.candidate_id
  ) {
    throw new ResearchRequestError(
      502,
      "The research service returned an invalid updated case.",
    );
  }
  return body;
}

export function researchErrorMessage(error: unknown): string {
  if (!(error instanceof ResearchRequestError)) {
    return "Saved research could not be loaded. Candidate evidence remains read-only.";
  }
  if (error.code === "unauthorized") {
    return "Your authenticated operator session is unavailable. Reload and sign in again.";
  }
  if (error.code === "stale") {
    return "This research case changed in another session. The latest version is being loaded; review it before saving again.";
  }
  if (error.code === "conflict") {
    return `The requested research status change was rejected. ${error.detail}`;
  }
  if (error.code === "unavailable") {
    return "Saved research is temporarily unavailable. Candidate evidence remains read-only.";
  }
  if (error.code === "not_found") {
    return "This candidate or saved research case is no longer available.";
  }
  if (error.code === "invalid") {
    return `The saved-research request was rejected. ${error.detail}`;
  }
  return "Saved research could not be completed. Candidate evidence remains read-only.";
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}
