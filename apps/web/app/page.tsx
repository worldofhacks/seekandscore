import { AppShell } from "@/components/app-shell";
import { OperatorConsole } from "@/components/operator-console";
import { loadTopQueueSnapshot } from "@/lib/api";
import {
  parseCandidateQuery,
  type CandidateSearchParams,
} from "@/lib/candidate-query";

export const dynamic = "force-dynamic";

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<CandidateSearchParams>;
}) {
  const query = parseCandidateQuery(await searchParams);
  const snapshot = await loadTopQueueSnapshot(query);
  return (
    <AppShell snapshot={snapshot}>
      <OperatorConsole key={snapshot.id} snapshot={snapshot} />
    </AppShell>
  );
}
