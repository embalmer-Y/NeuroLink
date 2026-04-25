#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TARGET_ROOT="applocation/NeuroLink"
EXECUTE=0

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/clean_zone_identifier.sh [target-root] [--execute]
   or: bash applocation/NeuroLink/scripts/clean_zone_identifier.sh --target <path> [--execute]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      EXECUTE=1
      shift
      ;;
    --target)
      [[ $# -ge 2 ]] || {
        echo "missing value for --target" >&2
        exit 2
      }
      TARGET_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ "$1" == -* ]]; then
        echo "unknown argument: $1" >&2
        usage >&2
        exit 2
      fi
      TARGET_ROOT="$1"
      shift
      ;;
  esac
done

cd "${ROOT_DIR}"

mapfile -d '' candidates < <(find "${TARGET_ROOT}" -type f -name '*:Zone.Identifier' -print0 2>/dev/null)

if [[ ${#candidates[@]} -eq 0 ]]; then
  echo "no matches found for *:Zone.Identifier under ${TARGET_ROOT}"
  exit 0
fi

echo "zone identifier candidates: ${#candidates[@]}"
printf ' - %s\n' "${candidates[@]}"

if [[ ${EXECUTE} -eq 0 ]]; then
  echo "preview only. re-run with --execute to delete."
  exit 0
fi

for candidate in "${candidates[@]}"; do
  rm -f -- "${candidate}"
  echo "removed ${candidate}"
done

echo "zone identifier cleanup completed"
