#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/setup_neurolink_env.sh"
FORMAT_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/format_neurolink_c_style.sh"
FAIL_ON_WARNINGS=0
TARGETS=(
  "applocation/NeuroLink/neuro_unit/include"
  "applocation/NeuroLink/neuro_unit/src"
  "applocation/NeuroLink/neuro_unit/tests/unit/src"
)
IGNORE_TYPES=(
  "SPDX_LICENSE_TAG"
)

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh [--fail-on-warnings] [--target <path> ...] [--ignore-type <type> ...]
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 not found in PATH" >&2
    exit 2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fail-on-warnings)
      FAIL_ON_WARNINGS=1
      shift
      ;;
    --target)
      [[ $# -ge 2 ]] || {
        echo "missing value for --target" >&2
        exit 2
      }
      TARGETS+=("$2")
      shift 2
      ;;
    --ignore-type)
      [[ $# -ge 2 ]] || {
        echo "missing value for --ignore-type" >&2
        exit 2
      }
      IGNORE_TYPES+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -f "${ENV_SCRIPT}" ]] || {
  echo "setup script not found: ${ENV_SCRIPT}" >&2
  exit 2
}

# shellcheck disable=SC1090
source "${ENV_SCRIPT}" --activate

require_cmd clang-format
require_cmd perl
[[ -f "${FORMAT_SCRIPT}" ]] || {
  echo "format script not found: ${FORMAT_SCRIPT}" >&2
  exit 2
}

cd "${ROOT_DIR}"
bash "${FORMAT_SCRIPT}" --check-only

declare -A seen=()
relative_files=()
for target in "${TARGETS[@]}"; do
  [[ -d "${target}" ]] || continue
  while IFS= read -r -d '' file_path; do
    relative_path="${file_path#${ROOT_DIR}/}"
    if [[ -z "${seen["${relative_path}"]+x}" ]]; then
      seen["${relative_path}"]=1
      relative_files+=("${relative_path}")
    fi
  done < <(find "${target}" -type f \( -name '*.c' -o -name '*.h' \) -print0)
done

if [[ ${#relative_files[@]} -eq 0 ]]; then
  echo "no C/H files found under target paths"
  exit 0
fi

mapfile -t relative_files < <(printf '%s\n' "${relative_files[@]}" | sort -u)

ignore_args=()
for ignore_type in "${IGNORE_TYPES[@]}"; do
  ignore_args+=(--ignore "${ignore_type}")
done

output_file="$(mktemp)"
trap 'rm -f "${output_file}"' EXIT

for relative_path in "${relative_files[@]}"; do
  perl zephyr/scripts/checkpatch.pl --no-tree --terse --show-types \
    "${ignore_args[@]}" --file "${relative_path}" >>"${output_file}" 2>&1 || true
done

mapfile -t findings < <(grep -E ': (ERROR|WARNING):[A-Z0-9_]+' "${output_file}" || true)
error_count=0
warning_count=0
for finding in "${findings[@]}"; do
  if [[ "${finding}" == *": ERROR:"* ]]; then
    ((error_count+=1))
  elif [[ "${finding}" == *": WARNING:"* ]]; then
    ((warning_count+=1))
  fi
done

if [[ ${#findings[@]} -eq 0 ]]; then
  echo "linux kernel style check passed (${#relative_files[@]} files)"
  exit 0
fi

echo "linux kernel style findings: errors=${error_count} warnings=${warning_count}"
cat "${output_file}"

if [[ ${error_count} -gt 0 || ( ${FAIL_ON_WARNINGS} -eq 1 && ${warning_count} -gt 0 ) ]]; then
  exit 1
fi

exit 0
