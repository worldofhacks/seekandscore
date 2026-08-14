import Link from "next/link";

import type { CandidateAppliedFilters } from "@seekandscore/contracts";
import { Button } from "@seekandscore/ui";

import { ArrowUpIcon, SearchIcon } from "@/components/icons";
import {
  buildCandidateExplorerHref,
  hasCandidateFilters,
} from "@/lib/candidate-query";

const approvedCities = [
  { label: "All approved cities", value: "" },
  { label: "Del Valle", value: "DEL VALLE" },
  { label: "Manor", value: "MANOR" },
] as const;

interface CandidateFiltersProps {
  enabled: boolean;
  filters: CandidateAppliedFilters;
}

export function CandidateFilters({ enabled, filters }: CandidateFiltersProps) {
  const filtered = hasCandidateFilters(filters);

  return (
    <form
      action="/"
      aria-label="Filter approved live cohort"
      className="cohort-filters"
      method="get"
    >
      <div className="cohort-filters__field cohort-filters__field--query">
        <label htmlFor="cohort-query">Parcel or address</label>
        <div className="cohort-filters__input">
          <SearchIcon aria-hidden="true" />
          <input
            defaultValue={filters.q ?? ""}
            disabled={!enabled}
            id="cohort-query"
            maxLength={100}
            name="q"
            placeholder="Search address or parcel ID"
            type="search"
          />
        </div>
      </div>

      <fieldset className="cohort-filters__cities" disabled={!enabled}>
        <legend>City</legend>
        <div>
          {approvedCities.map((city) => (
            <label key={city.value || "all"}>
              <input
                defaultChecked={(filters.city ?? "") === city.value}
                name="city"
                type="radio"
                value={city.value}
              />
              <span>{city.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="cohort-filters__acreage" role="group" aria-label="Acreage range">
        <div className="cohort-filters__field">
          <label htmlFor="minimum-acreage">Min acres</label>
          <input
            defaultValue={filters.minAcres ?? ""}
            disabled={!enabled}
            id="minimum-acreage"
            min="0"
            name="min_acres"
            placeholder="Any"
            step="0.1"
            type="number"
          />
        </div>
        <span aria-hidden="true">–</span>
        <div className="cohort-filters__field">
          <label htmlFor="maximum-acreage">Max acres</label>
          <input
            defaultValue={filters.maxAcres ?? ""}
            disabled={!enabled}
            id="maximum-acreage"
            min="0"
            name="max_acres"
            placeholder="Any"
            step="0.1"
            type="number"
          />
        </div>
      </div>

      <div className="cohort-filters__actions">
        <Button disabled={!enabled} size="small" type="submit" variant="primary">
          Apply filters
        </Button>
        {filtered ? (
          <Link className="cohort-filters__clear" href="/">
            Clear filters
          </Link>
        ) : null}
      </div>
    </form>
  );
}

interface CandidatePaginationProps {
  filters: CandidateAppliedFilters;
  nextCursor: string | null;
}

export function CandidatePagination({
  filters,
  nextCursor,
}: CandidatePaginationProps) {
  return (
    <nav aria-label="Candidate cohort pages" className="cohort-pagination">
      <p>Use browser Back to return to the previous page.</p>
      {nextCursor ? (
        <Link
          className="ui-button ui-button--secondary ui-button--small"
          href={buildCandidateExplorerHref(filters, nextCursor)}
          rel="next"
        >
          Next page
          <ArrowUpIcon aria-hidden="true" className="cohort-pagination__arrow" />
        </Link>
      ) : (
        <span>End of filtered cohort</span>
      )}
    </nav>
  );
}
