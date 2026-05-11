#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SCRIPT_PATH="${ROOT_DIR}/applocation/NeuroLink/scripts/run_release_2_2_3_pre_promotion_validation.sh"

output="$(bash "${SCRIPT_PATH}")"

if [[ "${output}" != *"Running release-2.2.3 social validation slice..."* ]]; then
  echo "pre-promotion validation script did not report social validation" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

if [[ "${output}" != *"Running release-2.2.3 closure validation slice..."* ]]; then
  echo "pre-promotion validation script did not report closure validation" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

if [[ "${output}" != *"release-2.2.3 pre-promotion validation: PASS"* ]]; then
  echo "pre-promotion validation script did not finish successfully" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

echo "test_release_2_2_3_pre_promotion_validation.sh: PASS"