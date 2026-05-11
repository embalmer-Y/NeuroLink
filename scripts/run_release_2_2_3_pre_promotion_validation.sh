#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CORE_DIR="${ROOT_DIR}/applocation/NeuroLink"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/run_release_2_2_3_pre_promotion_validation.sh

Runs the focused release-2.2.3 pre-promotion validation slice for the social
adapter expansion and final closure-summary bundle.

Coverage:
  1. qq_openclaw readiness, normalization, and OpenClaw gateway client tests
  2. social-adapter-smoke regression for additive qq_openclaw evidence
  3. closure-summary regressions that keep the final social adapter bundle green
EOF
}

if [[ ${1:-} == "-h" || ${1:-} == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -gt 0 ]]; then
  echo "unknown argument: $1" >&2
  usage >&2
  exit 2
fi

[[ -x "${PYTHON_BIN}" ]] || {
  echo "python interpreter not found at ${PYTHON_BIN}" >&2
  exit 2
}

cd "${CORE_DIR}"
export PYTHONPATH=.

social_args=(
  -m pytest
  neurolink_core/tests/test_social_adapters.py
  -q
  -k
  "qq_openclaw or openclaw_gateway_client_binds_and_dispatches_wechat_ilink or openclaw_gateway_client_binds_and_dispatches_qq_openclaw or test_cli_social_adapter_smoke_reports_registry_and_protocol_gates"
)

closure_args=(
  -m pytest
  neurolink_core/tests/test_neurolink_core.py
  -q
  -k
  "test_cli_social_adapter_smoke_reports_ingress_and_affective_egress or test_cli_closure_summary_keeps_social_adapter_bundle_green_with_qq_openclaw_smoke or test_cli_closure_summary_exposes_release_validation_gate_matrix_when_evidence_is_supplied"
)

printf 'Running release-2.2.3 social validation slice...\n'
"${PYTHON_BIN}" "${social_args[@]}"

printf 'Running release-2.2.3 closure validation slice...\n'
"${PYTHON_BIN}" "${closure_args[@]}"

printf 'release-2.2.3 pre-promotion validation: PASS\n'