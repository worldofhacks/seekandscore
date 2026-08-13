"use client";

import { useMemo, useState } from "react";

import type {
  CandidateSummary,
  EvidenceStatus,
  QueueFilter,
  TopQueueSnapshot,
} from "@seekandscore/contracts";
import { Badge, Button, IconButton, Panel, VisuallyHidden } from "@seekandscore/ui";

import {
  AlertIcon,
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  ChevronRightIcon,
  ClockIcon,
  ExternalIcon,
  LockIcon,
  SearchIcon,
} from "@/components/icons";
import {
  filterCandidates,
  formatMoneyCompact,
  rankMovement,
} from "@/lib/candidates";

const filters: Array<{ id: QueueFilter; label: string }> = [
  { id: "all", label: "All" },
  { id: "new", label: "New" },
  { id: "moved", label: "Moved" },
  { id: "needs_review", label: "Needs review" },
];

const evidenceLabels: Record<EvidenceStatus, string> = {
  verified: "Verified",
  estimated: "Estimated",
  stale: "Stale",
  conflicting: "Conflicting",
  unknown: "Unknown",
};

function formatAsOf(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(new Date(value));
}

function formatObserved(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function ScoreRing({ score }: { score: number }) {
  return (
    <span
      aria-label={`Overall score ${score.toFixed(1)} out of 100`}
      className="score-ring"
      style={{ "--score": `${score * 3.6}deg` } as React.CSSProperties}
    >
      <span>{Math.round(score)}</span>
    </span>
  );
}

function RankMovement({ candidate }: { candidate: CandidateSummary }) {
  const movement = rankMovement(candidate);

  if (movement === null) {
    return <Badge tone="accent">New</Badge>;
  }

  if (movement === 0) {
    return <span className="rank-movement rank-movement--flat">—</span>;
  }

  const improved = movement > 0;
  return (
    <span
      aria-label={`${improved ? "Up" : "Down"} ${Math.abs(movement)} ranks`}
      className={`rank-movement${improved ? " is-positive" : ""}`}
    >
      {improved ? <ArrowUpIcon /> : <ArrowDownIcon />}
      {Math.abs(movement)}
    </span>
  );
}

function QueueTable({
  candidates,
  selectedId,
  onSelect,
}: {
  candidates: CandidateSummary[];
  selectedId: string;
  onSelect: (candidate: CandidateSummary) => void;
}) {
  if (candidates.length === 0) {
    return (
      <div className="empty-state" role="status">
        <span aria-hidden="true" className="empty-state__mark">
          0
        </span>
        <h3>No candidates match this view</h3>
        <p>Clear the search or switch filters. The underlying ranking snapshot is unchanged.</p>
      </div>
    );
  }

  return (
    <div className="queue-table-wrap">
      <table className="queue-table">
        <caption className="ui-visually-hidden">
          Ranked investment candidates. Select a candidate name to inspect its evidence.
        </caption>
        <thead>
          <tr>
            <th scope="col">Rank</th>
            <th scope="col">Candidate</th>
            <th scope="col">Strategy</th>
            <th scope="col">Value range</th>
            <th scope="col">Score</th>
            <th scope="col">Move</th>
            <th scope="col">
              <VisuallyHidden>Actions</VisuallyHidden>
            </th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => {
            const selected = candidate.id === selectedId;
            return (
              <tr className={selected ? "is-selected" : undefined} key={candidate.id}>
                <td className="queue-table__rank">
                  <span>{String(candidate.rank).padStart(2, "0")}</span>
                </td>
                <td>
                  <button
                    aria-current={selected ? "true" : undefined}
                    className="candidate-select"
                    onClick={() => onSelect(candidate)}
                    type="button"
                  >
                    <strong>{candidate.name}</strong>
                    <span>
                      {candidate.locality} · {candidate.acreage.toFixed(1)} ac
                    </span>
                  </button>
                </td>
                <td>
                  <span className="strategy-label">{candidate.strategy}</span>
                </td>
                <td>
                  <span className="value-range">
                    {formatMoneyCompact(candidate.valueRange.low)}–
                    {formatMoneyCompact(candidate.valueRange.high)}
                  </span>
                  <span className="cell-subline">Basis {formatMoneyCompact(candidate.likelyBasis)}</span>
                </td>
                <td>
                  <div className="score-cell">
                    <strong>{candidate.overallScore.toFixed(1)}</strong>
                    <span>{Math.round(candidate.confidence * 100)}% conf.</span>
                  </div>
                </td>
                <td>
                  <RankMovement candidate={candidate} />
                </td>
                <td>
                  <IconButton
                    label={`Inspect ${candidate.name}`}
                    onClick={() => onSelect(candidate)}
                  >
                    <ChevronRightIcon />
                  </IconButton>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function EvidencePanel({ candidate }: { candidate: CandidateSummary }) {
  return (
    <div className="detail-panel__content" id="evidence-content" role="tabpanel">
      <section className="decision-read" aria-labelledby="decision-read-heading">
        <div className="section-heading-row">
          <h3 id="decision-read-heading">Decision read</h3>
          <Badge tone="outline">{candidate.queueState}</Badge>
        </div>
        <p>{candidate.thesis}</p>

        <dl className="decision-stats">
          <div>
            <dt>Value range</dt>
            <dd>
              {formatMoneyCompact(candidate.valueRange.low)}–
              {formatMoneyCompact(candidate.valueRange.high)}
            </dd>
          </div>
          <div>
            <dt>Likely basis</dt>
            <dd>{formatMoneyCompact(candidate.likelyBasis)}</dd>
          </div>
          <div>
            <dt>Confidence</dt>
            <dd>{Math.round(candidate.confidence * 100)}%</dd>
          </div>
        </dl>
      </section>

      {candidate.materialChange ? (
        <section className="material-change" aria-label="Material change">
          <ArrowUpIcon />
          <div>
            <strong>Changed since last review</strong>
            <p>{candidate.materialChange}</p>
          </div>
        </section>
      ) : null}

      <section className="detail-section" aria-labelledby="evidence-heading">
        <div className="section-heading-row">
          <h3 id="evidence-heading">Evidence</h3>
          <span>{candidate.evidence.length} observations</span>
        </div>
        <ul className="evidence-list">
          {candidate.evidence.map((datum) => (
            <li key={datum.id}>
              <span className={`evidence-status evidence-status--${datum.status}`} />
              <div>
                <div className="evidence-list__title">
                  <strong>{datum.label}</strong>
                  <Badge tone={datum.status === "verified" ? "accent" : "outline"}>
                    {evidenceLabels[datum.status]}
                  </Badge>
                </div>
                <p className="evidence-list__value">{datum.value}</p>
                <p className="evidence-list__source">
                  {datum.source} · {formatObserved(datum.observedAt)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="detail-section" aria-labelledby="risks-heading">
        <div className="section-heading-row">
          <h3 id="risks-heading">Three biggest risks</h3>
          <span>Explicit unknowns</span>
        </div>
        <ol className="risk-list">
          {candidate.risks.map((risk, index) => (
            <li key={risk.id}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <div>
                <strong>{risk.label}</strong>
                <p>{risk.detail}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="next-action" aria-labelledby="next-action-heading">
        <span className="next-action__label" id="next-action-heading">
          Proposed next action
        </span>
        <strong>{candidate.nextAction}</strong>
        <span>Research action · human decision required</span>
      </section>
    </div>
  );
}

function OutreachPanel({ candidate }: { candidate: CandidateSummary }) {
  const completed = candidate.outreachGate.reviewedChecks;
  const percentage = Math.round((completed / candidate.outreachGate.totalChecks) * 100);

  return (
    <div className="detail-panel__content" id="outreach-content" role="tabpanel">
      <section className="outreach-lockup" aria-labelledby="outreach-status-heading">
        <span aria-hidden="true" className="outreach-lockup__icon">
          <LockIcon height="24" width="24" />
        </span>
        <div>
          <Badge tone="blocked">Send disabled</Badge>
          <h3 id="outreach-status-heading">Outreach is policy-gated</h3>
          <p>
            No communication can leave the system until identity, source, campaign,
            channel, and exact-message checks all pass.
          </p>
        </div>
      </section>

      <section className="gate-progress" aria-labelledby="gate-progress-heading">
        <div className="section-heading-row">
          <h3 id="gate-progress-heading">Activation gate</h3>
          <span>
            {completed}/{candidate.outreachGate.totalChecks} reviewed
          </span>
        </div>
        <div
          aria-label={`${percentage}% of required checks reviewed`}
          aria-valuemax={100}
          aria-valuemin={0}
          aria-valuenow={percentage}
          className="gate-progress__bar"
          role="progressbar"
        >
          <span style={{ width: `${percentage}%` }} />
        </div>
      </section>

      <section className="detail-section" aria-labelledby="preflight-heading">
        <div className="section-heading-row">
          <h3 id="preflight-heading">Preflight blockers</h3>
          <Badge tone="outline">Fail closed</Badge>
        </div>
        <ul className="gate-list">
          {candidate.outreachGate.blockers.map((blocker) => (
            <li key={blocker}>
              <AlertIcon />
              <span>{blocker}</span>
            </li>
          ))}
          <li className="is-complete">
            <CheckIcon />
            <span>Candidate and narrow business purpose are recorded</span>
          </li>
        </ul>
      </section>

      <section className="policy-summary" aria-labelledby="policy-heading">
        <div>
          <span className="policy-summary__label" id="policy-heading">
            Active safe default
          </span>
          <strong>acquisition-outreach-safe-default-v1</strong>
        </div>
        <dl>
          <div>
            <dt>Cold SMS</dt>
            <dd>Disabled</dd>
          </div>
          <div>
            <dt>Automated calls</dt>
            <dd>Disabled</dd>
          </div>
          <div>
            <dt>Bulk sequences</dt>
            <dd>Disabled</dd>
          </div>
          <div>
            <dt>Human approval</dt>
            <dd>Required</dd>
          </div>
        </dl>
      </section>

      <Button className="outreach-disabled-button" disabled variant="primary">
        <LockIcon />
        Outbound channels disabled
      </Button>
      <p className="outreach-footnote">
        This interface is a product control, not a determination that outreach is lawful.
      </p>
    </div>
  );
}

function CandidateDetail({ candidate }: { candidate: CandidateSummary }) {
  const [activeTab, setActiveTab] = useState<"evidence" | "outreach">("evidence");

  return (
    <Panel as="aside" className="detail-panel" id="evidence-panel">
      <header className="detail-panel__header">
        <div className="detail-panel__title">
          <ScoreRing score={candidate.overallScore} />
          <div>
            <span className="detail-panel__rank">Rank {String(candidate.rank).padStart(2, "0")}</span>
            <h2>{candidate.name}</h2>
            <p>
              {candidate.locality} · {candidate.acreage.toFixed(1)} acres
            </p>
          </div>
        </div>
        <Badge tone="outline">Evidence view</Badge>
      </header>

      <div aria-label="Candidate detail" className="detail-tabs" role="tablist">
        <button
          aria-controls="evidence-content"
          aria-selected={activeTab === "evidence"}
          id="evidence-tab"
          onClick={() => setActiveTab("evidence")}
          role="tab"
          type="button"
        >
          Evidence
          <span>{candidate.evidence.length}</span>
        </button>
        <button
          aria-controls="outreach-content"
          aria-selected={activeTab === "outreach"}
          id="outreach-tab"
          onClick={() => setActiveTab("outreach")}
          role="tab"
          type="button"
        >
          Outreach
          <LockIcon height="14" width="14" />
        </button>
      </div>

      {activeTab === "evidence" ? (
        <EvidencePanel candidate={candidate} />
      ) : (
        <div id="outreach-panel">
          <OutreachPanel candidate={candidate} />
        </div>
      )}
    </Panel>
  );
}

export function OperatorConsole({ snapshot }: { snapshot: TopQueueSnapshot }) {
  const [filter, setFilter] = useState<QueueFilter>("all");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState(snapshot.candidates[0]?.id ?? "");
  const [announcement, setAnnouncement] = useState("");

  const filteredCandidates = useMemo(
    () => filterCandidates(snapshot.candidates, filter, search),
    [filter, search, snapshot.candidates],
  );

  const selectedCandidate =
    snapshot.candidates.find((candidate) => candidate.id === selectedId) ??
    snapshot.candidates[0];

  const changedCount = snapshot.candidates.filter(
    (candidate) => candidate.materialChange || candidate.newSinceLastReview,
  ).length;
  const reviewCount = snapshot.candidates.filter(
    (candidate) => candidate.queueState === "research",
  ).length;
  const averageConfidence = snapshot.candidates.length
    ? Math.round(
        (snapshot.candidates.reduce((total, candidate) => total + candidate.confidence, 0) /
          snapshot.candidates.length) *
          100,
      )
    : 0;

  function reviewChanges() {
    setFilter("new");
    setSearch("");
    const firstNew = snapshot.candidates.find((candidate) => candidate.newSinceLastReview);
    if (firstNew) setSelectedId(firstNew.id);
    setAnnouncement("Showing new candidates since the last review.");
    document.querySelector("#candidate-queue")?.scrollIntoView({ behavior: "smooth" });
  }

  return (
    <main id="main-content">
      <div aria-live="polite" className="ui-visually-hidden">
        {announcement}
      </div>

      <div className="workspace-topbar">
        <div className="breadcrumb" aria-label="Breadcrumb">
          <span>Intelligence</span>
          <ChevronRightIcon />
          <strong>Overview</strong>
        </div>
        <div className="topbar-meta">
          <span className="topbar-asof">
            <ClockIcon />
            As of {formatAsOf(snapshot.asOf)}
          </span>
          <span aria-label="Current user: Operator" className="avatar">
            OP
          </span>
        </div>
      </div>

      <div className="workspace-content">
        <section className="page-heading" id="overview">
          <div>
            <div className="eyebrow-row">
              <span>Investment queue</span>
              {snapshot.isSynthetic ? <Badge tone="outline">Synthetic data</Badge> : null}
            </div>
            <h1>Best opportunities, right now</h1>
            <p>
              A ranked, explainable review of {snapshot.region} candidates. Unknowns stay
              visible; every decision traces back to evidence.
            </p>
          </div>
          <Button onClick={reviewChanges} variant="primary">
            Review new changes
            <ArrowUpIcon />
          </Button>
        </section>

        <section aria-label="Queue summary" className="metric-grid">
          <Panel className="metric-card">
            <span>Active queue</span>
            <strong>{snapshot.candidates.length}</strong>
            <p>Eligible after minimum data gates</p>
          </Panel>
          <Panel className="metric-card">
            <span>Changed</span>
            <strong>{changedCount}</strong>
            <p>New or materially moved records</p>
          </Panel>
          <Panel className="metric-card">
            <span>Needs review</span>
            <strong>{reviewCount}</strong>
            <p>Unknown or conflicting evidence</p>
          </Panel>
          <Panel className="metric-card" id="source-health">
            <span>Average confidence</span>
            <strong>{averageConfidence}%</strong>
            <p>Across this ranking snapshot</p>
          </Panel>
        </section>

        <div className="console-grid">
          <Panel className="queue-panel" id="candidate-queue">
            <header className="queue-panel__header">
              <div>
                <div className="section-heading-row">
                  <h2>{snapshot.label}</h2>
                  <Badge tone="accent">Shadow mode</Badge>
                </div>
                <p>
                  {snapshot.modelVersion} · stable ranking snapshot
                </p>
              </div>
              <div className="queue-search">
                <SearchIcon />
                <label className="ui-visually-hidden" htmlFor="candidate-search">
                  Search candidates
                </label>
                <input
                  id="candidate-search"
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search candidates"
                  type="search"
                  value={search}
                />
                <kbd>/</kbd>
              </div>
            </header>

            <div className="queue-toolbar">
              <div aria-label="Candidate filters" className="filter-tabs" role="group">
                {filters.map((item) => (
                  <button
                    aria-pressed={filter === item.id}
                    key={item.id}
                    onClick={() => setFilter(item.id)}
                    type="button"
                  >
                    {item.id === "all"
                      ? `${item.label} ${snapshot.candidates.length}`
                      : item.label}
                  </button>
                ))}
              </div>
              <span className="queue-result-count" role="status">
                {filteredCandidates.length} shown
              </span>
            </div>

            <QueueTable
              candidates={filteredCandidates}
              onSelect={(candidate) => {
                setSelectedId(candidate.id);
                setAnnouncement(`${candidate.name} selected.`);
              }}
              selectedId={selectedId}
            />
          </Panel>

          {selectedCandidate ? <CandidateDetail candidate={selectedCandidate} /> : null}
        </div>

        <footer className="workspace-footer">
          <p>
            Synthetic product preview. Scores, parties, values, and parcels are fictional and
            are not investment, legal, tax, engineering, or valuation advice.
          </p>
          <a href="/api/health">
            Service health
            <ExternalIcon />
          </a>
        </footer>
      </div>
    </main>
  );
}
