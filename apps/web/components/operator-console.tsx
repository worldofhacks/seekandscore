"use client";

import { useMemo, useState, type KeyboardEvent } from "react";

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
  ContactPrepPanel,
  ResearchPanel,
  researchStatusLabel,
  useCandidateDossier,
  type ResearchMutationState,
} from "@/components/candidate-dossier";
import {
  AlertIcon,
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  ChevronRightIcon,
  ClockIcon,
  ExternalIcon,
  LockIcon,
} from "@/components/icons";
import {
  CandidateFilters,
  CandidatePagination,
} from "@/components/candidate-filters";
import {
  filterCandidates,
  formatMoneyCompact,
  rankMovement,
} from "@/lib/queue";
import { formatAsOf, formatObserved } from "@/lib/dates";
import { candidateScoreLabel, candidateValueDisplay } from "@/lib/presentation";
import {
  ResearchRequestError,
  createResearchCase,
  researchErrorMessage,
  updateResearchCase,
  type ResearchCasePatchInput,
} from "@/lib/research";

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

      {snapshot.cohort.cohortTotal > 0 ? (
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
            "Switch the page view filters. The server-loaded cohort page is unchanged."}
        </p>
      </div>
    );
  }

  return (
    <div className="queue-table-wrap">
      <table className="queue-table">
        <caption className="ui-visually-hidden">
          One server-loaded page from the approved live cohort. Select a candidate name to
          inspect its evidence.
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
    <div
      aria-labelledby="evidence-tab"
      className="detail-panel__content"
      id="evidence-content"
      role="tabpanel"
    >
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

function CandidateDetail({
  candidate,
  timeZone,
}: {
  candidate: CandidateSummary;
  timeZone: string;
}) {
  const [activeTab, setActiveTab] = useState<"evidence" | "research" | "contact">(
    "evidence",
  );
  const [mutation, setMutation] = useState<ResearchMutationState>({ status: "idle" });
  const dossier = useCandidateDossier(candidate.id);
  const researchCase =
    dossier.state.status === "ready" ? dossier.state.dossier.research_case : null;

  async function saveCandidate() {
    setActiveTab("research");
    setMutation({ status: "saving", message: "Saving this parcel to research…" });
    try {
      const saved = await createResearchCase(candidate.id);
      dossier.replaceResearchCase(saved);
      setMutation({
        status: "success",
        message: `Saved to research as ${researchStatusLabel(saved.status)}.`,
      });
    } catch (error: unknown) {
      setMutation({ status: "error", message: researchErrorMessage(error) });
    }
  }

  async function saveResearchChanges(input: ResearchCasePatchInput) {
    if (!researchCase) return;
    setMutation({ status: "saving", message: "Saving version-matched research changes…" });
    try {
      const updated = await updateResearchCase(researchCase, input);
      dossier.replaceResearchCase(updated);
      setMutation({
        status: "success",
        message: `Research case saved as version ${updated.version}.`,
      });
    } catch (error: unknown) {
      setMutation({ status: "error", message: researchErrorMessage(error) });
      if (error instanceof ResearchRequestError && error.code === "stale") {
        dossier.reload();
      }
    }
  }

  function openDossierTab(tab: "research" | "contact") {
    setActiveTab(tab);
    if (dossier.state.status === "error") dossier.reload();
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const tabOrder = ["evidence", "research", "contact"] as const;
    const currentIndex = tabOrder.indexOf(activeTab);
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabOrder.length;
    if (event.key === "ArrowLeft") {
      nextIndex = (currentIndex - 1 + tabOrder.length) % tabOrder.length;
    }
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = tabOrder.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    const nextTab = tabOrder[nextIndex];
    if (nextTab === "evidence") setActiveTab("evidence");
    else openDossierTab(nextTab);
    document.getElementById(`${nextTab}-tab`)?.focus();
  }

  const researchActionLabel =
    dossier.state.status === "loading"
      ? "Loading saved research"
      : dossier.state.status === "error"
        ? "Research unavailable"
        : researchCase
          ? `Saved · ${researchStatusLabel(researchCase.status)}`
          : mutation.status === "saving"
            ? "Saving…"
            : "Save to research";

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
        <div className="detail-panel__header-actions">
          <Badge tone="outline">{candidate.screeningOnly ? "Research only" : "Evidence view"}</Badge>
          <Button
            disabled={
              dossier.state.status !== "ready" || mutation.status === "saving"
            }
            onClick={researchCase ? () => openDossierTab("research") : saveCandidate}
            size="small"
            variant={researchCase ? "secondary" : "primary"}
          >
            {researchActionLabel}
          </Button>
        </div>
      </header>

      <div aria-label="Candidate detail" className="detail-tabs" role="tablist">
        <button
          aria-controls="evidence-content"
          aria-selected={activeTab === "evidence"}
          id="evidence-tab"
          onClick={() => setActiveTab("evidence")}
          onKeyDown={handleTabKeyDown}
          role="tab"
          tabIndex={activeTab === "evidence" ? 0 : -1}
          type="button"
        >
          Evidence
          <span>{candidate.evidence.length}</span>
        </button>
        <button
          aria-controls="research-content"
          aria-selected={activeTab === "research"}
          id="research-tab"
          onClick={() => openDossierTab("research")}
          onKeyDown={handleTabKeyDown}
          role="tab"
          tabIndex={activeTab === "research" ? 0 : -1}
          type="button"
        >
          Research
          <span>{researchCase ? researchStatusLabel(researchCase.status) : "Not saved"}</span>
        </button>
        <button
          aria-controls="contact-content"
          aria-selected={activeTab === "contact"}
          id="contact-tab"
          onClick={() => openDossierTab("contact")}
          onKeyDown={handleTabKeyDown}
          role="tab"
          tabIndex={activeTab === "contact" ? 0 : -1}
          type="button"
        >
          Contact prep
          <LockIcon height="14" width="14" />
        </button>
      </div>

      {activeTab === "evidence" ? (
        <EvidencePanel candidate={candidate} timeZone={timeZone} />
      ) : activeTab === "research" ? (
        <div
          aria-labelledby="research-tab"
          className="dossier-panel-content"
          id="research-content"
          role="tabpanel"
        >
          <ResearchPanel
            mutation={mutation}
            onCreate={saveCandidate}
            onRetry={dossier.reload}
            onSave={saveResearchChanges}
            state={dossier.state}
            timeZone={timeZone}
          />
        </div>
      ) : (
        <div
          aria-labelledby="contact-tab"
          className="dossier-panel-content"
          id="contact-content"
          role="tabpanel"
        >
          <ContactPrepPanel onRetry={dossier.reload} state={dossier.state} />
        </div>
      )}
    </Panel>
  );
}

export function OperatorConsole({ snapshot }: { snapshot: TopQueueSnapshot }) {
  const [filter, setFilter] = useState<QueueFilter>("all");
  const [selectedId, setSelectedId] = useState(snapshot.candidates[0]?.id ?? "");
  const [announcement, setAnnouncement] = useState("");

  const filteredCandidates = useMemo(
    () => filterCandidates(snapshot.candidates, filter, ""),
    [filter, snapshot.candidates],
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
  const hasCandidates = snapshot.candidates.length > 0;
  const rightsDisabled = snapshot.provenance.status === "rights_disabled";
  const hasLiveCohort =
    (snapshot.provenance.status === "current" ||
      snapshot.provenance.status === "stale" ||
      snapshot.provenance.status === "partial") &&
    snapshot.cohort.cohortTotal > 0;
  const emptyTitle = hasLiveCohort
    ? "No parcels match these cohort filters"
    : rightsDisabled
      ? "Live records are not approved for display"
      : "No verified live candidates";
  const emptyDetail = hasLiveCohort
    ? "Adjust or clear the server filters to search the approved live cohort."
    : rightsDisabled
      ? "A private source run may exist, but parcel observations stay excluded until display rights are approved."
      : "The console remains empty until the API returns a verified live-only candidate dataset.";

  function reviewChanges() {
    setFilter("new");
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
                {!hasLiveCohort
                  ? rightsDisabled
                    ? "Display control"
                    : "Live dataset status"
                  : "Parcel screening"}
              </span>
              <Badge
                tone={
                  snapshot.provenance.mode === "live" && hasLiveCohort
                    ? "accent"
                    : "outline"
                }
              >
                {datasetModeLabel(snapshot)}
              </Badge>
            </div>
            <h1>
              {!hasLiveCohort
                ? rightsDisabled
                  ? "Live source records are withheld from this console"
                  : "No verified live candidates"
                : "Source-backed parcels for research"}
            </h1>
            <p>
              {!hasLiveCohort
                ? rightsDisabled
                  ? "Live acquisition may run privately for rights review, but no parcel observations, values, or parties are published here."
                  : "No candidate or outreach action is available. Unverified records are never shown."
                : `A research-only screen of ${snapshot.cohort.cohortTotal.toLocaleString("en-US")} approved live ${snapshot.region} parcel observations. Source values and unknowns remain explicit.`}
            </p>
          </div>
          <Button disabled={!hasCandidates} onClick={reviewChanges} variant="primary">
            Review new changes
            <ArrowUpIcon />
          </Button>
        </section>

        <DataProvenancePanel snapshot={snapshot} />

        {hasLiveCohort ? (
          <section aria-label="Live queue summary" className="metric-grid">
            <Panel className="metric-card">
              <span>Approved live cohort</span>
              <strong>{snapshot.cohort.cohortTotal.toLocaleString("en-US")}</strong>
              <p>Source records available for bounded research</p>
            </Panel>
            <Panel className="metric-card">
              <span>Changed</span>
              <strong>{changedCount}</strong>
              <p>New or materially moved on this page</p>
            </Panel>
            <Panel className="metric-card">
              <span>Needs review</span>
              <strong>{reviewCount}</strong>
              <p>Research-state records on this page</p>
            </Panel>
            <Panel className="metric-card">
              <span>Average confidence</span>
              <strong>{averageConfidence}%</strong>
              <p>Across this server-loaded page</p>
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
                    {hasLiveCohort
                      ? "Research only"
                      : rightsDisabled
                        ? "Display disabled"
                        : "Awaiting live data"}
                  </Badge>
                </div>
                <p>
                  {snapshot.modelVersion} · {hasLiveCohort ? "approved live cohort" : "no publishable records"}
                </p>
              </div>
            </header>

            <CandidateFilters
              enabled={hasLiveCohort}
              filters={snapshot.cohort.appliedFilters}
              key={JSON.stringify(snapshot.cohort.appliedFilters)}
            />

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
                {filteredCandidates.length.toLocaleString("en-US")} shown of filtered{" "}
                {snapshot.cohort.filteredTotal.toLocaleString("en-US")} / cohort{" "}
                {snapshot.cohort.cohortTotal.toLocaleString("en-US")}
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

            {hasLiveCohort ? (
              <CandidatePagination
                filters={snapshot.cohort.appliedFilters}
                nextCursor={snapshot.cohort.nextCursor}
              />
            ) : null}
          </Panel>

          {selectedCandidate ? (
            <CandidateDetail
              candidate={selectedCandidate}
              key={selectedCandidate.id}
              timeZone={snapshot.timeZone}
            />
          ) : null}
        </div>

        <footer className="workspace-footer">
          <p>
            {hasLiveCohort
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
