#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
FORMAT_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/format_neurolink_c_style.sh"
CHECK_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh"

format_output="$(bash "${FORMAT_SCRIPT}" --check-only)"
if [[ "${format_output}" != *"c-style check passed"* ]]; then
  echo "format check-only did not report success" >&2
  printf '%s\n' "${format_output}" >&2
  exit 1
fi

check_output="$(bash "${CHECK_SCRIPT}")"
if [[ "${check_output}" != *"linux kernel style check passed"* && "${check_output}" != *"linux kernel style findings: errors=0"* ]]; then
  echo "style check did not report a passing result" >&2
  printf '%s\n' "${check_output}" >&2
  exit 1
fi

echo "test_style_scripts.sh: PASS"
