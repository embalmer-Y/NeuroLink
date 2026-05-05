#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SMOKE_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/smoke_neurolink_linux.sh"

bash -n "${SMOKE_SCRIPT}"

script_text="$(<"${SMOKE_SCRIPT}")"

for expected in \
  'FAILED_STEP="-"' \
  'FAILURE_EXIT_CODE=0' \
  'run_smoke_step()' \
  'artifact_is_valid_llext_file()' \
  'echo "failed_step=${FAILED_STEP}"' \
  'echo "failure_exit_code=${FAILURE_EXIT_CODE}"'; do
  if [[ "${script_text}" != *"${expected}"* ]]; then
    echo "smoke script missing expected failure-summary contract: ${expected}" >&2
    exit 1
  fi
done

for status in \
  '"error"' \
  '"not_implemented"' \
  '"invalid_input"' \
  '"query_failed"' \
  '"no_reply"' \
  '"error_reply"'; do
  if [[ "${script_text}" != *"${status}"* ]]; then
    echo "smoke script missing nested failure status classification: ${status}" >&2
    exit 1
  fi
done

echo "test_smoke_neurolink_linux.sh: PASS"