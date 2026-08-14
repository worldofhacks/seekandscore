import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type {
  ApiCandidateDossier,
  ApiResearchCase,
} from "@seekandscore/contracts";

import { ResearchRequestError } from "@/lib/research";

import {
  ContactPrepPanel,
  ResearchPanel,
  type DossierLoadState,
} from "./candidate-dossier";

const candidateId = "11111111-1111-4111-8111-111111111111";

const savedCase: ApiResearchCase = {
  id: "22222222-2222-4222-8222-222222222222",
  organization_id: "33333333-3333-4333-8333-333333333333",
  candidate_id: candidateId,
  region_id: "us-tx-central-texas",
  jurisdiction_id: "us-tx-travis",
  parcel_id: "TCAD-700001",
  status: "researching",
  operator_note: "Verify the assessor identity against a recorded instrument.",
  next_action: "Order a boundary survey after parcel identity resolves.",
  candidate_read_model_version: "live-assessor-explorer-v2",
  candidate_as_of: "2026-08-13T10:30:00Z",
  version: 4,
  created_by: "44444444-4444-4444-8444-444444444444",
  updated_by: "44444444-4444-4444-8444-444444444444",
  created_at: "2026-08-13T10:30:00Z",
  updated_at: "2026-08-13T11:45:00Z",
};

function readyState(researchCase: ApiResearchCase | null = savedCase): DossierLoadState {
  const dossier = {
    candidate: { id: candidateId },
    region_id: "us-tx-central-texas",
    gates: [
      {
        key: "contact_prep",
        status: "blocked",
        reason_code: "SERVER_CONTACT_EVIDENCE_REQUIRED",
        detail: "Unique server gate: approved responsible-party evidence is absent.",
        evidence_ids: [],
      },
      {
        key: "source_freshness",
        status: "satisfied",
        reason_code: "SOURCE_CURRENT",
        detail: "The server reports the source inside its freshness window.",
        evidence_ids: ["OBJECTID-42"],
      },
    ],
    research_case: researchCase,
    controls: { contact_prep_enabled: false, outbound_enabled: false },
  } as unknown as ApiCandidateDossier;
  return { status: "ready", candidateId, dossier };
}

const noMutation = { status: "idle" } as const;

describe("authenticated candidate dossier UI", () => {
  it("renders persisted status, notes, next action, and version from the backend case", () => {
    const markup = renderToStaticMarkup(
      <ResearchPanel
        mutation={noMutation}
        onCreate={vi.fn()}
        onRetry={vi.fn()}
        onSave={vi.fn()}
        state={readyState()}
        timeZone="America/Chicago"
      />,
    );

    expect(markup).toContain("Research status");
    expect(markup).toContain("Watching");
    expect(markup).toContain("Researching");
    expect(markup).toContain("Passed");
    expect(markup).toContain("Archived");
    expect(markup).toContain(savedCase.operator_note!);
    expect(markup).toContain(savedCase.next_action!);
    expect(markup).toContain("v4");
    expect(markup).toContain("live-assessor-explorer-v2");
    expect(markup).toContain('maxLength="4000"');
    expect(markup).toContain('maxLength="500"');
    expect(markup).toContain("version-matched writes");
  });

  it("offers an idempotent save action when no research case exists", () => {
    const markup = renderToStaticMarkup(
      <ResearchPanel
        mutation={noMutation}
        onCreate={vi.fn()}
        onRetry={vi.fn()}
        onSave={vi.fn()}
        state={readyState(null)}
        timeZone="America/Chicago"
      />,
    );

    expect(markup).toContain("This parcel is not saved");
    expect(markup).toContain("Save to research");
    expect(markup).toContain("does not verify any gate");
  });

  it("renders only server-returned gates and controls in contact preparation", () => {
    const markup = renderToStaticMarkup(
      <ContactPrepPanel onRetry={vi.fn()} state={readyState()} />,
    );

    expect(markup).toContain("Server-derived contact readiness");
    expect(markup).toContain("Unique server gate: approved responsible-party evidence is absent.");
    expect(markup).toContain("SERVER_CONTACT_EVIDENCE_REQUIRED");
    expect(markup).toContain("The server reports the source inside its freshness window.");
    expect(markup).toContain("Contact preparation");
    expect(markup).toContain("Outbound communication");
    expect(markup).toContain("Outbound disabled");
    expect(markup).not.toContain("Candidate and narrow business purpose are recorded");
    expect(markup).not.toContain("<button");
    expect(markup).not.toContain("<textarea");
  });

  it("shows authenticated and unavailable dossier errors without enabling writes", () => {
    const unauthorized: DossierLoadState = {
      status: "error",
      candidateId,
      error: new ResearchRequestError(401, "missing actor"),
    };
    const unavailable: DossierLoadState = {
      status: "error",
      candidateId,
      error: new ResearchRequestError(503, "disabled"),
    };

    const unauthorizedMarkup = renderToStaticMarkup(
      <ResearchPanel
        mutation={noMutation}
        onCreate={vi.fn()}
        onRetry={vi.fn()}
        onSave={vi.fn()}
        state={unauthorized}
        timeZone="America/Chicago"
      />,
    );
    const unavailableMarkup = renderToStaticMarkup(
      <ContactPrepPanel onRetry={vi.fn()} state={unavailable} />,
    );

    expect(unauthorizedMarkup).toContain("authenticated operator session is unavailable");
    expect(unavailableMarkup).toContain("temporarily unavailable");
    expect(unauthorizedMarkup).toContain("Retry dossier");
    expect(unavailableMarkup).toContain("Retry dossier");
  });
});
