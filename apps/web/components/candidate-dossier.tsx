"use client";

import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
} from "react";

import type {
  ApiCandidateDossier,
  ApiResearchCase,
  ApiVerificationGate,
  ResearchStatus,
  VerificationGateKey,
  VerificationGateStatus,
} from "@seekandscore/contracts";
import { Badge, Button, Spinner } from "@seekandscore/ui";

import { AlertIcon, CheckIcon, LockIcon } from "@/components/icons";
import { formatObserved } from "@/lib/dates";
import {
  getCandidateDossier,
  isAbortError,
  researchErrorMessage,
  type ResearchCasePatchInput,
} from "@/lib/research";

export type DossierLoadState =
  | { status: "loading"; candidateId: string }
  | { status: "ready"; candidateId: string; dossier: ApiCandidateDossier }
  | { status: "error"; candidateId: string; error: unknown };

export type ResearchMutationState =
  | { status: "idle" }
  | { status: "saving"; message: string }
  | { status: "success"; message: string }
  | { status: "error"; message: string };

const researchStatuses: Array<{ value: ResearchStatus; label: string }> = [
  { value: "watching", label: "Watching" },
  { value: "researching", label: "Researching" },
  { value: "passed", label: "Passed" },
  { value: "archived", label: "Archived" },
];

const gateLabels: Record<VerificationGateKey, string> = {
  parcel_identity: "Parcel identity",
  source_freshness: "Source freshness",
  opportunity_zone: "Opportunity Zone",
  underwriting: "Underwriting",
  contact_prep: "Contact preparation",
};

const gateStatusLabels: Record<VerificationGateStatus, string> = {
  satisfied: "Satisfied",
  open: "Open",
  blocked: "Blocked",
  not_available: "Not available",
};

export function researchStatusLabel(status: ResearchStatus): string {
  return researchStatuses.find((item) => item.value === status)?.label ?? status;
}

export function useCandidateDossier(candidateId: string) {
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<DossierLoadState>({
    status: "loading",
    candidateId,
  });

  useEffect(() => {
    const controller = new AbortController();
    void getCandidateDossier(candidateId, controller.signal)
      .then((dossier) => {
        setState({ status: "ready", candidateId, dossier });
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return;
        setState({ status: "error", candidateId, error });
      });
    return () => controller.abort();
  }, [candidateId, revision]);

  const reload = useCallback(() => {
    setState({ status: "loading", candidateId });
    setRevision((current) => current + 1);
  }, [candidateId]);

  const replaceResearchCase = useCallback(
    (researchCase: ApiResearchCase) => {
      setState((current) => {
        if (current.status !== "ready" || current.candidateId !== candidateId) {
          return current;
        }
        return {
          ...current,
          dossier: { ...current.dossier, research_case: researchCase },
        };
      });
    },
    [candidateId],
  );

  if (state.candidateId !== candidateId) {
    return {
      state: { status: "loading", candidateId } as DossierLoadState,
      reload,
      replaceResearchCase,
    };
  }
  return { state, reload, replaceResearchCase };
}

function DossierLoading({ label }: { label: string }) {
  return (
    <div aria-busy="true" className="dossier-state">
      <Spinner label={label} />
      <div>
        <strong>{label}</strong>
        <p>Reading the authenticated, server-derived dossier.</p>
      </div>
    </div>
  );
}

function DossierError({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry: () => void;
}) {
  return (
    <div className="dossier-state dossier-state--error" role="alert">
      <AlertIcon aria-hidden="true" />
      <div>
        <strong>Saved research is unavailable</strong>
        <p>{researchErrorMessage(error)}</p>
        <Button onClick={onRetry} size="small" variant="secondary">
          Retry dossier
        </Button>
      </div>
    </div>
  );
}

function MutationFeedback({ state }: { state: ResearchMutationState }) {
  if (state.status === "idle") return null;
  return (
    <div
      aria-live="polite"
      className={`research-feedback research-feedback--${state.status}`}
      role={state.status === "error" ? "alert" : undefined}
    >
      {state.status === "saving" ? <Spinner label="Saving research" /> : null}
      {state.status === "success" ? <CheckIcon aria-hidden="true" /> : null}
      {state.status === "error" ? <AlertIcon aria-hidden="true" /> : null}
      <span>{state.message}</span>
    </div>
  );
}

function ResearchCaseEditor({
  researchCase,
  mutation,
  onSave,
  timeZone,
}: {
  researchCase: ApiResearchCase;
  mutation: ResearchMutationState;
  onSave: (input: ResearchCasePatchInput) => void;
  timeZone: string;
}) {
  const [status, setStatus] = useState<ResearchStatus>(researchCase.status);
  const [operatorNote, setOperatorNote] = useState(researchCase.operator_note ?? "");
  const [nextAction, setNextAction] = useState(researchCase.next_action ?? "");

  const dirty =
    status !== researchCase.status ||
    operatorNote !== (researchCase.operator_note ?? "") ||
    nextAction !== (researchCase.next_action ?? "");
  const saving = mutation.status === "saving";

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!dirty || saving) return;
    onSave({
      status,
      operator_note: operatorNote,
      next_action: nextAction,
    });
  }

  return (
    <form className="research-editor" onSubmit={submit}>
      <MutationFeedback state={mutation} />

      <fieldset className="research-status" disabled={saving}>
        <legend>Research status</legend>
        <div>
          {researchStatuses.map((item) => (
            <label key={item.value}>
              <input
                checked={status === item.value}
                name={`research-status-${researchCase.id}`}
                onChange={() => setStatus(item.value)}
                type="radio"
                value={item.value}
              />
              <span>{item.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="research-field">
        <div className="research-field__label">
          <label htmlFor={`operator-note-${researchCase.id}`}>Operator note</label>
          <span>{operatorNote.length}/4000</span>
        </div>
        <textarea
          disabled={saving}
          id={`operator-note-${researchCase.id}`}
          maxLength={4000}
          onChange={(event) => setOperatorNote(event.target.value)}
          placeholder="Record evidence-backed reasoning, unknowns, and what changed."
          rows={5}
          value={operatorNote}
        />
      </div>

      <div className="research-field">
        <div className="research-field__label">
          <label htmlFor={`next-action-${researchCase.id}`}>Next action</label>
          <span>{nextAction.length}/500</span>
        </div>
        <textarea
          disabled={saving}
          id={`next-action-${researchCase.id}`}
          maxLength={500}
          onChange={(event) => setNextAction(event.target.value)}
          placeholder="Name one bounded, human-reviewed research action."
          rows={3}
          value={nextAction}
        />
      </div>

      <dl className="research-version">
        <div>
          <dt>Case version</dt>
          <dd>v{researchCase.version}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{formatObserved(researchCase.updated_at, timeZone)}</dd>
        </div>
        <div>
          <dt>Candidate snapshot</dt>
          <dd>{researchCase.candidate_read_model_version}</dd>
        </div>
      </dl>

      <div className="research-editor__actions">
        <p>Updates use version-matched writes and fail on concurrent changes.</p>
        <Button disabled={!dirty || saving} size="small" type="submit" variant="primary">
          {saving ? "Saving…" : "Save research changes"}
        </Button>
      </div>
    </form>
  );
}

export function ResearchPanel({
  state,
  mutation,
  onCreate,
  onRetry,
  onSave,
  timeZone,
}: {
  state: DossierLoadState;
  mutation: ResearchMutationState;
  onCreate: () => void;
  onRetry: () => void;
  onSave: (input: ResearchCasePatchInput) => void;
  timeZone: string;
}) {
  if (state.status === "loading") {
    return <DossierLoading label="Loading saved research" />;
  }
  if (state.status === "error") {
    return <DossierError error={state.error} onRetry={onRetry} />;
  }
  if (!state.dossier.research_case) {
    return (
      <div className="research-empty">
        <MutationFeedback state={mutation} />
        <span aria-hidden="true" className="research-empty__mark">
          +
        </span>
        <h3>This parcel is not saved</h3>
        <p>
          Create one organization-scoped research case. Saving does not verify any gate or
          enable contact preparation.
        </p>
        <Button
          disabled={mutation.status === "saving"}
          onClick={onCreate}
          size="small"
          variant="primary"
        >
          {mutation.status === "saving" ? "Saving…" : "Save to research"}
        </Button>
      </div>
    );
  }
  return (
    <ResearchCaseEditor
      key={`${state.dossier.research_case.id}:${state.dossier.research_case.version}`}
      mutation={mutation}
      onSave={onSave}
      researchCase={state.dossier.research_case}
      timeZone={timeZone}
    />
  );
}

function GateRow({ gate }: { gate: ApiVerificationGate }) {
  const tone = gate.status === "satisfied"
    ? "accent"
    : gate.status === "blocked"
      ? "blocked"
      : "outline";
  return (
    <li>
      <div className="contact-gate__heading">
        <strong>{gateLabels[gate.key]}</strong>
        <Badge tone={tone}>{gateStatusLabels[gate.status]}</Badge>
      </div>
      <p>{gate.detail}</p>
      <div className="contact-gate__meta">
        <code>{gate.reason_code}</code>
        <span>
          {gate.evidence_ids.length} linked evidence item
          {gate.evidence_ids.length === 1 ? "" : "s"}
        </span>
      </div>
    </li>
  );
}

export function ContactPrepPanel({
  state,
  onRetry,
}: {
  state: DossierLoadState;
  onRetry: () => void;
}) {
  if (state.status === "loading") {
    return <DossierLoading label="Loading contact controls" />;
  }
  if (state.status === "error") {
    return <DossierError error={state.error} onRetry={onRetry} />;
  }
  const { controls, gates } = state.dossier;
  return (
    <div className="contact-prep">
      <section className="contact-prep__lockup" aria-labelledby="contact-prep-heading">
        <span aria-hidden="true" className="contact-prep__icon">
          <LockIcon height="24" width="24" />
        </span>
        <div>
          <Badge tone="blocked">
            {controls.outbound_enabled ? "Outbound controlled" : "Outbound disabled"}
          </Badge>
          <h3 id="contact-prep-heading">Server-derived contact readiness</h3>
          <p>
            This panel only reports authenticated dossier gates and runtime controls. It
            cannot initiate communication.
          </p>
        </div>
      </section>

      <section className="detail-section" aria-labelledby="contact-controls-heading">
        <div className="section-heading-row">
          <h3 id="contact-controls-heading">Runtime controls</h3>
          <span>Read only</span>
        </div>
        <dl className="contact-controls">
          <div>
            <dt>Contact preparation</dt>
            <dd>{controls.contact_prep_enabled ? "Enabled upstream" : "Disabled"}</dd>
          </div>
          <div>
            <dt>Outbound communication</dt>
            <dd>{controls.outbound_enabled ? "Enabled upstream" : "Disabled"}</dd>
          </div>
        </dl>
      </section>

      <section className="detail-section" aria-labelledby="verification-gates-heading">
        <div className="section-heading-row">
          <h3 id="verification-gates-heading">Verification gates</h3>
          <span>{gates.length} from dossier</span>
        </div>
        {gates.length ? (
          <ul className="contact-gates">
            {gates.map((gate) => (
              <GateRow gate={gate} key={gate.key} />
            ))}
          </ul>
        ) : (
          <p className="contact-gates__empty">
            The research service returned no verification gates. No readiness is inferred.
          </p>
        )}
      </section>

      <p className="contact-prep__footnote">
        Controls remain server-authoritative. Saved notes and status changes cannot satisfy
        gates or activate outbound channels.
      </p>
    </div>
  );
}
