#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/setup_neurolink_env.sh"
CLI_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/neuro_cli/src/neuro_cli.py"
CORE_DIR="${ROOT_DIR}/applocation/NeuroLink"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
NODE="unit-01"
APP_ID="neuro_unit_app"
MODE="state-online"
DB_PATH="/tmp/neurolink-unit-live-probe.db"
LISTENER_DURATION=45
MAX_EVENTS=4
READY_TIMEOUT_SEC=20
EXPECTED_APP_ECHO=""
TRIGGER_EVERY=1
INVOKE_COUNT=2
ARTIFACT_FILE="build/neurolink_unit_app/neuro_unit_app.llext"
LEASE_ID=""
INSTALL_MISSING_CLI_DEPS=0
READY_FILE=""
LISTENER_OUTPUT_FILE=""
TRIGGER_OUTPUT_FILE=""
LISTENER_PID=""
LEASE_HELD=0

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/run_unit_live_event_probe.sh [options]

Options:
  --mode <callback|state-online|update-activate>
                                Probe mode to trigger once the listener is ready
  --node <node>                  Target NeuroLink node id (default: unit-01)
  --app-id <app-id>              Application id for trigger flow (default: neuro_unit_app)
  --db <path>                    SQLite db used by live-event-smoke
  --duration <seconds>           Listener duration in seconds (default: 45)
  --max-events <count>           Bounded live ingest event count (default: 4)
  --ready-timeout <seconds>      Max wait for ready-file before failing (default: 20)
  --expected-app-echo <value>    Expected echo for callback mode
  --trigger-every <n>            app-callback-smoke trigger interval (default: 1)
  --invoke-count <n>             app-callback-smoke invoke count (default: 2)
  --artifact-file <path>         Artifact path for update-activate mode
  --lease-id <lease-id>          Explicit lease id for state/update modes
  --install-missing-cli-deps     Install tracked Neuro CLI Python dependencies first
EOF
}

cleanup() {
  if [[ ${LEASE_HELD} -eq 1 && -n "${LEASE_ID}" ]]; then
    "${PYTHON_BIN}" "${CLI_SCRIPT}" --output json --node "${NODE}" lease release --lease-id "${LEASE_ID}" >/dev/null 2>&1 || true
  fi

  if [[ -n "${LISTENER_PID}" ]] && kill -0 "${LISTENER_PID}" >/dev/null 2>&1; then
    kill "${LISTENER_PID}" >/dev/null 2>&1 || true
    wait "${LISTENER_PID}" >/dev/null 2>&1 || true
  fi

  [[ -n "${READY_FILE}" ]] && rm -f "${READY_FILE}" || true
}

run_cli() {
  "${PYTHON_BIN}" "${CLI_SCRIPT}" --output json --node "${NODE}" "$@"
}

wait_for_ready() {
  local deadline=$((SECONDS + READY_TIMEOUT_SEC))

  while (( SECONDS < deadline )); do
    if [[ -f "${READY_FILE}" ]]; then
      return 0
    fi
    sleep 1
  done

  echo "listener ready-file was not written within ${READY_TIMEOUT_SEC}s" >&2
  return 1
}

run_listener() {
  local cmd=(
    "${PYTHON_BIN}" -m neurolink_core.cli live-event-smoke
    --event-source unit
    --db "${DB_PATH}"
    --duration "${LISTENER_DURATION}"
    --max-events "${MAX_EVENTS}"
    --ready-file "${READY_FILE}"
  )

  (
    cd "${CORE_DIR}"
    "${cmd[@]}"
  ) >"${LISTENER_OUTPUT_FILE}" 2>&1 &
  LISTENER_PID=$!
}

trigger_callback() {
  local cmd=(app-callback-smoke --app-id "${APP_ID}" --trigger-every "${TRIGGER_EVERY}" --invoke-count "${INVOKE_COUNT}")

  if [[ -n "${EXPECTED_APP_ECHO}" ]]; then
    cmd+=(--expected-app-echo "${EXPECTED_APP_ECHO}")
  fi

  run_cli "${cmd[@]}"
}

trigger_state_online() {
  LEASE_ID="${LEASE_ID:-l-state-evt-001}"
  run_cli lease acquire --resource "app/${APP_ID}/control" --lease-id "${LEASE_ID}"
  LEASE_HELD=1
  run_cli app stop --app-id "${APP_ID}" --lease-id "${LEASE_ID}"
  run_cli app start --app-id "${APP_ID}" --lease-id "${LEASE_ID}"
  run_cli lease release --lease-id "${LEASE_ID}"
  LEASE_HELD=0
}

trigger_update_activate() {
  LEASE_ID="${LEASE_ID:-l-update-evt-001}"
  run_cli deploy prepare --app-id "${APP_ID}" --file "${ARTIFACT_FILE}"
  run_cli deploy verify --app-id "${APP_ID}"
  run_cli lease acquire --resource "update/app/${APP_ID}/activate" --lease-id "${LEASE_ID}"
  LEASE_HELD=1
  run_cli deploy activate --app-id "${APP_ID}" --lease-id "${LEASE_ID}"
  run_cli lease release --lease-id "${LEASE_ID}"
  LEASE_HELD=0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --node)
      NODE="$2"
      shift 2
      ;;
    --app-id)
      APP_ID="$2"
      shift 2
      ;;
    --db)
      DB_PATH="$2"
      shift 2
      ;;
    --duration)
      LISTENER_DURATION="$2"
      shift 2
      ;;
    --max-events)
      MAX_EVENTS="$2"
      shift 2
      ;;
    --ready-timeout)
      READY_TIMEOUT_SEC="$2"
      shift 2
      ;;
    --expected-app-echo)
      EXPECTED_APP_ECHO="$2"
      shift 2
      ;;
    --trigger-every)
      TRIGGER_EVERY="$2"
      shift 2
      ;;
    --invoke-count)
      INVOKE_COUNT="$2"
      shift 2
      ;;
    --artifact-file)
      ARTIFACT_FILE="$2"
      shift 2
      ;;
    --lease-id)
      LEASE_ID="$2"
      shift 2
      ;;
    --install-missing-cli-deps)
      INSTALL_MISSING_CLI_DEPS=1
      shift
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

case "${MODE}" in
  callback|state-online|update-activate)
    ;;
  *)
    echo "unsupported mode: ${MODE}" >&2
    usage >&2
    exit 2
    ;;
esac

[[ -x "${PYTHON_BIN}" ]] || {
  echo "python interpreter not found at ${PYTHON_BIN}" >&2
  exit 2
}

[[ -f "${CLI_SCRIPT}" ]] || {
  echo "neuro_cli.py not found at ${CLI_SCRIPT}" >&2
  exit 2
}

trap cleanup EXIT

if [[ ${INSTALL_MISSING_CLI_DEPS} -eq 1 ]]; then
  source "${ENV_SCRIPT}" --activate --strict --install-unit-cli-deps
fi

READY_FILE="$(mktemp /tmp/neurolink-unit-live-ready.XXXXXX)"
rm -f "${READY_FILE}"
LISTENER_OUTPUT_FILE="$(mktemp /tmp/neurolink-unit-listener.XXXXXX)"
TRIGGER_OUTPUT_FILE="$(mktemp /tmp/neurolink-unit-trigger.XXXXXX)"
rm -f "${DB_PATH}"

run_listener
wait_for_ready

set +e
case "${MODE}" in
  callback)
    trigger_callback >"${TRIGGER_OUTPUT_FILE}" 2>&1
    TRIGGER_RC=$?
    ;;
  state-online)
    trigger_state_online >"${TRIGGER_OUTPUT_FILE}" 2>&1
    TRIGGER_RC=$?
    ;;
  update-activate)
    trigger_update_activate >"${TRIGGER_OUTPUT_FILE}" 2>&1
    TRIGGER_RC=$?
    ;;
esac

wait "${LISTENER_PID}"
LISTENER_RC=$?
set -e

echo "=== listener output ==="
cat "${LISTENER_OUTPUT_FILE}"
echo "=== trigger output ==="
cat "${TRIGGER_OUTPUT_FILE}"

if [[ ${TRIGGER_RC} -ne 0 ]]; then
  exit "${TRIGGER_RC}"
fi

exit "${LISTENER_RC}"