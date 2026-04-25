#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/setup_neurolink_env.sh"
STYLE_FILE="${ROOT_DIR}/applocation/NeuroLink/neuro_unit/.clang-format"
STYLE_ARG="file:${STYLE_FILE}"
FIX=0
CHECK_ONLY=0
TARGETS=(
  "applocation/NeuroLink/neuro_unit/include"
  "applocation/NeuroLink/neuro_unit/src"
  "applocation/NeuroLink/neuro_unit/tests/unit/src"
)

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/format_neurolink_c_style.sh [--fix|--check-only] [--target <path> ...]
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 not found in PATH" >&2
    exit 2
  fi
}

normalize_lf() {
  local file_path="$1"
  perl -0pi -e 's/\r\n/\n/g; s/\r/\n/g; $_ .= "\n" unless /\n\z/' "$file_path"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix)
      FIX=1
      shift
      ;;
    --check-only)
      CHECK_ONLY=1
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

if [[ ${FIX} -eq 1 && ${CHECK_ONLY} -eq 1 ]]; then
  echo "Use either --fix or --check-only, not both." >&2
  exit 2
fi

if [[ ${FIX} -eq 0 && ${CHECK_ONLY} -eq 0 ]]; then
  CHECK_ONLY=1
fi

require_cmd clang-format
[[ -f "${STYLE_FILE}" ]] || {
  echo "style file not found: ${STYLE_FILE}" >&2
  exit 2
}

cd "${ROOT_DIR}"

declare -A seen=()
files=()
for target in "${TARGETS[@]}"; do
  [[ -d "${target}" ]] || continue
  while IFS= read -r -d '' file_path; do
    if [[ -z "${seen["${file_path}"]+x}" ]]; then
      seen["${file_path}"]=1
      files+=("${file_path}")
    fi
  done < <(find "${target}" -type f \( -name '*.c' -o -name '*.h' \) -print0)
done

if [[ ${#files[@]} -eq 0 ]]; then
  echo "no C/H files found under target paths"
  exit 0
fi

mapfile -t files < <(printf '%s\n' "${files[@]}" | sort -u)

if [[ ${FIX} -eq 1 ]]; then
  for file_path in "${files[@]}"; do
    normalize_lf "${file_path}"
    clang-format -style="${STYLE_ARG}" -i "${file_path}"
  done
  echo "formatted ${#files[@]} files with Linux kernel style and normalized LF line endings"
  exit 0
fi

violations=()
for file_path in "${files[@]}"; do
  if ! clang-format -style="${STYLE_ARG}" --dry-run --Werror "${file_path}" >/dev/null 2>&1; then
    violations+=("${file_path}")
  fi
done

if [[ ${#violations[@]} -eq 0 ]]; then
  echo "c-style check passed (${#files[@]} files)"
  exit 0
fi

echo "c-style check failed: ${#violations[@]} file(s) need formatting"
for file_path in "${violations[@]}"; do
  echo " - ${file_path}"
done
exit 1
