#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
USER_LOCAL_ZENOHD="${HOME}/.local/zenoh/current/zenohd"
LISTEN_ENDPOINT="tcp/0.0.0.0:7447"
REST_HTTP_PORT="8000"
CONFIG_FILE=""
BACKGROUND=0
OUTPUT_BASE="applocation/NeuroLink/smoke-evidence/zenoh-router"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ZENOHD_BIN=""
ROUTER_DEBUG=0
ROUTER_RUST_LOG=""

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh [options]

Options:
  --listen <endpoint>         Router listen endpoint (default: tcp/0.0.0.0:7447)
  --rest-http-port <value>    REST interface port or 'none' (default: 8000)
  --config <path>             Optional zenohd config file
  --zenohd <path>             Explicit zenohd binary path
  --debug                     Enable verbose router logs (sets RUST_LOG=debug)
  --rust-log <level>          Explicit RUST_LOG value (overrides --debug default)
  --background                Launch zenohd with nohup and return immediately
  --output-base <path>        Evidence-relative output directory base
EOF
}

is_wsl() {
  [[ -n "${WSL_DISTRO_NAME:-}" ]] || grep -qi microsoft /proc/version 2>/dev/null
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --listen)
      LISTEN_ENDPOINT="$2"
      shift 2
      ;;
    --rest-http-port)
      REST_HTTP_PORT="$2"
      shift 2
      ;;
    --config)
      CONFIG_FILE="$2"
      shift 2
      ;;
    --zenohd)
      ZENOHD_BIN="$2"
      shift 2
      ;;
    --debug)
      ROUTER_DEBUG=1
      shift
      ;;
    --rust-log)
      ROUTER_RUST_LOG="$2"
      shift 2
      ;;
    --background)
      BACKGROUND=1
      shift
      ;;
    --output-base)
      OUTPUT_BASE="$2"
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

is_wsl || {
  echo "warning: this router helper is primarily intended for WSL Ubuntu/Debian" >&2
}

if [[ -z "${ZENOHD_BIN}" ]]; then
  if command -v zenohd >/dev/null 2>&1; then
    ZENOHD_BIN="$(command -v zenohd)"
  elif [[ -x "${USER_LOCAL_ZENOHD}" ]]; then
    ZENOHD_BIN="${USER_LOCAL_ZENOHD}"
  else
    echo "zenohd not found; install it first with install_zenoh_router_wsl.sh" >&2
    exit 2
  fi
fi

[[ -x "${ZENOHD_BIN}" ]] || {
  echo "zenohd binary is not executable: ${ZENOHD_BIN}" >&2
  exit 2
}

OUT_DIR="${ROOT_DIR}/${OUTPUT_BASE}/${TIMESTAMP}"
LOG_FILE="${OUT_DIR}/zenohd.log"
PID_FILE="${OUT_DIR}/zenohd.pid"
mkdir -p "${OUT_DIR}"

cmd=("${ZENOHD_BIN}" --listen "${LISTEN_ENDPOINT}" --rest-http-port "${REST_HTTP_PORT}")
if [[ -n "${CONFIG_FILE}" ]]; then
  cmd+=(--config "${CONFIG_FILE}")
fi

if [[ ${ROUTER_DEBUG} -eq 1 ]] && [[ -z "${ROUTER_RUST_LOG}" ]]; then
  ROUTER_RUST_LOG="debug"
fi

if [[ -z "${ROUTER_RUST_LOG}" ]] && [[ -n "${RUST_LOG:-}" ]]; then
  ROUTER_RUST_LOG="${RUST_LOG}"
fi

if [[ -n "${ROUTER_RUST_LOG}" ]]; then
  cmd=(env "RUST_LOG=${ROUTER_RUST_LOG}" "${cmd[@]}")
fi

echo "out_dir=${OUT_DIR}"
echo "log_file=${LOG_FILE}"
echo "listen_endpoint=${LISTEN_ENDPOINT}"
echo "zenohd_bin=${ZENOHD_BIN}"
echo "router_debug=${ROUTER_DEBUG}"
echo "router_rust_log=${ROUTER_RUST_LOG:-<unset>}"
echo "pid_file=${PID_FILE}"

if [[ ${BACKGROUND} -eq 1 ]]; then
  nohup "${cmd[@]}" >"${LOG_FILE}" 2>&1 &
  router_pid=$!
  printf '%s\n' "${router_pid}" >"${PID_FILE}"
  sleep 1
  if ! kill -0 "${router_pid}" >/dev/null 2>&1; then
    echo "zenohd exited before background startup completed; inspect ${LOG_FILE}" >&2
    exit 1
  fi
  echo "pid=${router_pid}"
  exit 0
fi

"${cmd[@]}" 2>&1 | tee "${LOG_FILE}"
