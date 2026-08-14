import "server-only";

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const OPERATOR_HEADER = "x-seekandscore-operator";
const INTERNAL_TOKEN_HEADER = "X-SeekAndScore-Internal-Token";
const RAILWAY_PRIVATE_API_ORIGIN = "http://api.railway.internal:8000";
const MAX_RESEARCH_BODY_BYTES = 16 * 1024;

function problem(status: number, detail: string): NextResponse {
  return NextResponse.json(
    {
      type: "about:blank",
      title: status === 401 ? "Unauthorized" : "Request Error",
      status,
      detail,
    },
    {
      status,
      headers: { "Cache-Control": "private, no-store, max-age=0" },
    },
  );
}

export function validateResearchMutation(request: NextRequest): NextResponse | null {
  if (request.method === "GET" || request.method === "HEAD") return null;

  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLocaleLowerCase().startsWith("application/json")) {
    return problem(415, "Saved-research mutations require application/json.");
  }
  const expectedOrigin = researchPublicOrigin(request);
  if (!expectedOrigin) {
    return problem(503, "Saved research public origin is not configured.");
  }
  const origin = request.headers.get("origin");
  if (!origin || origin !== expectedOrigin) {
    return problem(403, "Saved-research mutation origin was rejected.");
  }
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite && fetchSite !== "same-origin") {
    return problem(403, "Cross-site saved-research mutations are not allowed.");
  }
  return null;
}

export async function proxyResearchRequest(
  request: NextRequest,
  upstreamPath: string,
): Promise<NextResponse> {
  if (process.env.RESEARCH_WRITES_ENABLED !== "true") {
    return problem(503, "Saved research is disabled by the web runtime gate.");
  }
  const baseUrl = process.env.API_BASE_URL;
  const internalToken = process.env.RESEARCH_INTERNAL_TOKEN;
  const operator = request.headers.get(OPERATOR_HEADER);
  const apiOrigin = researchApiOrigin(baseUrl);
  const publicOrigin = researchPublicOrigin(request);
  if (!apiOrigin || !publicOrigin || !internalToken || internalToken.length < 32) {
    return problem(503, "Saved research is not configured.");
  }
  if (!operator) {
    return problem(401, "Authenticated operator identity is missing.");
  }
  const mutationError = validateResearchMutation(request);
  if (mutationError) return mutationError;

  const headers = new Headers({
    Accept: "application/json",
    [INTERNAL_TOKEN_HEADER]: internalToken,
  });
  const ifMatch = request.headers.get("if-match");
  if (ifMatch) headers.set("If-Match", ifMatch);
  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  if (hasBody) headers.set("Content-Type", "application/json");
  let body: string | undefined;
  if (hasBody) {
    const declaredLength = request.headers.get("content-length");
    if (declaredLength) {
      const parsedLength = Number(declaredLength);
      if (!Number.isSafeInteger(parsedLength) || parsedLength > MAX_RESEARCH_BODY_BYTES) {
        return problem(413, "Saved-research request body is too large.");
      }
    }
    body = await request.text();
    if (new TextEncoder().encode(body).byteLength > MAX_RESEARCH_BODY_BYTES) {
      return problem(413, "Saved-research request body is too large.");
    }
  }

  try {
    const upstream = await fetch(`${apiOrigin}${upstreamPath}`, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(5_000),
    });
    const responseHeaders = new Headers({
      "Cache-Control": "private, no-store, max-age=0",
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
    });
    const etag = upstream.headers.get("etag");
    if (etag) responseHeaders.set("ETag", etag);
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return problem(502, "The private research service is unavailable.");
  }
}

function researchPublicOrigin(request: NextRequest): string | null {
  const appEnv = process.env.APP_ENV;
  const localRuntime =
    process.env.NODE_ENV !== "production" &&
    (appEnv === undefined || appEnv === "development" || appEnv === "test");
  if (localRuntime) {
    return request.nextUrl.origin;
  }
  if (appEnv !== "staging" && appEnv !== "production") {
    return null;
  }

  const value = process.env.WEB_PUBLIC_ORIGIN;
  if (!value) return null;
  try {
    const url = new URL(value);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.pathname !== "/" ||
      url.search ||
      url.hash ||
      value !== url.origin
    ) {
      return null;
    }
    return url.origin;
  } catch {
    return null;
  }
}

function researchApiOrigin(value: string | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (
      url.username ||
      url.password ||
      url.pathname !== "/" ||
      url.search ||
      url.hash
    ) {
      return null;
    }
    const origin = url.origin;
    const appEnv = process.env.APP_ENV ?? "development";
    if (appEnv === "staging" || appEnv === "production") {
      return origin === RAILWAY_PRIVATE_API_ORIGIN ? origin : null;
    }
    const localHost = url.hostname === "localhost" || url.hostname === "127.0.0.1";
    const testHost = appEnv === "test" && url.hostname.endsWith(".internal");
    return localHost || testHost ? origin : null;
  } catch {
    return null;
  }
}
