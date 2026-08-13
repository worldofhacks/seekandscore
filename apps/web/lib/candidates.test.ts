import { describe, expect, it } from "vitest";

import {
  filterCandidates,
  formatMoneyCompact,
  rankMovement,
  topQueueSnapshot,
} from "./candidates";

describe("Top 25 queue fixture", () => {
  it("contains exactly 25 uniquely ranked synthetic candidates", () => {
    expect(topQueueSnapshot.isSynthetic).toBe(true);
    expect(topQueueSnapshot.candidates).toHaveLength(25);
    expect(new Set(topQueueSnapshot.candidates.map((candidate) => candidate.rank)).size).toBe(25);
    expect(new Set(topQueueSnapshot.candidates.map((candidate) => candidate.id)).size).toBe(25);
  });

  it("fails outreach closed for every candidate", () => {
    expect(
      topQueueSnapshot.candidates.every(
        (candidate) =>
          candidate.outreachGate.status === "blocked" &&
          candidate.outreachGate.blockers.length > 0,
      ),
    ).toBe(true);
  });
});

describe("candidate queue helpers", () => {
  it("reports positive rank movement when a candidate rises", () => {
    expect(rankMovement({ rank: 1, previousRank: 3 })).toBe(2);
    expect(rankMovement({ rank: 4, previousRank: null })).toBeNull();
  });

  it("filters by queue state and searchable evidence labels", () => {
    const candidates = topQueueSnapshot.candidates;
    expect(filterCandidates(candidates, "new", "")).toHaveLength(3);
    expect(filterCandidates(candidates, "all", "Caldwell").length).toBeGreaterThan(0);
    expect(filterCandidates(candidates, "all", "does-not-exist")).toEqual([]);
  });

  it("formats operating values compactly", () => {
    expect(formatMoneyCompact(980000)).toBe("$980K");
    expect(formatMoneyCompact(1_260_000)).toContain("$1.26M");
  });
});
