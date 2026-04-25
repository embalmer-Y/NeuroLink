#!/usr/bin/env bash
set -euo pipefail

ROOT_DEFAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
ROOT_DIR="${1:-$ROOT_DEFAULT}"
ENV_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/setup_neurolink_env.sh"
OUT_BASE="${2:-applocation/NeuroLink/smoke-evidence/ut-coverage}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${ROOT_DIR}/${OUT_BASE}/${TIMESTAMP}"
BUILD_DIR="${ROOT_DIR}/build/neurolink_unit_ut_native_sim_64_cov"
EXE_PATH="${BUILD_DIR}/zephyr/zephyr.exe"
GCOVR_BIN_DEFAULT="${HOME}/.local/share/pipx/venvs/west/bin/gcovr"

mkdir -p "${OUT_DIR}"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

if [[ ! -f "${ENV_SCRIPT}" ]]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: setup script not found at ${ENV_SCRIPT}" >&2
  exit 2
fi

# Self-bootstrap so coverage collection matches the canonical Linux wrapper model.
# shellcheck disable=SC1090
source "${ENV_SCRIPT}" --activate --strict

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: missing command '$1'"
    exit 2
  fi
}

extract_lcov_metrics() {
  local summary_file="$1"
  awk '
    /lines:/ { line_metric=$0 }
    /functions:/ { function_metric=$0 }
    /branches:/ { branch_metric=$0 }
    END {
      if (line_metric != "") print line_metric;
      if (function_metric != "") print function_metric;
      if (branch_metric != "") print branch_metric;
    }
  ' "${summary_file}"
}

log "root_dir=${ROOT_DIR}"
log "out_dir=${OUT_DIR}"

require_cmd west
require_cmd gcc
require_cmd timeout

if [[ -x "${GCOVR_BIN_DEFAULT}" ]]; then
  GCOVR_BIN="${GCOVR_BIN_DEFAULT}"
elif command -v gcovr >/dev/null 2>&1; then
  GCOVR_BIN="$(command -v gcovr)"
else
  log "ERROR: gcovr not found. Install it into the west pipx venv or export GCOVR_BIN."
  exit 2
fi

cd "${ROOT_DIR}"

RUN_LOG="${OUT_DIR}/native_sim_run.log"
BUILD_LOG="${OUT_DIR}/native_sim_build.log"
GCOVR_SUMMARY="${OUT_DIR}/coverage_gcovr_summary.txt"
HTML_DIR="${OUT_DIR}/coverage_html"
HTML_FILE="${HTML_DIR}/index.html"
SUMMARY_LOG="${OUT_DIR}/summary.txt"

log "step=native_sim_64_build_with_coverage"
set +e
west build -p always -b native_sim/native/64 applocation/NeuroLink/neuro_unit/tests/unit \
  -d build/neurolink_unit_ut_native_sim_64_cov -- -DCONFIG_COVERAGE=y \
  2>&1 | tee "${BUILD_LOG}"
BUILD_RC=${PIPESTATUS[0]}
set -e

if [[ ${BUILD_RC} -ne 0 ]]; then
  {
    echo "result=FAIL"
    echo "build_rc=${BUILD_RC}"
    echo "run_rc=not_run"
    echo "artifact.build_log=${BUILD_LOG}"
    echo "artifact.run_log=${RUN_LOG}"
    echo "artifact.coverage_summary=${GCOVR_SUMMARY}"
    echo "artifact.coverage_html=${HTML_FILE}"
  } >"${SUMMARY_LOG}"

  cat "${SUMMARY_LOG}"
  exit 1
fi

if [[ ! -x "${EXE_PATH}" ]]; then
  log "ERROR: coverage executable not found at ${EXE_PATH}"
  exit 2
fi

log "step=native_sim_64_run_with_coverage"
RUN_TIMEOUT_SEC="${RUN_TIMEOUT_SEC:-120}"
set +e
timeout "${RUN_TIMEOUT_SEC}" "${EXE_PATH}" 2>&1 | tee "${RUN_LOG}"
RUN_RC=${PIPESTATUS[0]}
set -e

RESULT="FAIL"
if grep -Eq "PROJECT EXECUTION SUCCESSFUL|TESTSUITE SUMMARY END|SUITE PASS" "${RUN_LOG}" && \
   ! grep -Eq "SUITE FAIL|FAIL -|PROJECT EXECUTION FAILED|ZEPHYR FATAL ERROR|Assertion failed|ERROR:" "${RUN_LOG}"; then
  RESULT="PASS"
fi

mkdir -p "${HTML_DIR}"

log "step=gcovr_capture"
"${GCOVR_BIN}" -r "${ROOT_DIR}" "${BUILD_DIR}" \
  --filter "${ROOT_DIR}/applocation/NeuroLink/neuro_unit/src/" \
  --txt-summary --txt-metric branch >"${GCOVR_SUMMARY}"
"${GCOVR_BIN}" -r "${ROOT_DIR}" "${BUILD_DIR}" \
  --filter "${ROOT_DIR}/applocation/NeuroLink/neuro_unit/src/" \
  --html-details "${HTML_FILE}" --html-title "Neuro Unit Module UT Coverage" \
  --txt-metric branch >/dev/null

{
  echo "result=${RESULT}"
  echo "build_rc=${BUILD_RC}"
  echo "run_rc=${RUN_RC}"
  echo "run_timeout_sec=${RUN_TIMEOUT_SEC}"
  echo "artifact.build_log=${BUILD_LOG}"
  echo "artifact.run_log=${RUN_LOG}"
  echo "artifact.coverage_summary=${GCOVR_SUMMARY}"
  echo "artifact.coverage_html=${HTML_FILE}"
  extract_lcov_metrics "${GCOVR_SUMMARY}" | sed 's/^/metric./'
} >"${SUMMARY_LOG}"

cat "${SUMMARY_LOG}"

if [[ "${RESULT}" != "PASS" ]]; then
  exit 1
fi