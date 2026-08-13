# Region packs

Region packs describe local capabilities and configuration without putting county/state conditionals in core application code.

Each version should declare:

- stable jurisdiction identifiers and time zones;
- source instances, capability, rollout status, schedule, and source-policy reference;
- local property/use mappings;
- authoritative GIS layers and boundary vintages;
- named corridors/reference points;
- approved scoring-profile reference/overrides;
- compliance/access notes;
- activation state (`development`, `shadow`, `review`, `active`, `suspended`).

Credentials never belong in region packs. Use secret-variable references resolved by the runtime.

The example Central Texas pack is a planning artifact. Sources remain `planned` until Milestone 0 confirms supported access and rights.
