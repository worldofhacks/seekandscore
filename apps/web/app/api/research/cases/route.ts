import type { NextRequest } from "next/server";

import { proxyResearchRequest } from "@/lib/research-proxy";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.toString();
  const suffix = query ? `?${query}` : "";
  return proxyResearchRequest(request, `/v1/research-cases${suffix}`);
}
