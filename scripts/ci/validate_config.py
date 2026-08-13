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
        "INGESTION_ENABLED": "false",
        "LIVE_SOURCE_DISPLAY_ENABLED": "false",
        "OUTREACH_MODE": "disabled",
        "OUTREACH_SEND_ENABLED": "false",
    }
    for name, value in expected.items():
        if f"${{{name}:={value}}}" not in entrypoint:
            failures.append(f"python entrypoint must default {name}={value}")

    compose = parse_yaml(ROOT / "compose.yaml")
    runtime = compose.get("x-safe-runtime", {}) if isinstance(compose, dict) else {}
    for name, value in expected.items():
        if str(runtime.get(name, "")).lower() != value:
            failures.append(f"compose x-safe-runtime must set {name}={value}")
    return failures


def require_safe_railway_commands() -> list[str]:
    """Ensure Railway cannot bypass fail-closed Python runtime defaults."""

    failures: list[str] = []
    safe_entrypoint = "/app/scripts/runtime/python-entrypoint.sh"
    for path in sorted((ROOT / "infra/railway").glob("*.toml")):
        config = parse_toml(path)
        deploy = config.get("deploy", {}) if isinstance(config, dict) else {}
        command = deploy.get("startCommand") if isinstance(deploy, dict) else None
        if (
            isinstance(command, str)
            and "python -m seekandscore" in command
            and not command.startswith(f"{safe_entrypoint} ")
        ):
            failures.append(
                f"{path.relative_to(ROOT)}: Python startCommand must invoke {safe_entrypoint}"
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
