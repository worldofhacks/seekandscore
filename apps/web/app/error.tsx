"use client";

import { useEffect } from "react";

import { Button } from "@seekandscore/ui";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Operator console render failed", error);
  }, [error]);

  return (
    <main className="state-page">
      <section className="state-card">
        <span className="state-card__code">VIEW UNAVAILABLE</span>
        <h1>The investment queue could not load</h1>
        <p>
          The current snapshot is unchanged. Retry the view; no decisions or outreach actions
          were submitted.
        </p>
        <Button onClick={reset} variant="primary">
          Retry view
        </Button>
      </section>
    </main>
  );
}
