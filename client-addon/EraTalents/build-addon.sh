#!/usr/bin/env bash
# Regenerate the addon's per-(era,class) Lua from every dataset in era-data/datasets.txt.
# Called by tools/era-regen.sh (the only supported ship path); safe to run alone.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if command -v uv >/dev/null 2>&1; then PYRUN=(uv run --with pyyaml python); else PYRUN=(python3); fi
# build_era_addon.py reads era-data/datasets.txt and validates EVERY locale first.
"${PYRUN[@]}" "$ROOT/tools/build_era_addon.py"
