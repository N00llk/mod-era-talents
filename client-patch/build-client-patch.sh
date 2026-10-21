#!/usr/bin/env bash
# Build one locale from the user's original Spell.dbc + SkillLineAbility.dbc.
# Usage: build-client-patch.sh --locale ruRU --source-dbc DIR [--out FILE]
#        [--mode auto|native|docker] [--force] [--without-addon]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CP="$ROOT/client-patch"
MODE="${ERA_MPQ_MODE:-auto}"
LOCALE=""; SOURCE=""; OUT=""
EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --locale) LOCALE="${2:?--locale needs a locale}"; shift 2 ;;
    --source-dbc) SOURCE="${2:?--source-dbc needs a directory}"; shift 2 ;;
    --out) OUT="${2:?--out needs a file}"; shift 2 ;;
    --mode) MODE="${2:?--mode needs auto|native|docker}"; shift 2 ;;
    --force|--without-addon) EXTRA+=("$1"); shift ;;
    *) echo "Unsupported option: $1. Use --locale LOCALE --source-dbc DIR [--out FILE] [--mode auto|native|docker]. IP archives are no longer supported." >&2; exit 2 ;;
  esac
done
[[ -n "$LOCALE" && -n "$SOURCE" ]] || { echo 'Required: --locale LOCALE --source-dbc DIR' >&2; exit 2; }
[[ "$LOCALE" =~ ^[a-z]{2}[A-Z]{2}$ ]] || { echo "Invalid locale: $LOCALE" >&2; exit 2; }
[[ -f "$SOURCE/Spell.dbc" && -f "$SOURCE/SkillLineAbility.dbc" ]] || { echo 'Source directory needs Spell.dbc and SkillLineAbility.dbc' >&2; exit 2; }
SOURCE="$(cd "$SOURCE" && pwd)"
OUT="${OUT:-$CP/out/$LOCALE/patch-V.mpq}"
if [[ "$MODE" == auto ]]; then
  if [[ -x "$CP/mpqpack" && -x "$CP/mpqread" ]] && python3 -c 'import yaml' >/dev/null 2>&1; then MODE=native
  elif command -v docker >/dev/null 2>&1; then MODE=docker
  else MODE=native
  fi
fi
case "$MODE" in
  native)
    [[ -x "$CP/mpqpack" && -x "$CP/mpqread" ]] || bash "$CP/build-mpqpack.sh"
    if command -v uv >/dev/null 2>&1; then PYRUN=(uv run --with pyyaml python)
    else PYRUN=(python3)
    fi
    "${PYRUN[@]}" "$ROOT/tools/build_client_patch.py" --locale "$LOCALE" --source-dbc "$SOURCE" --out "$OUT" "${EXTRA[@]}" ;;
  docker)
    mkdir -p "$(dirname "$OUT")"
    OUTDIR="$(cd "$(dirname "$OUT")" && pwd)"
    docker build -q -t mod-era-talents-mpq:local "$CP" >/dev/null
    docker run --rm -u "$(id -u):$(id -g)" \
      -v "$ROOT:/work:ro" -v "$SOURCE:/source:ro" -v "$OUTDIR:/out" \
      mod-era-talents-mpq:local python3 /work/tools/build_client_patch.py \
      --locale "$LOCALE" --source-dbc /source --out "/out/$(basename "$OUT")" "${EXTRA[@]}" ;;
  *) echo "Unknown mode: $MODE" >&2; exit 2 ;;
esac
