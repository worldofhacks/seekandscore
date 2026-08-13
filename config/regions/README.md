# Region packs

Region packs describe local capabilities and configuration without putting county/state conditionals in core application code.

Each version should declare:

- stable jurisdiction identifiers and time zones;
- source instances, capability, rollout status, schedule, and source-policy reference;
- local property/use mappings;
- authoritative GIS layers and boundary vintages;
- named corridors/reference points;
- approved scoring-profile reference/overrides;
- outreach policy reference, rollout mode, and intentionally enabled purposes/channels;
- compliance/access notes;
- activation state (`development`, `shadow`, `review`, `active`, `suspended`).

Credentials never belong in region packs. Use secret-variable references resolved by the runtime.

The example Central Texas pack is a planning artifact. Its ingestion profile may identify an adapter and bounded endpoint while the source remains `rights_review`; that does not grant activation. Sources remain disabled until supported access, rights, artifact durability, and replay are approved.

Property location is only one outreach-policy input. Participant, sender, organization, contact-source, and campaign jurisdictions may also matter. A region pack may reference a reviewed policy but cannot declare a channel legal or bypass a stricter suppression/source/organization rule.
