.DEFAULT_GOAL := help

.PHONY: help install check lint test build infra-up infra-down infra-logs infra-status app-up ingestion-check ingestion-run-local compose-config config-check secret-check

help: ## List common development commands.
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "%-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install locked Python and JavaScript dependencies.
	uv sync --frozen --group dev
	corepack enable
	pnpm install --frozen-lockfile

check: config-check secret-check ## Run repository quality gates.
	uv run ruff check python services tests/backend migrations
	uv run ruff format --check python services tests/backend migrations
	uv run mypy python services
	uv run pytest tests/backend
	pnpm check

lint: ## Run Python and web linters.
	uv run ruff check python services tests/backend migrations
	pnpm lint

test: ## Run Python and web tests.
	uv run pytest tests/backend
	pnpm test

build: ## Build the production web bundle.
	pnpm build

infra-up: ## Start local PostGIS, Redis, and MinIO.
	docker compose up --detach --wait postgis redis minio
	docker compose run --rm minio-init

infra-down: ## Stop local infrastructure without deleting data volumes.
	docker compose down

infra-logs: ## Follow local infrastructure logs.
	docker compose logs --follow postgis redis minio

infra-status: ## Show local service status.
	docker compose ps

app-up: ## Build and start the full local stack with safe defaults.
	docker compose --profile app up --build

ingestion-check: ## Check ingestion gates without acquiring source data.
	APP_ENV=development DATASET_MODE=synthetic INGESTION_ENABLED=false uv run python -m seekandscore.ingestion check

ingestion-run-local: ## Run the bounded local job; required live gates come only from the caller.
	docker compose --profile ingestion run --rm -e APP_ENV -e DATASET_MODE -e INGESTION_ENABLED -e INGESTION_ACTIVATION_ID ingestion-travis

compose-config: ## Validate and render the Compose model.
	docker compose config --quiet

config-check: ## Parse YAML and TOML configuration files.
	uv run python scripts/ci/validate_config.py

secret-check: ## Scan tracked text for high-confidence credential patterns.
	scripts/ci/check-secrets.sh
