#!/usr/bin/env python3
"""Parse repository YAML/TOML and enforce deployment safety invariants."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - developer setup guard
    raise SystemExit("PyYAML is required: install project dev dependencies first") from exc


ROOT = Path(__file__).resolve().parents[2]


def parse_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def parse_toml(path: Path) -> Any:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def require_safe_runtime_defaults() -> list[str]:
    failures: list[str] = []
    entrypoint = (ROOT / "scripts/runtime/python-entrypoint.sh").read_text(encoding="utf-8")
    expected = {
        "DATASET_MODE": "live",
        "INGESTION_ENABLED": "false",
        "LIVE_SOURCE_DISPLAY_ENABLED": "false",
        "OUTREACH_MODE": "disabled",
        "OUTREACH_SEND_ENABLED": "false",
    }
    for name, value in expected.items():
        if f"${{{name}:={value}}}" not in entrypoint:
            failures.append(f"python entrypoint must default {name}={value}")
    if "MIGRATION_DATABASE_URL belongs only on db-migrate" not in entrypoint:
        failures.append("deployed Python runtime must reject the migration owner credential")
    if "deployed Python services require a database role audit" not in entrypoint:
        failures.append("deployed Python runtime must require a database role audit wrapper")

    role_entrypoint = (ROOT / "scripts/runtime/database-role-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    for marker in (
        "audit-api-runtime",
        "audit-ingestion-runtime",
        "owner credential must not be present at runtime",
    ):
        if marker not in role_entrypoint:
            failures.append(f"database role entrypoint is missing safety marker: {marker}")

    web_entrypoint = (ROOT / "scripts/runtime/web-entrypoint.sh").read_text(encoding="utf-8")
    if "${DATASET_MODE:=live}" not in web_entrypoint:
        failures.append("web entrypoint must default DATASET_MODE=live")
    if 'if [ "$DATASET_MODE" != "live" ]' not in web_entrypoint:
        failures.append("web entrypoint must reject non-live dataset modes")
    if "API_BASE_URL is required in $APP_ENV" not in web_entrypoint:
        failures.append("web staging/production runtime must require API_BASE_URL")
    if "web startup refused: unsupported APP_ENV" not in web_entrypoint:
        failures.append("web runtime must reject unknown application environments")
    if "WEB_PRIVATE_ACCESS_ENABLED must be true in $APP_ENV" not in web_entrypoint:
        failures.append("web staging/production runtime must require private access")
    for name in ("WEB_PRIVATE_ACCESS_USERNAME", "WEB_PRIVATE_ACCESS_PASSWORD"):
        if f"{name} is required in $APP_ENV" not in web_entrypoint:
            failures.append(f"web staging/production runtime must require {name}")
    if "WEB_PRIVATE_ACCESS_PASSWORD must be at least 24 characters" not in web_entrypoint:
        failures.append("web staging/production runtime must enforce private password length")
    if "research writes require the exact private Railway API origin" not in web_entrypoint:
        failures.append("web research writes must require the exact private API origin")
    if "saved research is disabled in development and test runtimes" not in web_entrypoint:
        failures.append("web research writes must fail closed in development/test runtimes")

    web_proxy = (ROOT / "apps/web/proxy.ts").read_text(encoding="utf-8")
    if 'const HEALTH_PATH = "/api/health"' not in web_proxy:
        failures.append("web private-access proxy must preserve only /api/health")
    if 'matcher: "/:path*"' not in web_proxy:
        failures.append("web private-access proxy must cover every application path")
    if "requestHeaders.delete(OPERATOR_HEADER)" not in web_proxy:
        failures.append("web proxy must remove caller-supplied operator identity")

    research_proxy = (ROOT / "apps/web/lib/research-proxy.ts").read_text(encoding="utf-8")
    for marker, description in (
        ('import "server-only"', "research proxy must be server-only"),
        ('redirect: "error"', "research proxy must reject redirects"),
        (
            '"http://api.railway.internal:8000"',
            "research proxy must pin the private Railway API origin",
        ),
    ):
        if marker not in research_proxy:
            failures.append(description)

    web_dockerfile = (ROOT / "infra/docker/web.Dockerfile").read_text(encoding="utf-8")
    if "APP_ENV=production" not in web_dockerfile:
        failures.append("web production image must set APP_ENV=production")
    if "DATASET_MODE=live" not in web_dockerfile:
        failures.append("web production image must set DATASET_MODE=live")

    for image_name in ("api", "worker"):
        dockerfile = (ROOT / f"infra/docker/{image_name}.Dockerfile").read_text(encoding="utf-8")
        if "APP_ENV=production" not in dockerfile:
            failures.append(f"{image_name} production image must set APP_ENV=production")
        if "DATASET_MODE=live" not in dockerfile:
            failures.append(f"{image_name} production image must set DATASET_MODE=live")
    api_dockerfile = (ROOT / "infra/docker/api.Dockerfile").read_text(encoding="utf-8")
    if 'database-role-entrypoint.sh", "api"' not in api_dockerfile:
        failures.append("API image default command must audit the API database role")
    worker_dockerfile = (ROOT / "infra/docker/worker.Dockerfile").read_text(encoding="utf-8")
    if 'database-role-entrypoint.sh", "unprovisioned"' not in worker_dockerfile:
        failures.append("worker default command must refuse an unprovisioned database role")

    compose = parse_yaml(ROOT / "compose.yaml")
    runtime = compose.get("x-safe-runtime", {}) if isinstance(compose, dict) else {}
    for name, value in expected.items():
        if str(runtime.get(name, "")).lower() != value:
            failures.append(f"compose x-safe-runtime must set {name}={value}")
    return failures


def require_safe_railway_commands() -> list[str]:
    """Ensure Railway cannot bypass fail-closed Python runtime defaults."""

    failures: list[str] = []
    safe_entrypoints = (
        "/app/scripts/runtime/python-entrypoint.sh",
        "/app/scripts/runtime/database-role-entrypoint.sh",
        "/app/scripts/runtime/db-migrate-entrypoint.sh",
    )
    for path in sorted((ROOT / "infra/railway").glob("*.toml")):
        config = parse_toml(path)
        deploy = config.get("deploy", {}) if isinstance(config, dict) else {}
        command = deploy.get("startCommand") if isinstance(deploy, dict) else None
        if (
            isinstance(command, str)
            and "python -m seekandscore" in command
            and not command.startswith(tuple(f"{entrypoint} " for entrypoint in safe_entrypoints))
        ):
            failures.append(
                f"{path.relative_to(ROOT)}: Python startCommand must invoke a safe entrypoint"
            )
    return failures


def require_database_role_isolation() -> list[str]:
    """Keep owner credentials on one one-shot service and audit every deployed DB runtime."""

    failures: list[str] = []
    railway = ROOT / "infra/railway"
    expected_start_fragments = {
        "api.example.toml": "database-role-entrypoint.sh api ",
        "ingestion-travis.example.toml": "database-role-entrypoint.sh ingestion ",
        "ingestion-travis.cron.example.toml": "database-role-entrypoint.sh ingestion ",
        "worker-discovery.example.toml": "database-role-entrypoint.sh ingestion ",
        "worker-enrichment.example.toml": "database-role-entrypoint.sh unprovisioned ",
        "worker-engagement.example.toml": "database-role-entrypoint.sh unprovisioned ",
        "scheduler.example.toml": "database-role-entrypoint.sh unprovisioned ",
    }
    for filename, marker in expected_start_fragments.items():
        deploy = parse_toml(railway / filename).get("deploy", {})
        command = deploy.get("startCommand", "") if isinstance(deploy, dict) else ""
        if marker not in command:
            failures.append(f"infra/railway/{filename}: missing database role contract {marker}")
        if isinstance(deploy, dict) and "preDeployCommand" in deploy:
            failures.append(f"infra/railway/{filename}: runtime service must not own migrations")

    migration_path = railway / "db-migrate.example.toml"
    migration_deploy = parse_toml(migration_path).get("deploy", {})
    if not isinstance(migration_deploy, dict):
        failures.append("infra/railway/db-migrate.example.toml: deploy config is required")
        return failures
    if migration_deploy.get("preDeployCommand") != (
        "/app/scripts/runtime/db-migrate-entrypoint.sh python -m seekandscore.db.release apply"
    ):
        failures.append("db-migrate must exclusively apply migrations and provision runtime roles")
    if migration_deploy.get("startCommand") != (
        "/app/scripts/runtime/db-migrate-entrypoint.sh python -m seekandscore.db.release verify"
    ):
        failures.append("db-migrate start must verify schema and both runtime roles")

    for path in sorted(railway.glob("*.toml")):
        if path == migration_path:
            continue
        content = path.read_text(encoding="utf-8")
        if "seekandscore.db.migrate" in content or "MIGRATION_DATABASE_URL" in content:
            failures.append(
                f"{path.relative_to(ROOT)}: owner migration capability belongs only on db-migrate"
            )
    return failures


def require_live_only_runtime_tree() -> list[str]:
    """Prevent candidate fixtures or substitute modes from returning to runtime code."""

    failures: list[str] = []
    runtime_roots = (
        ROOT / "python/seekandscore",
        ROOT / "apps/web",
        ROOT / "packages/contracts/typescript",
    )
    forbidden = {
        "SyntheticCandidateRepository": "fixture-backed candidate repository",
        'dataset_status="fallback"': "fallback candidate status",
        'dataset_status="synthetic"': "non-live candidate status",
        "DatasetMode.SYNTHETIC": "non-live dataset mode",
        "synthetic-candidate-v1": "fixture read-model version",
    }
    suffixes = {".py", ".ts", ".tsx"}
    for root in runtime_roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in suffixes or ".next" in path.parts:
                continue
            if ".test." in path.name:
                continue
            content = path.read_text(encoding="utf-8")
            for marker, label in forbidden.items():
                if marker in content:
                    failures.append(f"{path.relative_to(ROOT)}: contains forbidden {label}")
    if (ROOT / "apps/web/lib/candidates.ts").exists():
        failures.append(
            "apps/web/lib/candidates.ts: deployed candidate fixture module must not exist"
        )
    return failures


def require_safe_ingestion_profiles() -> list[str]:
    """Keep committed live-source descriptions inert and bounded."""

    failures: list[str] = []
    for path in sorted((ROOT / "config/ingestion").glob("*.yaml")):
        profile = parse_yaml(path)
        label = path.relative_to(ROOT)
        if not isinstance(profile, dict):
            failures.append(f"{label}: ingestion profile must be a mapping")
            continue
        if profile.get("default_enabled") is not False:
            failures.append(f"{label}: default_enabled must be false")
        sources = profile.get("sources")
        if not isinstance(sources, list) or not sources:
            failures.append(f"{label}: sources must be a non-empty list")
            continue
        for source in sources:
            if not isinstance(source, dict):
                failures.append(f"{label}: every source must be a mapping")
                continue
            source_id = source.get("id", "<unknown>")
            if source.get("enabled") is not False:
                failures.append(f"{label}#{source_id}: enabled must be false")
            bounds = source.get("bounded_fetch")
            if not isinstance(bounds, dict):
                continue
            page_size = bounds.get("default_page_size")
            max_page_size = bounds.get("maximum_page_size")
            contract = source.get("upstream_contract", {})
            provider_max = contract.get("provider_max_record_count", 0)
            if not all(isinstance(value, int) for value in (page_size, max_page_size)):
                failures.append(f"{label}#{source_id}: page bounds must be integers")
            elif page_size > max_page_size:
                failures.append(f"{label}#{source_id}: default page exceeds maximum")
            if (
                isinstance(provider_max, int)
                and isinstance(max_page_size, int)
                and provider_max
                and max_page_size > provider_max
            ):
                failures.append(f"{label}#{source_id}: page maximum exceeds provider limit")
            if bounds.get("max_concurrency") != 1:
                failures.append(f"{label}#{source_id}: max_concurrency must be 1")
    return failures


def main() -> int:
    failures: list[str] = []
    paths = sorted((ROOT / "config").rglob("*.yaml"))
    paths += sorted((ROOT / ".github").rglob("*.yml"))
    paths += [ROOT / "compose.yaml", ROOT / "pnpm-workspace.yaml"]
    paths += sorted((ROOT / "infra/railway").glob("*.toml"))

    for path in paths:
        try:
            parsed = parse_toml(path) if path.suffix == ".toml" else parse_yaml(path)
            if parsed is None:
                failures.append(f"{path.relative_to(ROOT)}: empty configuration")
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")

    try:
        failures.extend(require_safe_runtime_defaults())
        failures.extend(require_safe_railway_commands())
        failures.extend(require_database_role_isolation())
        failures.extend(require_live_only_runtime_tree())
        failures.extend(require_safe_ingestion_profiles())
    except Exception as exc:
        failures.append(f"deployment safety validation failed: {exc}")

    if failures:
        print("Configuration validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Validated {len(paths)} YAML/TOML files and safe runtime defaults.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
