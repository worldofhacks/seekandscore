import type { NextRequest } from "next/server";

import { proxyResearchRequest } from "@/lib/research-proxy";

interface CandidateRouteContext {
  params: Promise<{ candidateId: string }>;
}

export async function GET(request: NextRequest, context: CandidateRouteContext) {
  const { candidateId } = await context.params;
  return proxyResearchRequest(
    request,
    `/v1/candidates/${encodeURIComponent(candidateId)}/dossier`,
  );
}

export async function PUT(request: NextRequest, context: CandidateRouteContext) {
  const { candidateId } = await context.params;
  return proxyResearchRequest(
    request,
    `/v1/candidates/${encodeURIComponent(candidateId)}/research-case`,
  );
}
