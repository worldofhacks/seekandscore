import type { NextRequest } from "next/server";

import { proxyResearchRequest } from "@/lib/research-proxy";

interface ResearchCaseRouteContext {
  params: Promise<{ caseId: string }>;
}

export async function PATCH(request: NextRequest, context: ResearchCaseRouteContext) {
  const { caseId } = await context.params;
  return proxyResearchRequest(
    request,
    `/v1/research-cases/${encodeURIComponent(caseId)}`,
  );
}
