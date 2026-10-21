#!/usr/bin/env bash
# Stage user-supplied stock build-12340 DBCs for server template generation.
# Historical filename retained for callers; this script performs no downloads.
# Usage: tools/fetch-base-dbc.sh <original-client-dbc-directory>
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${1:?usage: fetch-base-dbc.sh <original-client-dbc-directory>}"
OUT="$ROOT/client-patch/base"
for file in Spell.dbc SkillLineAbility.dbc; do
  [[ -f "$SOURCE/$file" ]] || { echo "Missing original client DBC: $SOURCE/$file" >&2; exit 1; }
done
mkdir -p "$OUT"
for file in Spell.dbc SkillLineAbility.dbc; do
  [[ "$SOURCE/$file" -ef "$OUT/$file" ]] || cp "$SOURCE/$file" "$OUT/$file"
done
echo "Staged original client DBCs in $OUT"
