#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/setup_neurolink_env.sh"
CLI_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/neuro_cli/src/neuro_cli.py"
ROUTER_SCRIPT="${NEUROLINK_ROUTER_SCRIPT:-${ROOT_DIR}/applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh}"
BUILD_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/build_neurolink.sh"
CLI_REQUIREMENTS="${ROOT_DIR}/applocation/NeuroLink/neuro_cli/requirements.txt"
NODE="unit-01"
ARTIFACT_FILE="build/neurolink_unit_app/neuro_unit_app.llext"
DEFAULT_ARTIFACT_FILE="build/neurolink_unit_app/neuro_unit_app.llext"
ROUTER_PORT=7447
ROUTER_LISTEN=""
AUTO_START_ROUTER=0
INSTALL_MISSING_CLI_DEPS=0
REQUIRE_SERIAL=0
OUTPUT_FORMAT="text"
ROUTER_DEBUG=0
ROUTER_RUST_LOG=""
ROUTER_START_WAIT_SEC="${NEUROLINK_ROUTER_START_WAIT_SEC:-5}"

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/preflight_neurolink_linux.sh [options]

Options:
  --node <node>                    Target NeuroLink node id
  --artifact-file <path>           Local llext file required for smoke
  --router-port <port>             Expected zenoh router TCP port (default: 7447)
  --router-listen <endpoint>       Listen endpoint used when auto-starting router
  --auto-start-router              Start zenohd in background when router port is not listening
  --router-debug                   Start auto-launched router in debug mode
  --router-rust-log <level>        Explicit RUST_LOG for auto-launched router
  --install-missing-cli-deps       Install tracked Neuro CLI Python dependencies before checks
  --require-serial                 Fail if no /dev/ttyACM* or /dev/ttyUSB* device is present
  --output <text|json>             Output format (default: text)
EOF
}

serial_devices_json() {
  local first=1
  local device

  printf '['
  for device in "$@"; do
    if [[ ${first} -eq 0 ]]; then
      printf ','
    fi
    python3 - <<'PY' "$device"
import json
import sys
print(json.dumps(sys.argv[1]), end='')
PY
    first=0
  done
  printf ']'
}

emit_result() {
  local status="$1"
  local ready="$2"
  local detail="$3"
  local router_listening="$4"
  local serial_present="$5"
  local artifact_present="$6"
  local query_rc="$7"
  local query_status="$8"
  local router_started="$9"
  local router_debug="${10}"
  local router_rust_log="${11}"
  shift 11
  local serial_devices=("$@")

  if [[ "${OUTPUT_FORMAT}" == "json" ]]; then
    python3 - <<'PY' \
      "$status" "$ready" "$detail" "$NODE" "$ARTIFACT_FILE" "$router_listening" \
      "$ROUTER_PORT" "$serial_present" "$artifact_present" "$query_rc" "$query_status" \
      "$router_started" "$router_debug" "$router_rust_log" \
      "$(serial_devices_json "${serial_devices[@]}")"
import json
import sys

print(json.dumps({
    "status": sys.argv[1],
    "ready": sys.argv[2] == "1",
    "detail": sys.argv[3],
    "node": sys.argv[4],
    "artifact_file": sys.argv[5],
    "router": {
        "listening": sys.argv[6] == "1",
        "port": int(sys.argv[7]),
        "auto_started": sys.argv[12] == "1",
        "debug": sys.argv[13] == "1",
        "rust_log": sys.argv[14],
    },
    "serial": {
        "present": sys.argv[8] == "1",
        "devices": json.loads(sys.argv[15]),
    },
    "artifact_present": sys.argv[9] == "1",
    "query": {
        "rc": int(sys.argv[10]),
      "status": sys.argv[11],
    },
}, indent=2, ensure_ascii=False))
PY
    return
  fi

  echo "status=${status}"
  echo "ready=${ready}"
  echo "detail=${detail}"
  echo "node=${NODE}"
  echo "artifact_file=${ARTIFACT_FILE}"
  echo "artifact_present=${artifact_present}"
  echo "router_port=${ROUTER_PORT}"
  echo "router_listening=${router_listening}"
  echo "router_auto_started=${router_started}"
  echo "router_debug=${router_debug}"
  echo "router_rust_log=${router_rust_log}"
  echo "serial_present=${serial_present}"
  if [[ ${#serial_devices[@]} -gt 0 ]]; then
    printf 'serial_devices=%s\n' "${serial_devices[*]}"
  fi
  echo "query_rc=${query_rc}"
  echo "query_status=${query_status}"
}

router_is_listening() {
  command -v ss >/dev/null 2>&1 || return 1
  ss -ltnp 2>/dev/null | grep -F ":${ROUTER_PORT}" >/dev/null 2>&1
}

wait_for_router_listening() {
  local attempt

  for attempt in $(seq 1 "${ROUTER_START_WAIT_SEC}"); do
    if router_is_listening; then
      return 0
    fi
    sleep 1
  done

  return 1
}

build_artifact_with_edk_external_app() {
  [[ -f "${BUILD_SCRIPT}" ]] || {
    return 2
  }

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

collect_serial_devices() {
  local devices=()
  local candidate

  for candidate in /dev/ttyACM* /dev/ttyUSB*; do
    if [[ -e "${candidate}" ]]; then
      devices+=("${candidate}")
    fi
  done

  [[ ${#devices[@]} -gt 0 ]] || return 0
  printf '%s\n' "${devices[@]}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --node)
      NODE="$2"
      shift 2
      ;;
    --artifact-file)
      ARTIFACT_FILE="$2"
      shift 2
      ;;
    --router-port)
      ROUTER_PORT="$2"
      shift 2
      ;;
    --router-listen)
      ROUTER_LISTEN="$2"
      shift 2
      ;;
    --auto-start-router)
      AUTO_START_ROUTER=1
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
    --install-missing-cli-deps)
      INSTALL_MISSING_CLI_DEPS=1
      shift
      ;;
    --require-serial)
      REQUIRE_SERIAL=1
      shift
      ;;
    --output)
      OUTPUT_FORMAT="$2"
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

case "${OUTPUT_FORMAT}" in
  text|json)
    ;;
  *)
    echo "invalid output format '${OUTPUT_FORMAT}': use text or json" >&2
    exit 2
    ;;
esac

if [[ -z "${ROUTER_LISTEN}" ]]; then
  ROUTER_LISTEN="tcp/0.0.0.0:${ROUTER_PORT}"
fi

[[ -f "${ENV_SCRIPT}" ]] || {
  echo "setup script not found at ${ENV_SCRIPT}" >&2
  exit 2
}

[[ -f "${CLI_SCRIPT}" ]] || {
  echo "neuro_cli.py not found at ${CLI_SCRIPT}" >&2
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

artifact_present=0
router_listening=0
serial_present=0
router_started=0
query_rc=0
query_status="not_run"
query_output=""
mapfile -t serial_devices < <(collect_serial_devices)

if artifact_is_valid_llext_file "${ARTIFACT_FILE}"; then
  artifact_present=1
fi

if [[ ${#serial_devices[@]} -gt 0 ]]; then
  serial_present=1
fi

python3 -c 'import zenoh' >/dev/null 2>&1 || {
  emit_result "cli_dependency_missing" 0 \
    "python zenoh module is unavailable; install ${CLI_REQUIREMENTS} first" \
    "${router_listening}" "${serial_present}" "${artifact_present}" \
    "${query_rc}" "${query_status}" "${router_started}" \
    "${ROUTER_DEBUG}" "${ROUTER_RUST_LOG:-<unset>}" "${serial_devices[@]}"
  exit 1
}

if [[ ${artifact_present} -eq 0 ]]; then
  if [[ "${ARTIFACT_FILE}" == "${DEFAULT_ARTIFACT_FILE}" ]]; then
    set +e
    build_artifact_with_edk_external_app >/dev/null 2>&1
    build_rc=$?
    set -e

    if [[ ${build_rc} -eq 0 ]] && artifact_is_valid_llext_file "${ARTIFACT_FILE}"; then
      artifact_present=1
    fi
  fi

  if [[ ${artifact_present} -eq 0 ]]; then
    artifact_hint="build failed or artifact is missing, empty, or not an ELF llext"
    if [[ "${ARTIFACT_FILE}" != "${DEFAULT_ARTIFACT_FILE}" ]]; then
      artifact_hint="artifact missing, empty, or not an ELF llext at custom path"
    fi

    emit_result "artifact_invalid" 0 \
      "${artifact_hint}; build default artifact with build_neurolink.sh --preset unit-app (EDK external app) or provide --artifact-file" \
      "${router_listening}" "${serial_present}" "${artifact_present}" \
      "${query_rc}" "${query_status}" "${router_started}" \
      "${ROUTER_DEBUG}" "${ROUTER_RUST_LOG:-<unset>}" "${serial_devices[@]}"
    exit 1
  fi
fi

if router_is_listening; then
  router_listening=1
elif [[ ${AUTO_START_ROUTER} -eq 1 ]]; then
  [[ -f "${ROUTER_SCRIPT}" ]] || {
    emit_result "router_helper_missing" 0 \
      "router helper not found at ${ROUTER_SCRIPT}" \
      "${router_listening}" "${serial_present}" "${artifact_present}" \
      "${query_rc}" "${query_status}" "${router_started}" \
      "${ROUTER_DEBUG}" "${ROUTER_RUST_LOG:-<unset>}" "${serial_devices[@]}"
    exit 1
  }
  router_cmd=(
    bash "${ROUTER_SCRIPT}"
    --listen "${ROUTER_LISTEN}"
    --rest-http-port none
    --background
  )
  if [[ ${ROUTER_DEBUG} -eq 1 ]]; then
    router_cmd+=(--debug)
  fi
  if [[ -n "${ROUTER_RUST_LOG}" ]]; then
    router_cmd+=(--rust-log "${ROUTER_RUST_LOG}")
  fi
  set +e
  router_launch_output="$(${router_cmd[@]} 2>&1)"
  router_launch_rc=$?
  set -e
  if [[ ${router_launch_rc} -ne 0 ]]; then
    emit_result "router_failed_to_start" 0 \
      "router helper failed: ${router_launch_output//$'\n'/; }" \
      "${router_listening}" "${serial_present}" "${artifact_present}" \
      "${query_rc}" "${query_status}" "${router_started}" \
      "${ROUTER_DEBUG}" "${ROUTER_RUST_LOG:-<unset>}" "${serial_devices[@]}"
    exit 1
  fi
  if wait_for_router_listening; then
    router_listening=1
    router_started=1
  else
    emit_result "router_failed_to_start" 0 \
      "router launch returned success but tcp port ${ROUTER_PORT} never became ready" \
      "${router_listening}" "${serial_present}" "${artifact_present}" \
      "${query_rc}" "${query_status}" "${router_started}" \
      "${ROUTER_DEBUG}" "${ROUTER_RUST_LOG:-<unset>}" "${serial_devices[@]}"
    exit 1
  fi
fi

if [[ ${router_listening} -eq 0 ]]; then
  emit_result "router_not_listening" 0 \
    "zenohd is not listening on tcp port ${ROUTER_PORT}" \
    "${router_listening}" "${serial_present}" "${artifact_present}" \
    "${query_rc}" "${query_status}" "${router_started}" \
    "${ROUTER_DEBUG}" "${ROUTER_RUST_LOG:-<unset>}" "${serial_devices[@]}"
  exit 1
fi

if [[ ${REQUIRE_SERIAL} -eq 1 ]] && [[ ${serial_present} -eq 0 ]]; then
  emit_result "serial_device_missing" 0 \
    "no /dev/ttyACM* or /dev/ttyUSB* device is visible on this Linux host" \
    "${router_listening}" "${serial_present}" "${artifact_present}" \
    "${query_rc}" "${query_status}" "${router_started}" \
    "${ROUTER_DEBUG}" "${ROUTER_RUST_LOG:-<unset>}" "${serial_devices[@]}"
  exit 1
fi

set +e
query_output="$(python3 "${CLI_SCRIPT}" --output json --node "${NODE}" query device 2>&1)"
query_rc=$?
set -e

if [[ ${query_rc} -eq 0 ]]; then
  query_status="ok"
  emit_result "ready" 1 \
    "query_device succeeded" \
    "${router_listening}" "${serial_present}" "${artifact_present}" \
    "${query_rc}" "${query_status}" "${router_started}" \
    "${ROUTER_DEBUG}" "${ROUTER_RUST_LOG:-<unset>}" "${serial_devices[@]}"
  exit 0
fi

if grep -F '"status": "no_reply"' <<<"${query_output}" >/dev/null 2>&1; then
  query_status="no_reply"
  if [[ ${serial_present} -eq 0 ]]; then
    emit_result "no_reply_board_not_attached" 0 \
      "router is listening but no serial device is attached, so the node is likely offline" \
      "${router_listening}" "${serial_present}" "${artifact_present}" \
      "${query_rc}" "${query_status}" "${router_started}" \
      "${ROUTER_DEBUG}" "${ROUTER_RUST_LOG:-<unset>}" "${serial_devices[@]}"
  else
    emit_result "no_reply_board_unreachable" 0 \
      "router is listening and a serial device exists, but query_device still returned no_reply; check UART for network readiness or run prepare_dnesp32s3b_wsl.sh with Wi-Fi credentials" \
      "${router_listening}" "${serial_present}" "${artifact_present}" \
      "${query_rc}" "${query_status}" "${router_started}" \
      "${ROUTER_DEBUG}" "${ROUTER_RUST_LOG:-<unset>}" "${serial_devices[@]}"
  fi
  exit 1
fi

query_status="query_failed"
emit_result "query_failed" 0 \
  "query_device failed for a reason other than no_reply" \
  "${router_listening}" "${serial_present}" "${artifact_present}" \
  "${query_rc}" "${query_status}" "${router_started}" \
  "${ROUTER_DEBUG}" "${ROUTER_RUST_LOG:-<unset>}" "${serial_devices[@]}"
exit 1