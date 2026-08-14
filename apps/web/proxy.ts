import { Buffer } from "node:buffer";
import { createHash, timingSafeEqual } from "node:crypto";

import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const HEALTH_PATH = "/api/health";
const OPERATOR_HEADER = "x-seekandscore-operator";
const BASIC_CREDENTIAL_PATTERN = /^Basic ([A-Za-z0-9+/]+={0,2})$/i;

type PrivateAccessState =
  | { mode: "disabled" }
  | { mode: "enforced"; username: string; password: string }
  | { mode: "misconfigured" };

function isDeploymentEnvironment(): boolean {
  if (process.env.NODE_ENV === "production") {
    return true;
  }
  const appEnvironment = process.env.APP_ENV;
  if (appEnvironment === "development" || appEnvironment === "test") {
    return false;
  }
  if (appEnvironment === undefined) {
    return false;
  }
  return true;
}

function privateAccessState(): PrivateAccessState {
  const enabled = process.env.WEB_PRIVATE_ACCESS_ENABLED;

  if (enabled !== "true") {
    if (isDeploymentEnvironment() || (enabled !== undefined && enabled !== "false")) {
      return { mode: "misconfigured" };
    }
    return { mode: "disabled" };
  }

  const username = process.env.WEB_PRIVATE_ACCESS_USERNAME ?? "";
  const password = process.env.WEB_PRIVATE_ACCESS_PASSWORD ?? "";
  if (
    !username.trim() ||
    username.includes(":") ||
    !password.trim() ||
    password.length < 24
  ) {
    return { mode: "misconfigured" };
  }

  return { mode: "enforced", username, password };
}

function constantTimeEqual(left: string, right: string): boolean {
  const leftDigest = createHash("sha256").update(left, "utf8").digest();
  const rightDigest = createHash("sha256").update(right, "utf8").digest();
  return timingSafeEqual(leftDigest, rightDigest);
}

function hasValidAuthorization(
  authorization: string | null,
  username: string,
  password: string,
): boolean {
  if (!authorization || authorization.length > 8192) {
    return false;
  }

  const match = BASIC_CREDENTIAL_PATTERN.exec(authorization);
  if (!match) {
    return false;
  }

  const expected = Buffer.from(`${username}:${password}`, "utf8").toString("base64");
  return constantTimeEqual(match[1], expected);
}

function privateResponse(body: string, status: number, authenticate = false): NextResponse {
  const headers = new Headers({
    "Cache-Control": "private, no-store, max-age=0",
    "Content-Type": "text/plain; charset=utf-8",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
  });
  if (authenticate) {
    headers.set(
      "WWW-Authenticate",
      'Basic realm="SeekAndScore private", charset="UTF-8"',
    );
  }
  return new NextResponse(body, { status, headers });
}

export function proxy(request: NextRequest): NextResponse {
  if (request.nextUrl.pathname === HEALTH_PATH) {
    return NextResponse.next();
  }

  const state = privateAccessState();
  if (state.mode === "misconfigured") {
    return privateResponse("Private access is unavailable.\n", 503);
  }
  if (state.mode === "disabled") {
    if (process.env.RESEARCH_WRITES_ENABLED === "true") {
      return privateResponse("Saved research requires enforced private access.\n", 503);
    }
    const requestHeaders = new Headers(request.headers);
    requestHeaders.delete("authorization");
    requestHeaders.delete(OPERATOR_HEADER);
    return NextResponse.next({ request: { headers: requestHeaders } });
  }

  if (
    !hasValidAuthorization(
      request.headers.get("authorization"),
      state.username,
      state.password,
    )
  ) {
    return privateResponse("Authentication required.\n", 401, true);
  }

  const requestHeaders = new Headers(request.headers);
  requestHeaders.delete("authorization");
  requestHeaders.delete(OPERATOR_HEADER);
  requestHeaders.set(OPERATOR_HEADER, state.username);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Cache-Control", "private, no-store, max-age=0");
  response.headers.set("Vary", "Authorization");
  response.headers.set("X-Robots-Tag", "noindex, nofollow, noarchive");
  return response;
}

export const config = {
  matcher: "/:path*",
};
