# Scoring profiles

Scoring profiles are immutable after activation. A behavioral change creates a new version so historical ranks remain reproducible.

Every profile defines:

- eligibility gates and strategy applicability;
- component inputs, weights, normalization, null/unknown behavior;
- risk deductions and fatal/manual-review conditions;
- confidence aggregation and adjustment;
- material-event thresholds and smoothing;
- Top-25 composition preferences;
- units, rounding, and explanation templates;
- fixture suite and approval record.

The current YAML is a design draft based on the product brief. No runtime should treat it as approved until Milestone 0 review and regression fixtures are complete.
