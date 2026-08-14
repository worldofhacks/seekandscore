import { afterEach, describe, expect, it, vi } from "vitest";

import type { ApiCandidateDossier, ApiResearchCase } from "@seekandscore/contracts";

import {
  ResearchRequestError,
  createResearchCase,
  getCandidateDossier,
  researchErrorMessage,
  updateResearchCase,
} from "./research";

const candidateId = "11111111-1111-4111-8111-111111111111";

const researchCase: ApiResearchCase = {
  id: "22222222-2222-4222-8222-222222222222",
  organization_id: "33333333-3333-4333-8333-333333333333",
  candidate_id: candidateId,
  region_id: "us-tx-central-texas",
  jurisdiction_id: "us-tx-travis",
  parcel_id: "TCAD-700001",
  status: "watching",
  operator_note: null,
  next_action: null,
  candidate_read_model_version: "live-assessor-explorer-v2",
  candidate_as_of: "2026-08-13T10:30:00Z",
  version: 3,
  created_by: "44444444-4444-4444-8444-444444444444",
  updated_by: "44444444-4444-4444-8444-444444444444",
  created_at: "2026-08-13T10:30:00Z",
  updated_at: "2026-08-13T10:30:00Z",
};

const dossier = {
  candidate: { id: candidateId },
  region_id: "us-tx-central-texas",
  gates: [],
  research_case: researchCase,
  controls: { contact_prep_enabled: false, outbound_enabled: false },
} as unknown as ApiCandidateDossier;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("saved research client", () => {
  it("loads the selected candidate dossier from the same-origin route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(dossier), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getCandidateDossier(candidateId)).resolves.toEqual(dossier);
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/research/candidates/${candidateId}`,
      expect.objectContaining({
        method: "GET",
        cache: "no-store",
        credentials: "same-origin",
      }),
    );
  });

  it("creates a research case with an idempotent candidate PUT", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(researchCase), { status: 201 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(createResearchCase(candidateId)).resolves.toEqual(researchCase);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("PUT");
    expect(init.body).toBe(JSON.stringify({ status: "watching" }));
    expect(init.headers).toMatchObject({ "Content-Type": "application/json" });
  });

  it("patches with the quoted current version in If-Match", async () => {
    const updated = { ...researchCase, status: "researching", version: 4 };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(updated), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      updateResearchCase(researchCase, {
        status: "researching",
        operator_note: "Verify access.",
        next_action: "Order survey.",
      }),
    ).resolves.toEqual(updated);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/research/cases/${researchCase.id}`);
    expect(init.method).toBe("PATCH");
    expect(init.headers).toMatchObject({
      "Content-Type": "application/json",
      "If-Match": '"3"',
    });
  });

  it("classifies authentication, transition, stale-write, and unavailable errors", async () => {
    for (const [status, code] of [
      [401, "unauthorized"],
      [409, "conflict"],
      [412, "stale"],
      [503, "unavailable"],
    ] as const) {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          new Response(JSON.stringify({ detail: `detail-${status}` }), { status }),
        ),
      );
      const error = await getCandidateDossier(candidateId).catch((caught) => caught);
      expect(error).toBeInstanceOf(ResearchRequestError);
      expect((error as ResearchRequestError).code).toBe(code);
      expect(researchErrorMessage(error)).toBeTruthy();
    }
  });

  it("rejects a dossier for a different candidate", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            ...dossier,
            candidate: { ...dossier.candidate, id: "different-candidate" },
          }),
          { status: 200 },
        ),
      ),
    );

    await expect(getCandidateDossier(candidateId)).rejects.toMatchObject({
      code: "unavailable",
      status: 502,
    });
  });
});
