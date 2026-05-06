#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/setup_neurolink_env.sh"
PREFLIGHT_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/preflight_neurolink_linux.sh"
CLI_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/neuro_cli/src/neuro_cli.py"
BUILD_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/build_neurolink.sh"
CLI_REQUIREMENTS="${ROOT_DIR}/applocation/NeuroLink/neuro_cli/requirements.txt"
NODE="unit-01"
APP_ID="neuro_unit_app"
ARTIFACT_FILE="build/neurolink_unit_app/neuro_unit_app.llext"
DEFAULT_ARTIFACT_FILE="build/neurolink_unit_app/neuro_unit_app.llext"
ACTIVATE_LEASE_ID="lease-act-017b-001"
ACTIVATE_LEASE_RESOURCE="update/app/neuro_unit_app/activate"
LEASE_TTL_MS=120000
EVENTS_DURATION_SEC=20
OUTPUT_DIR="applocation/NeuroLink/smoke-evidence"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"
INSTALL_MISSING_CLI_DEPS=0
SKIP_PREFLIGHT=0
PREFLIGHT_REQUIRE_SERIAL=1
ROUTER_DEBUG=0
ROUTER_RUST_LOG=""
FAILED_STEP="-"
FAILURE_EXIT_CODE=0

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/smoke_neurolink_linux.sh [options]

Options:
  --node <node>                    Target NeuroLink node id
  --app-id <app-id>                Application id for deploy flow
  --artifact-file <path>           Local llext file served by neuro_cli.py
  --lease-id <lease-id>            Lease id used for activate
  --lease-resource <resource>      Protected resource for lease acquire
  --lease-ttl-ms <ttl>             Lease TTL in milliseconds
  --events-duration-sec <seconds>  Event monitor duration
  --output-dir <path>              Output directory for NDJSON evidence
  --install-missing-cli-deps       Install tracked Neuro CLI Python dependencies before smoke
  --skip-preflight                 Skip Linux board/router preflight
  --no-preflight-require-serial    Allow preflight to succeed without a local serial device
  --router-debug                   Enable debug mode for auto-started zenoh router
  --router-rust-log <level>        Explicit RUST_LOG for auto-started zenoh router
EOF
}

append_evidence() {
  local step="$1"
  local exit_code="$2"
  local command_line="$3"
  local output_text="$4"

  STEP="${step}" \
  EXIT_CODE="${exit_code}" \
  COMMAND_LINE="${command_line}" \
  OUTPUT_TEXT="${output_text}" \
  python3 - <<'PY' >>"${EVIDENCE_FILE}"
import json
import os
from datetime import datetime, timezone

print(
    json.dumps(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": os.environ["STEP"],
            "exit_code": int(os.environ["EXIT_CODE"]),
            "command_line": os.environ["COMMAND_LINE"],
            "output": os.environ["OUTPUT_TEXT"],
        },
        ensure_ascii=False,
    )
)
PY
}

build_artifact_with_edk_external_app() {
  [[ -f "${BUILD_SCRIPT}" ]] || return 2
  bash "${BUILD_SCRIPT}" --preset unit-app --no-c-style-check
}

artifact_is_nonempty_file() {
  [[ -f "$1" ]] && [[ -s "$1" ]]
}

artifact_has_valid_elf_header() {
  local header
  local elf_class
  local elf_version

  [[ -f "$1" ]] || return 1
  header="$(LC_ALL=C od -An -tx1 -N6 "$1" 2>/dev/null | tr -d ' \n')"
  [[ ${#header} -eq 12 ]] || return 1
  [[ "${header:0:8}" == "7f454c46" ]] || return 1

  elf_class="${header:8:2}"
  elf_version="${header:10:2}"
  [[ "${elf_class}" == "01" || "${elf_class}" == "02" ]] || return 1
  [[ "${elf_version}" == "01" ]]
}

artifact_is_valid_llext_file() {
  artifact_is_nonempty_file "$1" && artifact_has_valid_elf_header "$1"
}

output_has_error_reply() {
  local output_text="$1"

  OUTPUT_TEXT="${output_text}" python3 - <<'PY'
import json
import os
import sys

text = os.environ["OUTPUT_TEXT"]
start = text.find("{\n")
if start < 0:
  start = text.find("{")
if start < 0:
  raise SystemExit(0)

try:
  payload = json.loads(text[start:])
except json.JSONDecodeError:
  raise SystemExit(0)

if not payload.get("ok", True):
  raise SystemExit(1)

for reply in payload.get("replies", []):
  if not reply.get("ok", True):
    raise SystemExit(1)
  reply_payload = reply.get("payload")
  if isinstance(reply_payload, dict):
    reply_status = str(reply_payload.get("status", ""))
    if reply_status in {
      "error",
      "not_implemented",
      "invalid_input",
      "query_failed",
      "no_reply",
      "error_reply",
    }:
      raise SystemExit(1)

raise SystemExit(0)
PY
}

invoke_step() {
  local step="$1"
  shift

  local cmd=(python3 "${CLI_SCRIPT}" --output json --node "${NODE}" "$@")
  local command_line
  local output
  local rc

  command_line="$(printf '%q ' "${cmd[@]}")"
  echo "[SMOKE-LINUX] step=${step}"

  set +e
  output="$(${cmd[@]} 2>&1)"
  rc=$?
  set -e

  if [[ ${rc} -eq 0 ]] && ! output_has_error_reply "${output}"; then
    rc=1
  fi

  append_evidence "${step}" "${rc}" "${command_line}" "${output}"
  printf '%s\n' "${output}"
  return "${rc}"
}

run_smoke_step() {
  local step="$1"
  local rc
  shift

  set +e
  invoke_step "${step}" "$@"
  rc=$?
  set -e

  if [[ ${rc} -eq 0 ]]; then
    return 0
  fi

  FAILURE_EXIT_CODE=${rc}
  FAILED_STEP="${step}"
  RESULT="FAIL"
  return 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --node)
      NODE="$2"
      shift 2
      ;;
    --app-id)
      APP_ID="$2"
      shift 2
      ;;
    --artifact-file)
      ARTIFACT_FILE="$2"
      shift 2
      ;;
    --lease-id)
      ACTIVATE_LEASE_ID="$2"
      shift 2
      ;;
    --lease-resource)
      ACTIVATE_LEASE_RESOURCE="$2"
      shift 2
      ;;
    --lease-ttl-ms)
      LEASE_TTL_MS="$2"
      shift 2
      ;;
    --events-duration-sec)
      EVENTS_DURATION_SEC="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --install-missing-cli-deps)
      INSTALL_MISSING_CLI_DEPS=1
      shift
      ;;
    --skip-preflight)
      SKIP_PREFLIGHT=1
      shift
      ;;
    --no-preflight-require-serial)
      PREFLIGHT_REQUIRE_SERIAL=0
      shift
      ;;
    --router-debug)
      ROUTER_DEBUG=1
      shift
      ;;
    --router-rust-log)
      ROUTER_RUST_LOG="$2"
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
  echo "setup script not found at ${ENV_SCRIPT}" >&2
  exit 2
}

[[ -f "${CLI_SCRIPT}" ]] || {
  echo "neuro_cli.py not found at ${CLI_SCRIPT}" >&2
  exit 2
}

[[ -f "${PREFLIGHT_SCRIPT}" ]] || {
  echo "preflight script not found at ${PREFLIGHT_SCRIPT}" >&2
  exit 2
}

[[ -f "${BUILD_SCRIPT}" ]] || {
  echo "build script not found at ${BUILD_SCRIPT}" >&2
  exit 2
}

# shellcheck disable=SC1090
if [[ ${INSTALL_MISSING_CLI_DEPS} -eq 1 ]]; then
  source "${ENV_SCRIPT}" --activate --strict --install-unit-cli-deps
else
  source "${ENV_SCRIPT}" --activate --strict
fi

cd "${ROOT_DIR}"

if [[ "${ARTIFACT_FILE}" == "${DEFAULT_ARTIFACT_FILE}" ]]; then
  build_rc=1
  build_output=""
  set +e
  build_output="$(build_artifact_with_edk_external_app 2>&1)"
  build_rc=$?
  set -e

  if [[ ${build_rc} -ne 0 ]] || ! artifact_is_valid_llext_file "${ARTIFACT_FILE}"; then
    echo "artifact file missing, empty, or not an ELF llext: ${ARTIFACT_FILE}" >&2
    if [[ -n "${build_output}" ]]; then
      echo "auto-build output:" >&2
      printf '%s\n' "${build_output}" >&2
    fi
    echo "build default artifact with EDK external app flow: bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check" >&2
    echo "or provide --artifact-file pointing to an existing llext" >&2
    exit 2
  fi
elif ! artifact_is_valid_llext_file "${ARTIFACT_FILE}"; then
  echo "artifact file missing, empty, or not an ELF llext: ${ARTIFACT_FILE}" >&2
  echo "build default artifact with EDK external app flow: bash applocation/NeuroLink/scripts/build_neurolink.sh --preset unit-app --no-c-style-check" >&2
  echo "or provide --artifact-file pointing to an existing llext" >&2
  exit 2
fi

python3 -c 'import zenoh' >/dev/null 2>&1 || {
  echo "python zenoh module is missing in the active environment" >&2
  echo "rerun with --install-missing-cli-deps or install manually before retrying" >&2
  if [[ -f "${CLI_REQUIREMENTS}" ]]; then
    echo "install Neuro CLI dependencies first: python3 -m pip install -r applocation/NeuroLink/neuro_cli/requirements.txt" >&2
  else
    echo "install the validated package first: python3 -m pip install eclipse-zenoh==1.9.0" >&2
  fi
  exit 2
}

if [[ ${SKIP_PREFLIGHT} -eq 0 ]]; then
  preflight_cmd=(
    bash "${PREFLIGHT_SCRIPT}"
    --node "${NODE}"
    --artifact-file "${ARTIFACT_FILE}"
    --auto-start-router
    --output text
  )

  if [[ ${PREFLIGHT_REQUIRE_SERIAL} -eq 1 ]]; then
    preflight_cmd+=(--require-serial)
  fi

  if [[ ${INSTALL_MISSING_CLI_DEPS} -eq 1 ]]; then
    preflight_cmd+=(--install-missing-cli-deps)
  fi
  if [[ ${ROUTER_DEBUG} -eq 1 ]]; then
    preflight_cmd+=(--router-debug)
  fi
  if [[ -n "${ROUTER_RUST_LOG}" ]]; then
    preflight_cmd+=(--router-rust-log "${ROUTER_RUST_LOG}")
  fi

  echo "[SMOKE-LINUX] step=preflight"
  set +e
  preflight_output="$(${preflight_cmd[@]} 2>&1)"
  preflight_rc=$?
  set -e
  printf '%s\n' "${preflight_output}"
  if [[ ${preflight_rc} -ne 0 ]]; then
    echo "smoke preflight failed; rerun after correcting the reported readiness issue" >&2
    exit 2
  fi
fi

if [[ ! "${OUTPUT_DIR}" = /* ]]; then
  OUTPUT_DIR="${ROOT_DIR}/${OUTPUT_DIR}"
fi

mkdir -p "${OUTPUT_DIR}"
EVIDENCE_FILE="${OUTPUT_DIR}/SMOKE-017B-LINUX-001-${TIMESTAMP}.ndjson"
SUMMARY_FILE="${OUTPUT_DIR}/SMOKE-017B-LINUX-001-${TIMESTAMP}.summary.txt"

RESULT="PASS"

if ! run_smoke_step "query_device" query device; then
  :
fi

if [[ "${RESULT}" == "PASS" ]] && ! run_smoke_step \
  "lease_acquire_activate" \
  lease acquire \
  --resource "${ACTIVATE_LEASE_RESOURCE}" \
  --lease-id "${ACTIVATE_LEASE_ID}" \
  --ttl-ms "${LEASE_TTL_MS}"; then
  :
fi

if [[ "${RESULT}" == "PASS" ]] && ! run_smoke_step \
  "deploy_prepare" \
  deploy prepare \
  --app-id "${APP_ID}" \
  --file "${ARTIFACT_FILE}"; then
  :
fi

if [[ "${RESULT}" == "PASS" ]] && ! run_smoke_step \
  "deploy_verify" \
  deploy verify \
  --app-id "${APP_ID}"; then
  :
fi

if [[ "${RESULT}" == "PASS" ]] && ! run_smoke_step \
  "deploy_activate" \
  deploy activate \
  --app-id "${APP_ID}" \
  --lease-id "${ACTIVATE_LEASE_ID}" \
  --start-args "mode=demo,profile=release"; then
  :
fi

if [[ "${RESULT}" == "PASS" ]] && ! run_smoke_step \
  "monitor_events" \
  monitor events \
  --duration "${EVENTS_DURATION_SEC}"; then
  :
fi

{
  echo "result=${RESULT}"
  echo "node=${NODE}"
  echo "app_id=${APP_ID}"
  echo "artifact_file=${ARTIFACT_FILE}"
  echo "lease_id=${ACTIVATE_LEASE_ID}"
  echo "failed_step=${FAILED_STEP}"
  echo "failure_exit_code=${FAILURE_EXIT_CODE}"
  echo "evidence_file=${EVIDENCE_FILE}"
} >"${SUMMARY_FILE}"

cat "${SUMMARY_FILE}"

if [[ "${RESULT}" != "PASS" ]]; then
  exit 1
fi
