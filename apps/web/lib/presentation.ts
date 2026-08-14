import type {
  CandidateSummary,
  OpportunityZoneEvidence,
} from "@seekandscore/contracts";

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

export interface OpportunityZoneDisplay {
  label: string;
  shortLabel: string;
  detail: string;
  subline: string;
  tone: "accent" | "outline" | "blocked";
}

export function opportunityZoneDisplay(
  evidence: OpportunityZoneEvidence,
): OpportunityZoneDisplay {
  const vintage = evidence.designation?.censusVintage;
  const tract = evidence.designation?.tractGeoid;
  if (evidence.classification === "inside") {
    return {
      label: "Inside a 2018 designated tract",
      shortLabel: "Inside tract",
      detail:
        "The versioned parcel geometry is strictly inside one designated tract in this evidence snapshot.",
      subline: tract
        ? `${vintage ?? 2010} Census tract ${tract}`
        : `${vintage ?? 2010} Census tract geometry`,
      tone: "accent",
    };
  }
  if (evidence.classification === "outside") {
    return {
      label: "Outside 2018 designated tracts",
      shortLabel: "Outside tracts",
      detail:
        "The versioned parcel geometry does not intersect a designated tract in this evidence snapshot.",
      subline: `${vintage ?? 2010} Census tract geometry`,
      tone: "outline",
    };
  }
  if (evidence.classification === "boundary_review") {
    const count = evidence.designation?.intersectingTractGeoids.length ?? 0;
    const repairedGeometry = evidence.reasonCode === "parcel_geometry_repaired";
    const repairedDesignation =
      evidence.reasonCode === "designation_geometry_repaired";
    return {
      label: repairedDesignation
        ? "Repaired designation geometry requires review"
        : repairedGeometry
          ? "Repaired parcel geometry requires review"
          : "Designation boundary review required",
      shortLabel: "Boundary review",
      detail: repairedDesignation
        ? "The source designation geometry required repair. The platform reports neither inside nor outside until a human reviews the repaired boundary."
        : repairedGeometry
          ? "The source parcel geometry required repair. The platform reports neither inside nor outside until a human reviews the repaired geometry."
          : "The parcel intersects a designation boundary. The platform reports neither inside nor outside until a human reviews the geometry.",
      subline: repairedDesignation
        ? `${count} intersecting ${vintage ?? 2010} tract${count === 1 ? "" : "s"} · repair review`
        : repairedGeometry
          ? `${vintage ?? 2010} parcel geometry · repair review`
          : count
            ? `${count} intersecting ${vintage ?? 2010} tract${count === 1 ? "" : "s"}`
            : `${vintage ?? 2010} Census boundary`,
      tone: "blocked",
    };
  }

  const unavailable = {
    parcel_geometry_unavailable: {
      label: "Parcel geometry unavailable",
      detail: "No approved parcel geometry was available for the spatial comparison.",
    },
    designation_layer_unavailable: {
      label: "2018 designation layer unavailable",
      detail: "The approved designation layer was unavailable for this evidence snapshot.",
    },
    membership_snapshot_unavailable: {
      label: "Membership snapshot unavailable",
      detail: "No complete versioned parcel-to-designation comparison is available.",
    },
    display_not_approved: {
      label: "Reference display not approved",
      detail:
        "The authenticated Opportunity Zone reference-display gate is closed. No underlying geographic result is disclosed.",
    },
  } as const;
  const state =
    evidence.reasonCode in unavailable
      ? unavailable[evidence.reasonCode as keyof typeof unavailable]
      : unavailable.membership_snapshot_unavailable;
  return {
    label: state.label,
    shortLabel:
      evidence.reasonCode === "display_not_approved" ? "Display gated" : "Unavailable",
    detail: state.detail,
    subline: "2018 round · 2010 Census layer",
    tone: "blocked",
  };
}
