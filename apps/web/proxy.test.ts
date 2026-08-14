import { Buffer } from "node:buffer";

import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { proxy } from "./proxy";

function stagingCredentials(): void {
  vi.stubEnv("APP_ENV", "staging");
  vi.stubEnv("WEB_PRIVATE_ACCESS_ENABLED", "true");
  vi.stubEnv("WEB_PRIVATE_ACCESS_USERNAME", "operator");
  vi.stubEnv("WEB_PRIVATE_ACCESS_PASSWORD", "test-password-not-a-real-secret");
}

function authorization(username: string, password: string): string {
  return `Basic ${Buffer.from(`${username}:${password}`, "utf8").toString("base64")}`;
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("private access proxy", () => {
  it("keeps only the data-free health endpoint available when deployment auth is missing", () => {
    vi.stubEnv("APP_ENV", "staging");

    const health = proxy(new NextRequest("https://web.example.test/api/health"));
    const nearMatch = proxy(new NextRequest("https://web.example.test/api/health/details"));

    expect(health.status).toBe(200);
    expect(health.headers.get("x-middleware-next")).toBe("1");
    expect(nearMatch.status).toBe(503);
    expect(nearMatch.headers.get("cache-control")).toContain("no-store");
  });

  it("fails closed when the deployment gate is not exactly true", () => {
    vi.stubEnv("APP_ENV", "production");
    vi.stubEnv("WEB_PRIVATE_ACCESS_ENABLED", "false");

    const response = proxy(new NextRequest("https://web.example.test/"));

    expect(response.status).toBe(503);
    expect(response.headers.get("www-authenticate")).toBeNull();
  });

  it("fails closed when enabled credentials are blank or the username is ambiguous", () => {
    stagingCredentials();
    vi.stubEnv("WEB_PRIVATE_ACCESS_PASSWORD", "   ");
    expect(proxy(new NextRequest("https://web.example.test/")).status).toBe(503);

    vi.stubEnv("WEB_PRIVATE_ACCESS_PASSWORD", "test-password-not-a-real-secret");
    vi.stubEnv("WEB_PRIVATE_ACCESS_USERNAME", "operator:secondary");
    expect(proxy(new NextRequest("https://web.example.test/")).status).toBe(503);

    vi.stubEnv("WEB_PRIVATE_ACCESS_USERNAME", "operator");
    vi.stubEnv("WEB_PRIVATE_ACCESS_PASSWORD", "short-password");
    expect(proxy(new NextRequest("https://web.example.test/")).status).toBe(503);
  });

  it("challenges missing and incorrect credentials without caching the response", () => {
    stagingCredentials();

    const missing = proxy(new NextRequest("https://web.example.test/"));
    const incorrect = proxy(
      new NextRequest("https://web.example.test/", {
        headers: { authorization: authorization("operator", "wrong") },
      }),
    );

    for (const response of [missing, incorrect]) {
      expect(response.status).toBe(401);
      expect(response.headers.get("www-authenticate")).toBe(
        'Basic realm="SeekAndScore private", charset="UTF-8"',
      );
      expect(response.headers.get("cache-control")).toContain("no-store");
      expect(response.headers.get("x-robots-tag")).toContain("noindex");
    }
  });

  it("allows valid credentials on pages, RSC requests, and static assets", () => {
    stagingCredentials();
    const headers = {
      authorization: authorization("operator", "test-password-not-a-real-secret"),
    };

    for (const path of ["/", "/?_rsc=example", "/_next/static/chunks/app.js"]) {
      const response = proxy(new NextRequest(`https://web.example.test${path}`, { headers }));
      expect(response.status).toBe(200);
      expect(response.headers.get("x-middleware-next")).toBe("1");
      expect(response.headers.get("cache-control")).toContain("no-store");
      expect(response.headers.get("vary")).toBe("Authorization");
      expect(response.headers.get("x-middleware-request-authorization")).toBeNull();
      expect(response.headers.get("x-middleware-override-headers")).not.toContain(
        "authorization",
      );
      expect(response.headers.get("x-middleware-request-x-seekandscore-operator")).toBe(
        "operator",
      );
    }
  });

  it("replaces an untrusted inbound operator header with the authenticated identity", () => {
    stagingCredentials();
    const response = proxy(
      new NextRequest("https://web.example.test/", {
        headers: {
          authorization: authorization("operator", "test-password-not-a-real-secret"),
          "x-seekandscore-operator": "attacker",
        },
      }),
    );

    expect(response.headers.get("x-middleware-request-x-seekandscore-operator")).toBe(
      "operator",
    );
  });

  it("accepts the case-insensitive Basic scheme but rejects malformed tokens", () => {
    stagingCredentials();
    const token = authorization("operator", "test-password-not-a-real-secret").slice(6);

    const lowerCaseScheme = proxy(
      new NextRequest("https://web.example.test/", {
        headers: { authorization: `basic ${token}` },
      }),
    );
    const malformed = proxy(
      new NextRequest("https://web.example.test/", {
        headers: { authorization: `Basic ${token} trailing` },
      }),
    );

    expect(lowerCaseScheme.status).toBe(200);
    expect(malformed.status).toBe(401);
  });

  it("remains optional for explicit local development", () => {
    vi.stubEnv("APP_ENV", "development");
    vi.stubEnv("WEB_PRIVATE_ACCESS_ENABLED", "false");

    const response = proxy(new NextRequest("http://localhost:3000/"));

    expect(response.status).toBe(200);
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });

  it("strips spoofed identity and refuses research without enforced private access", () => {
    vi.stubEnv("APP_ENV", "development");
    vi.stubEnv("WEB_PRIVATE_ACCESS_ENABLED", "false");
    const spoofed = new NextRequest("http://localhost:3000/api/research/cases", {
      headers: { "x-seekandscore-operator": "attacker" },
    });

    const readOnly = proxy(spoofed);
    expect(readOnly.status).toBe(200);
    expect(
      readOnly.headers.get("x-middleware-request-x-seekandscore-operator"),
    ).toBeNull();

    vi.stubEnv("RESEARCH_WRITES_ENABLED", "true");
    expect(proxy(spoofed).status).toBe(503);
  });

  it("never treats a production process as local development", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("APP_ENV", "development");
    vi.stubEnv("WEB_PRIVATE_ACCESS_ENABLED", "false");

    expect(proxy(new NextRequest("https://web.example.test/")).status).toBe(503);
  });
});
