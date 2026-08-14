# Database migrations

Alembic owns forward migrations for the modular monolith. The first migration
creates only foundational schemas and an append-only platform audit table. Each
future migration must name its owning context and compatibility strategy.

Run `python -m seekandscore.db.migrate upgrade`. Generate offline SQL for review
with `python -m seekandscore.db.migrate upgrade --sql`.
