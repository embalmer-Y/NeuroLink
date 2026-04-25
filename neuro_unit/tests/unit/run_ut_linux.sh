#!/usr/bin/env bash
set -euo pipefail

ROOT_DEFAULT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../.." && pwd)"
ROOT_DIR="${1:-$ROOT_DEFAULT}"
ENV_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/setup_neurolink_env.sh"
OUT_BASE="${2:-applocation/NeuroLink/smoke-evidence/ut-runtime}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="${ROOT_DIR}/${OUT_BASE}/${TIMESTAMP}"

mkdir -p "${OUT_DIR}"

log() {
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
}

if [[ ! -f "${ENV_SCRIPT}" ]]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR: setup script not found at ${ENV_SCRIPT}" >&2
  exit 2
fi

# Self-bootstrap so the Linux UT entrypoint is runnable from a fresh shell.
# shellcheck disable=SC1090
source "${ENV_SCRIPT}" --activate --strict

resolve_sdk_dir() {
  local candidates=()
  local candidate

  if [[ -n "${ZEPHYR_SDK_INSTALL_DIR:-}" ]] && [[ -f "${ZEPHYR_SDK_INSTALL_DIR}/cmake/Zephyr-sdkConfig.cmake" ]]; then
    echo "${ZEPHYR_SDK_INSTALL_DIR}"
    return 0
  fi

  for candidate in "${HOME}"/zephyr-sdk-* /opt/zephyr-sdk-*; do
    if [[ -f "${candidate}/cmake/Zephyr-sdkConfig.cmake" ]]; then
      candidates+=("${candidate}")
    fi
  done

  if [[ ${#candidates[@]} -gt 0 ]]; then
    printf '%s\n' "${candidates[@]}" | sort -V | tail -n 1
    return 0
  fi

  return 1
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: missing command '$1'"
    exit 2
  fi
}

log "root_dir=${ROOT_DIR}"
log "out_dir=${OUT_DIR}"

require_cmd west
require_cmd ninja

QEMU_AVAILABLE=1
if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
  QEMU_AVAILABLE=0
  log "WARNING: qemu-system-x86_64 not found; qemu_x86_64 validation will be skipped"
fi

if SDK_DIR="$(resolve_sdk_dir)"; then
  export ZEPHYR_SDK_INSTALL_DIR="${SDK_DIR}"
  log "zephyr_sdk_install_dir=${ZEPHYR_SDK_INSTALL_DIR}"
else
  log "ERROR: Zephyr SDK not found. Set ZEPHYR_SDK_INSTALL_DIR or install SDK with: west sdk install"
  exit 2
fi

cd "${ROOT_DIR}"

TWISTER_LOG="${OUT_DIR}/twister_native_sim.log"
TWISTER_OUT_DIR="${ROOT_DIR}/build/twister/neurolink_unit_ut_native_sim"
QEMU_BUILD_LOG="${OUT_DIR}/qemu_x86_64_build.log"
QEMU_RUN_LOG="${OUT_DIR}/qemu_x86_64_run.log"
SUMMARY_LOG="${OUT_DIR}/summary.txt"

log "step=twister_native_sim_attempt"
mkdir -p "${TWISTER_OUT_DIR}"
set +e
west twister -T applocation/NeuroLink/neuro_unit/tests/unit -p native_sim -v --inline-logs \
  --outdir "${TWISTER_OUT_DIR}" \
  2>&1 | tee "${TWISTER_LOG}"
TWISTER_RC=$?
set -e

QEMU_BUILD_RC="skipped"
QEMU_RUN_RC="skipped"
QEMU_STATUS="skipped_missing_qemu"
RUN_TIMEOUT_SEC="${RUN_TIMEOUT_SEC:-900}"
PASS_PATTERN="PROJECT EXECUTION SUCCESSFUL|TESTSUITE SUMMARY END|SUITE PASS"
FAIL_PATTERN="SUITE FAIL|FAIL -|PROJECT EXECUTION FAILED|ZEPHYR FATAL ERROR|Assertion failed|ERROR:"

if [[ ${QEMU_AVAILABLE} -eq 1 ]]; then
  log "step=qemu_x86_64_build"
  set +e
  west build -p always -b qemu_x86_64 applocation/NeuroLink/neuro_unit/tests/unit \
    -d build/neurolink_unit_ut_qemu_x86_64_linux 2>&1 | tee "${QEMU_BUILD_LOG}"
  QEMU_BUILD_RC=${PIPESTATUS[0]}
  set -e

  if [[ ${QEMU_BUILD_RC} -eq 0 ]]; then
    log "step=qemu_x86_64_run"
    QEMU_RUN_CMD="ninja -C build/neurolink_unit_ut_qemu_x86_64_linux run_qemu"
    set +e
    if command -v script >/dev/null 2>&1; then
      : >"${QEMU_RUN_LOG}"
      script -q -f -e -c "${QEMU_RUN_CMD}" "${QEMU_RUN_LOG}" &
      SCRIPT_PID=$!
      QEMU_RUN_RC=0
      PASS_DETECTED=0
      TIMEOUT_HIT=0
      DEADLINE_EPOCH=$(( $(date +%s) + RUN_TIMEOUT_SEC ))

      while kill -0 "${SCRIPT_PID}" >/dev/null 2>&1; do
        if grep -Eq "${PASS_PATTERN}" "${QEMU_RUN_LOG}" && \
           ! grep -Eq "${FAIL_PATTERN}" "${QEMU_RUN_LOG}"; then
          PASS_DETECTED=1
          pkill -INT -f "qemu-system-x86_64" >/dev/null 2>&1 || true
          break
        fi

        if (( $(date +%s) >= DEADLINE_EPOCH )); then
          TIMEOUT_HIT=1
          pkill -INT -f "qemu-system-x86_64" >/dev/null 2>&1 || true
          break
        fi

        sleep 1
      done

      wait "${SCRIPT_PID}"
      QEMU_RUN_RC=$?

      if [[ ${PASS_DETECTED} -eq 1 ]]; then
        QEMU_RUN_RC=0
      elif [[ ${TIMEOUT_HIT} -eq 1 ]]; then
        QEMU_RUN_RC=124
      fi
    else
      if command -v timeout >/dev/null 2>&1; then
        timeout "${RUN_TIMEOUT_SEC}" ${QEMU_RUN_CMD} 2>&1 | tee "${QEMU_RUN_LOG}"
        QEMU_RUN_RC=${PIPESTATUS[0]}
      else
        ${QEMU_RUN_CMD} 2>&1 | tee "${QEMU_RUN_LOG}"
        QEMU_RUN_RC=${PIPESTATUS[0]}
      fi
    fi
    set -e

    if grep -Eq "${PASS_PATTERN}" "${QEMU_RUN_LOG}" && \
      ! grep -Eq "${FAIL_PATTERN}" "${QEMU_RUN_LOG}" && \
      [[ ${QEMU_RUN_RC} -eq 0 ]]; then
      QEMU_STATUS="passed"
    else
      QEMU_STATUS="failed"
    fi
  else
    QEMU_STATUS="build_failed"
  fi
fi

RESULT="FAIL"
if [[ ${TWISTER_RC} -eq 0 ]]; then
  if [[ "${QEMU_STATUS}" == "skipped_missing_qemu" || "${QEMU_STATUS}" == "passed" ]]; then
    RESULT="PASS"
  fi
fi

{
  echo "result=${RESULT}"
  echo "twister_native_sim_rc=${TWISTER_RC}"
  echo "qemu_status=${QEMU_STATUS}"
  echo "qemu_build_rc=${QEMU_BUILD_RC}"
  echo "qemu_run_rc=${QEMU_RUN_RC}"
  echo "run_timeout_sec=${RUN_TIMEOUT_SEC}"
  echo "artifact.twister_log=${TWISTER_LOG}"
  echo "artifact.qemu_build_log=${QEMU_BUILD_LOG}"
  echo "artifact.qemu_run_log=${QEMU_RUN_LOG}"
} >"${SUMMARY_LOG}"

cat "${SUMMARY_LOG}"

if [[ "${RESULT}" != "PASS" ]]; then
  exit 1
fi
