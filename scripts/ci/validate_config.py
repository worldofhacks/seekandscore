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
        "OUTREACH_MODE": "disabled",
        "OUTREACH_SEND_ENABLED": "false",
    }
    for name, value in expected.items():
        if f'${{{name}:={value}}}' not in entrypoint:
            failures.append(f"python entrypoint must default {name}={value}")

    compose = parse_yaml(ROOT / "compose.yaml")
    runtime = compose.get("x-safe-runtime", {}) if isinstance(compose, dict) else {}
    for name, value in expected.items():
        if str(runtime.get(name, "")).lower() != value:
            failures.append(f"compose x-safe-runtime must set {name}={value}")
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
        except Exception as exc:  # noqa: BLE001 - report every malformed config together
            failures.append(f"{path.relative_to(ROOT)}: {exc}")

    try:
        failures.extend(require_safe_runtime_defaults())
    except Exception as exc:  # noqa: BLE001
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
