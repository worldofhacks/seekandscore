# Ingestion profiles

Ingestion profiles are versioned source and operational contracts. They never contain credentials and never activate network acquisition by themselves.

All committed profiles must set `default_enabled: false`, every source must set `enabled: false`, and a live run must separately satisfy the application environment gates. A source may move from `rights_review` to a narrowly scoped approval only through a recorded evidence review and operator decision; the repository profile still stays disabled so Railway variables remain the final kill switch.

The first bounded profile is [`us-tx-central-texas-v1.yaml`](us-tx-central-texas-v1.yaml). Its Travis approval covers bounded collection, private raw retention, and attributed reference display of the non-owner field allowlist. It explicitly excludes export, redistribution, owner/contact use, legal-boundary conclusions, appraisal, and offers. The Opportunity Zone entries remain reference-only until vintage-correct tract joining exists.

`INGESTION_CONFIG_PATH` is an audit/reserved reference in this first slice; the runtime does not dynamically execute the YAML. The v1 URL, field list, predicate, and ordering are compiled and tested so a config-only change cannot broaden acquisition. Signed/versioned profile loading can be added after its own security and change-control design.

Raw acquisition must be stored before parsing with a SHA-256 content address and source/config lineage. Do not commit downloaded source artifacts; `data/raw/` and `var/raw-artifacts/` are ignored.
