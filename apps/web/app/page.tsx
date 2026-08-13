import { AppShell } from "@/components/app-shell";
import { OperatorConsole } from "@/components/operator-console";
import { loadTopQueueSnapshot } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const snapshot = await loadTopQueueSnapshot();
  return (
    <AppShell>
      <OperatorConsole snapshot={snapshot} />
    </AppShell>
  );
}
