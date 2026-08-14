import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { proxyResearchRequest, validateResearchMutation } from "./research-proxy";

function request(
  method: "GET" | "PUT" | "PATCH",
  headers: Record<string, string> = {},
): NextRequest {
  return new NextRequest("https://web.example.test/api/research/cases", {
    method,
    headers: {
      "x-seekandscore-operator": "operator",
      ...headers,
    },
    body: method === "GET" ? undefined : JSON.stringify({ status: "watching" }),
  });
}

function largeMutation(): NextRequest {
  return new NextRequest("https://web.example.test/api/research/cases", {
    method: "PUT",
    headers: {
      "content-type": "application/json",
      origin: "https://web.example.test",
      "sec-fetch-site": "same-origin",
      "x-seekandscore-operator": "operator",
    },
    body: JSON.stringify({ operator_note: "x".repeat(17 * 1024) }),
  });
}

function railwayMutation(origin: string): NextRequest {
  return new NextRequest(
    "http://web.railway.internal:3000/api/research/cases/example",
    {
      method: "PATCH",
      headers: {
        "content-type": "application/json",
        origin,
        "sec-fetch-site": "same-origin",
        "x-seekandscore-operator": "operator",
      },
      body: JSON.stringify({ status: "watching" }),
    },
  );
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("research proxy", () => {
  it("requires same-origin JSON mutations", () => {
    expect(validateResearchMutation(request("PUT"))?.status).toBe(415);
    expect(
      validateResearchMutation(
        request("PUT", {
          "content-type": "application/json",
          origin: "https://attacker.example",
        }),
      )?.status,
    ).toBe(403);
    expect(
      validateResearchMutation(
        request("PUT", {
          "content-type": "application/json",
          origin: "https://web.example.test",
          "sec-fetch-site": "cross-site",
        }),
      )?.status,
    ).toBe(403);
    expect(
      validateResearchMutation(
        request("PUT", {
          "content-type": "application/json",
          origin: "https://web.example.test",
          "sec-fetch-site": "same-origin",
        }),
      ),
    ).toBeNull();
  });

  it("accepts the configured public origin when Railway presents an internal request URL", () => {
    vi.stubEnv("APP_ENV", "staging");
    vi.stubEnv("WEB_PUBLIC_ORIGIN", "https://web-staging-7db2.up.railway.app");

    expect(
      validateResearchMutation(
        railwayMutation("https://web-staging-7db2.up.railway.app"),
      ),
    ).toBeNull();
    expect(
      validateResearchMutation(railwayMutation("https://attacker.example"))?.status,
    ).toBe(403);
  });

  it("fails closed on missing or invalid deployment public origins", () => {
    vi.stubEnv("APP_ENV", "production");
    expect(
      validateResearchMutation(
        railwayMutation("https://web-staging-7db2.up.railway.app"),
      )?.status,
    ).toBe(503);

    for (const invalid of [
      "http://web-staging-7db2.up.railway.app",
      "https://operator@web-staging-7db2.up.railway.app",
      "https://web-staging-7db2.up.railway.app/",
      "https://web-staging-7db2.up.railway.app/path",
      "https://web-staging-7db2.up.railway.app?preview=true",
      "https://web-staging-7db2.up.railway.app#fragment",
      "not-an-origin",
    ]) {
      vi.stubEnv("WEB_PUBLIC_ORIGIN", invalid);
      expect(
        validateResearchMutation(
          railwayMutation("https://web-staging-7db2.up.railway.app"),
        )?.status,
      ).toBe(503);
    }
  });

  it("does not contact the private API when deployment public-origin config is missing", async () => {
    vi.stubEnv("APP_ENV", "staging");
    vi.stubEnv("RESEARCH_WRITES_ENABLED", "true");
    vi.stubEnv("API_BASE_URL", "http://api.railway.internal:8000");
    vi.stubEnv("RESEARCH_INTERNAL_TOKEN", "t".repeat(40));
    const upstreamFetch = vi.fn();
    vi.stubGlobal("fetch", upstreamFetch);

    const response = await proxyResearchRequest(
      railwayMutation("https://web-staging-7db2.up.railway.app"),
      "/v1/research-cases/example",
    );

    expect(response.status).toBe(503);
    expect(upstreamFetch).not.toHaveBeenCalled();
  });

  it("fails closed when research writes are disabled or operator identity is absent", async () => {
    vi.stubEnv("APP_ENV", "test");
    vi.stubEnv("RESEARCH_WRITES_ENABLED", "false");
    expect((await proxyResearchRequest(request("GET"), "/v1/research-cases")).status).toBe(
      503,
    );

    vi.stubEnv("RESEARCH_WRITES_ENABLED", "true");
    vi.stubEnv("API_BASE_URL", "http://api.internal:8000");
    vi.stubEnv("RESEARCH_INTERNAL_TOKEN", "t".repeat(40));
    const noActor = new NextRequest("https://web.example.test/api/research/cases");
    expect((await proxyResearchRequest(noActor, "/v1/research-cases")).status).toBe(401);
  });

  it("keeps the internal token server-side and forwards the authenticated operator", async () => {
    vi.stubEnv("APP_ENV", "test");
    vi.stubEnv("RESEARCH_WRITES_ENABLED", "true");
    vi.stubEnv("API_BASE_URL", "http://api.internal:8000");
    vi.stubEnv("RESEARCH_INTERNAL_TOKEN", "t".repeat(40));
    const upstreamFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [], total: 0, next_cursor: null }), {
        status: 200,
        headers: { "content-type": "application/json", etag: '"2"' },
      }),
    );
    vi.stubGlobal("fetch", upstreamFetch);

    const response = await proxyResearchRequest(request("GET"), "/v1/research-cases");
    const init = upstreamFetch.mock.calls[0]?.[1] as RequestInit;
    const forwarded = init.headers as Headers;

    expect(response.status).toBe(200);
    expect(response.headers.get("etag")).toBe('"2"');
    expect(forwarded.get("X-SeekAndScore-Internal-Token")).toBe("t".repeat(40));
    expect(forwarded.has("X-SeekAndScore-Operator")).toBe(false);
    expect(response.headers.has("X-SeekAndScore-Internal-Token")).toBe(false);
    expect(init.redirect).toBe("error");
  });

  it("never sends the token to an unapproved deployment origin", async () => {
    vi.stubEnv("APP_ENV", "staging");
    vi.stubEnv("RESEARCH_WRITES_ENABLED", "true");
    vi.stubEnv("WEB_PUBLIC_ORIGIN", "https://web.example.test");
    vi.stubEnv("API_BASE_URL", "https://attacker.example");
    vi.stubEnv("RESEARCH_INTERNAL_TOKEN", "t".repeat(40));
    const upstreamFetch = vi.fn();
    vi.stubGlobal("fetch", upstreamFetch);

    const response = await proxyResearchRequest(request("GET"), "/v1/research-cases");

    expect(response.status).toBe(503);
    expect(upstreamFetch).not.toHaveBeenCalled();
  });

  it("rejects oversized mutation bodies before contacting the API", async () => {
    vi.stubEnv("APP_ENV", "test");
    vi.stubEnv("RESEARCH_WRITES_ENABLED", "true");
    vi.stubEnv("API_BASE_URL", "http://api.internal:8000");
    vi.stubEnv("RESEARCH_INTERNAL_TOKEN", "t".repeat(40));
    const upstreamFetch = vi.fn();
    vi.stubGlobal("fetch", upstreamFetch);

    const response = await proxyResearchRequest(
      largeMutation(),
      "/v1/candidates/example/research-case",
    );

    expect(response.status).toBe(413);
    expect(upstreamFetch).not.toHaveBeenCalled();
  });
});
