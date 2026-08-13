import type { CandidateSummary } from "@seekandscore/contracts";

import { formatMoneyCompact } from "./queue";

export interface CandidateValueDisplay {
  label: string;
  value: string;
  subline: string;
  observed: boolean;
}

function formatCents(value: number): string {
  return formatMoneyCompact(value / 100);
}

export function candidateValueDisplay(candidate: CandidateSummary): CandidateValueDisplay {
  const fields = candidate.sourceObservation?.fields;

  if (fields?.appraisedValueCents !== undefined) {
    return {
      label: "Appraised value observation",
      value: formatCents(fields.appraisedValueCents),
      subline: "Assessor observation · not an offer",
      observed: true,
    };
  }

  if (fields?.assessedValueCents !== undefined) {
    return {
      label: "Assessed value observation",
      value: formatCents(fields.assessedValueCents),
      subline: "Assessor observation · not an offer",
      observed: true,
    };
  }

  if (fields?.marketValueCents !== undefined) {
    return {
      label: "Market value observation",
      value: formatCents(fields.marketValueCents),
      subline: "Assessor observation · not an offer",
      observed: true,
    };
  }

  if (fields?.landValueCents !== undefined) {
    return {
      label: "Land value observation",
      value: formatCents(fields.landValueCents),
      subline: "Assessor observation · not an offer",
      observed: true,
    };
  }

  return {
    label: "Source value observation",
    value: "Not supplied",
    subline: "No verified source value",
    observed: false,
  };
}

export function candidateScoreLabel(candidate: CandidateSummary): string {
  return candidate.screeningOnly ? "Screening score" : "Opportunity score";
}
