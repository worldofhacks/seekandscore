"use client";

import { useMemo, useState } from "react";

import type {
  CandidateSummary,
  DataSourceProvenance,
  DatasetHealthStatus,
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
} from "@/lib/queue";
import { formatAsOf, formatObserved } from "@/lib/dates";
import { candidateScoreLabel, candidateValueDisplay } from "@/lib/presentation";

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

const datasetStatusLabels: Record<DatasetHealthStatus, string> = {
  current: "Current",
  stale: "Stale",
  partial: "Partial",
  error: "Error",
  rights_disabled: "Display disabled",
  unavailable: "Unavailable",
  unknown: "Unknown",
};

function datasetModeLabel(snapshot: TopQueueSnapshot): string {
  if (snapshot.provenance.mode === "live") return "Live data";
  return "No live dataset";
}

function statusTone(status: DatasetHealthStatus): "accent" | "outline" | "blocked" {
  if (status === "current") return "accent";
  if (
    status === "error" ||
    status === "rights_disabled" ||
    status === "unavailable"
  ) {
    return "blocked";
  }
  return "outline";
}

function SourceRow({ source, timeZone }: { source: DataSourceProvenance; timeZone: string }) {
  return (
    <li>
      <div>
        <strong>{source.name}</strong>
        <span>{source.id}</span>
      </div>
      <div className="source-provenance__status">
        <Badge tone={source.status === "current" ? "accent" : "outline"}>
          {source.status}
        </Badge>
        <span>
          {source.retrievedAt ? (
            <>
              Retrieved{" "}
              <time dateTime={source.retrievedAt}>
                {formatAsOf(source.retrievedAt, timeZone)}
              </time>
            </>
          ) : (
            "Retrieval time not supplied"
          )}
        </span>
      </div>
      <dl>
        <div>
          <dt>Published</dt>
          <dd>
            {source.publishedAt ? (
              <time dateTime={source.publishedAt}>{formatAsOf(source.publishedAt, timeZone)}</time>
            ) : (
              "Not supplied"
            )}
          </dd>
        </div>
        <div>
          <dt>Records</dt>
          <dd>{source.recordCount?.toLocaleString("en-US") ?? "Not supplied"}</dd>
        </div>
      </dl>
      {source.detail ? <p>{source.detail}</p> : null}
    </li>
  );
}

function DataProvenancePanel({ snapshot }: { snapshot: TopQueueSnapshot }) {
  const { provenance } = snapshot;
  const primarySource = provenance.sources[0];
  const needsAttention = provenance.status !== "current";
  const additionalWarnings = provenance.warnings.filter(
    (warning) => warning !== provenance.statusDetail,
  );
  const heading = provenance.status === "rights_disabled"
    ? "Live source display is disabled"
    : provenance.status === "error"
      ? "Live candidate data could not be loaded"
      : provenance.status === "unavailable"
        ? "No verified live candidate data"
      : provenance.status === "partial"
        ? "The live dataset is only partially available"
        : provenance.status === "stale"
          ? "The live dataset is outside its freshness target"
          : provenance.status === "current"
            ? "Live source-backed parcel data"
            : "Live dataset status is unknown";

  return (
    <section
      aria-labelledby="data-provenance-heading"
      className={`data-provenance data-provenance--${provenance.status}`}
      id="source-health"
    >
      <div className="data-provenance__summary">
        <span aria-hidden="true" className="data-provenance__icon">
          {needsAttention ? <AlertIcon /> : <CheckIcon />}
        </span>
        <div>
          <div className="data-provenance__badges">
            <Badge
              tone={provenance.mode === "live" ? "accent" : "outline"}
            >
              {datasetModeLabel(snapshot)}
            </Badge>
            <Badge tone={statusTone(provenance.status)}>
              {datasetStatusLabels[provenance.status]}
            </Badge>
          </div>
          <h2 id="data-provenance-heading">{heading}</h2>
          <p>
            {provenance.statusDetail ??
              provenance.warnings[0] ??
              "Review source dates and evidence before acting on any live screening result."}
          </p>
        </div>
      </div>

      <dl className="data-provenance__facts">
        <div>
          <dt>Primary source</dt>
          <dd>{primarySource?.name ?? "Source metadata not supplied"}</dd>
        </div>
        <div>
          <dt>Retrieved</dt>
          <dd>
            {provenance.retrievedAt ? (
              <time dateTime={provenance.retrievedAt}>
                {formatAsOf(provenance.retrievedAt, snapshot.timeZone)}
              </time>
            ) : (
              "Not supplied"
            )}
          </dd>
        </div>
        <div>
          <dt>Published</dt>
          <dd>
            {provenance.publishedAt ? (
              <time dateTime={provenance.publishedAt}>
                {formatAsOf(provenance.publishedAt, snapshot.timeZone)}
              </time>
            ) : (
              "Not supplied"
            )}
          </dd>
        </div>
        <div>
          <dt>Fresh through</dt>
          <dd>
            {provenance.staleAfter ? (
              <time dateTime={provenance.staleAfter}>
                {formatAsOf(provenance.staleAfter, snapshot.timeZone)}
              </time>
            ) : (
              "No threshold supplied"
            )}
          </dd>
        </div>
      </dl>

      {provenance.sources.length ? (
        <details className="source-provenance">
          <summary>
            Source provenance
            <span>{provenance.sources.length}</span>
          </summary>
          <ul>
            {provenance.sources.map((source) => (
              <SourceRow key={source.id} source={source} timeZone={snapshot.timeZone} />
            ))}
          </ul>
        </details>
      ) : null}

      {additionalWarnings.length ? (
        <ul aria-label="Dataset warnings" className="data-provenance__warnings">
          {additionalWarnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}

      {snapshot.candidates.some((candidate) => candidate.screeningOnly) ? (
        <p className="data-provenance__screening-note">
          <strong>Research-only screen.</strong> Assessed or appraised values are source
          observations—not offers, acquisition basis, or independent valuations. Screening
          scores do not verify buildability, Opportunity Zone status, ownership, or contact
          authority.
        </p>
      ) : null}
    </section>
  );
}

function ScoreRing({ score, label = "Overall score" }: { score: number; label?: string }) {
  return (
    <span
      aria-label={`${label} ${score.toFixed(1)} out of 100`}
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
  emptyDetail,
  emptyTitle,
  selectedId,
  onSelect,
}: {
  candidates: CandidateSummary[];
  emptyDetail?: string;
  emptyTitle?: string;
  selectedId: string;
  onSelect: (candidate: CandidateSummary) => void;
}) {
  if (candidates.length === 0) {
    return (
      <div className="empty-state" role="status">
        <span aria-hidden="true" className="empty-state__mark">
          0
        </span>
        <h3>{emptyTitle ?? "No candidates match this view"}</h3>
        <p>
          {emptyDetail ??
            "Clear the search or switch filters. The underlying live ranking snapshot is unchanged."}
        </p>
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
            <th scope="col">Value evidence</th>
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
            const valueDisplay = candidateValueDisplay(candidate);
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
                    {valueDisplay.value}
                  </span>
                  <span className="cell-subline">{valueDisplay.subline}</span>
                </td>
                <td>
                  <div className="score-cell">
                    <strong>{candidate.overallScore.toFixed(1)}</strong>
                    <span>
                      {candidate.screeningOnly ? "screen" : `${Math.round(candidate.confidence * 100)}% conf.`}
                    </span>
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

function EvidencePanel({
  candidate,
  timeZone,
}: {
  candidate: CandidateSummary;
  timeZone: string;
}) {
  const valueDisplay = candidateValueDisplay(candidate);
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
            <dt>{valueDisplay.label}</dt>
            <dd>{valueDisplay.value}</dd>
          </div>
          <div>
            <dt>{candidate.screeningOnly ? "Use" : "Scenario basis"}</dt>
            <dd>
              {candidate.screeningOnly
                ? "Research only"
                : formatMoneyCompact(candidate.likelyBasis)}
            </dd>
          </div>
          <div>
            <dt>{candidateScoreLabel(candidate)}</dt>
            <dd>{candidate.overallScore.toFixed(1)}</dd>
          </div>
        </dl>
        {valueDisplay.observed ? (
          <p className="source-observation-disclaimer">
            {valueDisplay.subline}. Confirm the source record and effective tax year before use.
          </p>
        ) : null}
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
                  {datum.source} · {formatObserved(datum.observedAt, timeZone)}
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

function CandidateDetail({
  candidate,
  timeZone,
}: {
  candidate: CandidateSummary;
  timeZone: string;
}) {
  const [activeTab, setActiveTab] = useState<"evidence" | "outreach">("evidence");

  return (
    <Panel as="aside" className="detail-panel" id="evidence-panel">
      <header className="detail-panel__header">
        <div className="detail-panel__title">
          <ScoreRing label={candidateScoreLabel(candidate)} score={candidate.overallScore} />
          <div>
            <span className="detail-panel__rank">Rank {String(candidate.rank).padStart(2, "0")}</span>
            <h2>{candidate.name}</h2>
            <p>
              {candidate.locality} · {candidate.acreage.toFixed(1)} acres
            </p>
          </div>
        </div>
        <Badge tone="outline">{candidate.screeningOnly ? "Research only" : "Evidence view"}</Badge>
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
        <EvidencePanel candidate={candidate} timeZone={timeZone} />
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
  const hasScreeningCandidates = snapshot.candidates.some(
    (candidate) => candidate.screeningOnly,
  );
  const hasCandidates = snapshot.candidates.length > 0;
  const rightsDisabled = snapshot.provenance.status === "rights_disabled";
  const emptyTitle = rightsDisabled
    ? "Live records are not approved for display"
    : "No verified live candidates";
  const emptyDetail = rightsDisabled
    ? "A private source run may exist, but parcel observations stay excluded until display rights are approved."
    : "The console remains empty until the API returns a verified live-only candidate dataset.";

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
            {snapshot.asOf ? (
              <>
                Snapshot{" "}
                <time dateTime={snapshot.asOf}>
                  {formatAsOf(snapshot.asOf, snapshot.timeZone)}
                </time>
              </>
            ) : (
              "Snapshot time unavailable"
            )}
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
              <span>
                {!hasCandidates
                  ? rightsDisabled
                    ? "Display control"
                    : "Live dataset status"
                  : hasScreeningCandidates
                    ? "Parcel screening"
                    : "Investment queue"}
              </span>
              <Badge
                tone={
                  snapshot.provenance.mode === "live" && hasCandidates
                    ? "accent"
                    : "outline"
                }
              >
                {datasetModeLabel(snapshot)}
              </Badge>
            </div>
            <h1>
              {!hasCandidates
                ? rightsDisabled
                  ? "Live source records are withheld from this console"
                  : "No verified live candidates"
                : hasScreeningCandidates
                  ? "Source-backed parcels for research"
                  : "Verified live opportunities"}
            </h1>
            <p>
              {!hasCandidates
                ? rightsDisabled
                  ? "Live acquisition may run privately for rights review, but no parcel observations, values, or parties are published here."
                  : "No candidate or outreach action is available. Unverified records are never shown."
                : hasScreeningCandidates
                  ? `A research-only screen of ${snapshot.region} parcel observations. Source values and unknowns remain explicit.`
                  : `A ranked, explainable review of verified ${snapshot.region} records. Unknowns stay visible; every decision traces back to evidence.`}
            </p>
          </div>
          <Button disabled={!hasCandidates} onClick={reviewChanges} variant="primary">
            Review new changes
            <ArrowUpIcon />
          </Button>
        </section>

        <DataProvenancePanel snapshot={snapshot} />

        {hasCandidates ? (
          <section aria-label="Live queue summary" className="metric-grid">
            <Panel className="metric-card">
              <span>Verified live queue</span>
              <strong>{snapshot.candidates.length}</strong>
              <p>
                {hasScreeningCandidates
                  ? "Source records available for research"
                  : "Eligible after minimum data gates"}
              </p>
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
            <Panel className="metric-card">
              <span>Average confidence</span>
              <strong>{averageConfidence}%</strong>
              <p>Across this live ranking snapshot</p>
            </Panel>
          </section>
        ) : (
          <section aria-label="Live data controls" className="metric-grid">
            <Panel className="metric-card">
              <span>Published candidates</span>
              <strong>0</strong>
              <p>Only verified live records can enter the console</p>
            </Panel>
            <Panel className="metric-card">
              <span>Source mode</span>
              <strong className="metric-card__status">
                {snapshot.provenance.mode === "live" ? "Live" : "Unknown"}
              </strong>
              <p>Reported by the candidate API</p>
            </Panel>
            <Panel className="metric-card">
              <span>Display rights</span>
              <strong className="metric-card__status">
                {rightsDisabled ? "Disabled" : "Not verified"}
              </strong>
              <p>Public parcel display fails closed</p>
            </Panel>
            <Panel className="metric-card">
              <span>Outbound outreach</span>
              <strong className="metric-card__status">Disabled</strong>
              <p>No candidate data can activate communication</p>
            </Panel>
          </section>
        )}

        <div className={`console-grid${selectedCandidate ? "" : " console-grid--empty"}`}>
          <Panel className="queue-panel" id="candidate-queue">
            <header className="queue-panel__header">
              <div>
                <div className="section-heading-row">
                  <h2>{snapshot.label}</h2>
                  <Badge tone="accent">
                    {hasScreeningCandidates
                      ? "Research only"
                      : rightsDisabled
                        ? "Display disabled"
                        : "Awaiting live data"}
                  </Badge>
                </div>
                <p>
                  {snapshot.modelVersion} · {hasCandidates ? "stable live snapshot" : "no publishable records"}
                </p>
              </div>
              <div className="queue-search">
                <SearchIcon />
                <label className="ui-visually-hidden" htmlFor="candidate-search">
                  Search candidates
                </label>
                <input
                  disabled={!hasCandidates}
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
                    disabled={!hasCandidates}
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
              emptyDetail={hasCandidates ? undefined : emptyDetail}
              emptyTitle={hasCandidates ? undefined : emptyTitle}
              onSelect={(candidate) => {
                setSelectedId(candidate.id);
                setAnnouncement(`${candidate.name} selected.`);
              }}
              selectedId={selectedId}
            />
          </Panel>

          {selectedCandidate ? (
            <CandidateDetail candidate={selectedCandidate} timeZone={snapshot.timeZone} />
          ) : null}
        </div>

        <footer className="workspace-footer">
          <p>
            {hasCandidates
              ? "Source-backed parcel screening. Assessor observations and screening scores are not offers, acquisition basis, or independent valuations. "
              : "No property candidate records are currently displayed, and no unverified records are used. "}
            Data availability never activates owner outreach. Nothing shown is investment, legal,
            tax, engineering, or valuation advice.
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
