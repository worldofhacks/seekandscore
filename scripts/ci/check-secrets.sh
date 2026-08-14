#!/bin/sh
set -eu

pattern='ghp_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,}|AKIA[A-Z0-9]{16}|sk-(proj-)?[A-Za-z0-9_-]{32,}|xox[baprs]-[A-Za-z0-9-]{20,}|-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----'
matches="$(git ls-files --cached --others --exclude-standard -z \
  | xargs -0 grep -EIl "$pattern" -- 2>/dev/null || true)"

if [ -n "$matches" ]; then
  printf '%s\n' "Potential credentials detected in:" >&2
  printf '%s\n' "$matches" >&2
  exit 1
fi

printf '%s\n' "No high-confidence credential patterns detected."
