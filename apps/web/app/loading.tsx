import { Spinner } from "@seekandscore/ui";

export default function Loading() {
  return (
    <div aria-busy="true" aria-label="Loading live cohort" className="loading-shell">
      <div className="loading-sidebar" />
      <main className="loading-main">
        <Spinner label="Loading live cohort" />
        <div className="loading-line" />
        <div className="loading-metrics">
          {Array.from({ length: 4 }, (_, index) => (
            <div className="loading-card" key={index} />
          ))}
        </div>
        <div className="loading-card loading-table" />
      </main>
    </div>
  );
}
