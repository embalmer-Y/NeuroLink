#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/setup_neurolink_env.sh"
PREFLIGHT_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/preflight_neurolink_linux.sh"
UART_CAPTURE_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/capture_neurolink_uart.py"
CLI_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/neuro_cli/src/neuro_cli.py"
BOARD_NAME="dnesp32s3b"
USB_HINT="CH343"
NODE="unit-01"
DEVICE=""
BUSID=""
WIFI_SSID="${NEUROLINK_WIFI_SSID:-${NEUROLINK_DEFAULT_WIFI_SSID:-cemetery}}"
WIFI_CREDENTIAL="${NEUROLINK_WIFI_CREDENTIAL:-${NEUROLINK_DEFAULT_WIFI_CREDENTIAL:-goodluck1024}}"
CAPTURE_DURATION_SEC=60
ROUTER_LISTEN="tcp/0.0.0.0:7447"
INSTALL_MISSING_CLI_DEPS=1
ROUTER_DEBUG=0
ROUTER_RUST_LOG=""
ATTACH_ONLY=0

verify_query_device_board() {
  local query_output="$1"

  python3 - <<'PY' "${BOARD_NAME}" "${query_output}"
import json
import sys

expected_board = sys.argv[1]
payload = json.loads(sys.argv[2])
replies = payload.get("replies") or []
if not replies:
    raise SystemExit("query device returned no replies")

reply_payload = replies[0].get("payload") or {}
board = reply_payload.get("board")
if board != expected_board:
    raise SystemExit(f"unexpected board '{board}', expected '{expected_board}'")
PY
}

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh [options]

Options:
  --busid <busid>                  Explicit usbipd BUSID to attach
  --device <path>                  Explicit serial device path in WSL
  --wifi-ssid <ssid>               Wi-Fi SSID used for app network_connect
                                    (default: NEUROLINK_WIFI_SSID or lab default)
  --wifi-credential <credential>   Wi-Fi credential used for app network_connect
                                    (default: NEUROLINK_WIFI_CREDENTIAL or lab default)
  --capture-duration-sec <sec>     UART capture duration (default: 60)
  --router-listen <endpoint>       Zenoh router listen endpoint for preflight auto-start
  --router-debug                   Enable debug mode for auto-started zenoh router
  --router-rust-log <level>        Explicit RUST_LOG for auto-started zenoh router
  --node <node>                    Target NeuroLink node id (default: unit-01)
  --attach-only                    Attach/detect the USB serial device, then exit
EOF
}

require_command() {
  local command_name="$1"

  command -v "${command_name}" >/dev/null 2>&1 || {
    echo "required command not found: ${command_name}" >&2
    exit 2
  }
}

usbipd_list_output() {
  usbipd.exe list 2>/dev/null | tr -d '\r'
}

detect_busid() {
  local list_output="$1"
  local matches

  if [[ -n "${BUSID}" ]]; then
    printf '%s\n' "${BUSID}"
    return 0
  fi

  matches="$(printf '%s\n' "${list_output}" | grep -F "${USB_HINT}" || true)"
  if [[ -z "${matches}" ]]; then
    echo "unable to auto-detect ${BOARD_NAME} USB device via usbipd hint '${USB_HINT}'" >&2
    return 1
  fi

  if [[ $(printf '%s\n' "${matches}" | sed '/^$/d' | wc -l) -ne 1 ]]; then
    echo "multiple usbipd candidates matched '${USB_HINT}'; pass --busid explicitly" >&2
    printf '%s\n' "${matches}" >&2
    return 1
  fi

  printf '%s\n' "${matches}" | awk '{print $1}'
}

collect_serial_device() {
  local candidate

  if [[ -n "${DEVICE}" ]] && [[ -e "${DEVICE}" ]]; then
    printf '%s\n' "${DEVICE}"
    return 0
  fi

  for candidate in /dev/ttyACM* /dev/ttyUSB*; do
    if [[ -e "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  return 1
}

attach_usb_into_wsl() {
  local list_output="$1"
  local selected_busid="$2"
  local selected_line
  local bound_here=0

  selected_line="$(printf '%s\n' "${list_output}" | awk -v busid="${selected_busid}" '$1 == busid {print}')"
  [[ -n "${selected_line}" ]] || {
    echo "usbipd BUSID not found: ${selected_busid}" >&2
    return 1
  }

  if grep -F "Attached" <<<"${selected_line}" >/dev/null 2>&1; then
    echo "BUSID ${selected_busid} is already attached into WSL"
    return 0
  fi

  if grep -F "Not shared" <<<"${selected_line}" >/dev/null 2>&1; then
    echo "binding BUSID ${selected_busid} into usbipd share set"
    usbipd.exe bind --busid "${selected_busid}" >/dev/null
    bound_here=1
  fi

  echo "attaching BUSID ${selected_busid} into WSL"
  if ! usbipd.exe attach --wsl --busid "${selected_busid}" >/dev/null; then
    if [[ ${bound_here} -eq 1 ]]; then
      echo "attach failed; unbinding BUSID ${selected_busid} for rollback" >&2
      usbipd.exe unbind --busid "${selected_busid}" >/dev/null 2>&1 || true
    fi
    return 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --busid)
      BUSID="$2"
      shift 2
      ;;
    --device)
      DEVICE="$2"
      shift 2
      ;;
    --wifi-ssid)
      WIFI_SSID="$2"
      shift 2
      ;;
    --wifi-credential)
      WIFI_CREDENTIAL="$2"
      shift 2
      ;;
    --capture-duration-sec)
      CAPTURE_DURATION_SEC="$2"
      shift 2
      ;;
    --router-listen)
      ROUTER_LISTEN="$2"
      shift 2
      ;;
    --router-debug)
      ROUTER_DEBUG=1
      shift
      ;;
    --router-rust-log)
      ROUTER_RUST_LOG="$2"
      shift 2
      ;;
    --node)
      NODE="$2"
      shift 2
      ;;
    --attach-only)
      ATTACH_ONLY=1
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

require_command powershell.exe
require_command usbipd.exe

cd "${ROOT_DIR}"

if ! selected_device="$(collect_serial_device)"; then
  usb_list="$(usbipd_list_output)"
  selected_busid="$(detect_busid "${usb_list}")"
  attach_usb_into_wsl "${usb_list}" "${selected_busid}"

  selected_device=""
  for _ in $(seq 1 20); do
    if selected_device="$(collect_serial_device)"; then
      break
    fi
    sleep 1
  done

  [[ -n "${selected_device}" ]] || {
    echo "serial device did not appear in WSL after usbipd attach" >&2
    exit 1
  }
fi

echo "board=${BOARD_NAME}"
echo "serial_device=${selected_device}"

if [[ ${ATTACH_ONLY} -eq 1 ]]; then
  exit 0
fi

[[ -n "${WIFI_SSID}" ]] || {
  echo "missing Wi-Fi SSID; pass --wifi-ssid or export NEUROLINK_WIFI_SSID" >&2
  exit 2
}

[[ -n "${WIFI_CREDENTIAL}" ]] || {
  echo "missing Wi-Fi credential; pass --wifi-credential or export NEUROLINK_WIFI_CREDENTIAL" >&2
  exit 2
}

[[ -f "${UART_CAPTURE_SCRIPT}" ]] || {
  echo "UART capture helper not found at ${UART_CAPTURE_SCRIPT}" >&2
  exit 2
}

[[ -f "${PREFLIGHT_SCRIPT}" ]] || {
  echo "preflight helper not found at ${PREFLIGHT_SCRIPT}" >&2
  exit 2
}

[[ -f "${CLI_SCRIPT}" ]] || {
  echo "neuro_cli.py not found at ${CLI_SCRIPT}" >&2
  exit 2
}

# shellcheck disable=SC1090
if [[ ${INSTALL_MISSING_CLI_DEPS} -eq 1 ]]; then
  source "${ENV_SCRIPT}" --activate --strict --install-unit-cli-deps
else
  source "${ENV_SCRIPT}" --activate --strict
fi

capture_output="$({
  python3 "${UART_CAPTURE_SCRIPT}" \
    --device "${selected_device}" \
    --duration-sec "${CAPTURE_DURATION_SEC}" \
    --send-after '6:app mount_storage' \
    --send-after "10:app network_connect ${WIFI_SSID} ${WIFI_CREDENTIAL}"
} 2>&1)"
printf '%s\n' "${capture_output}"

preflight_output="$({
  preflight_cmd=(
    bash "${PREFLIGHT_SCRIPT}"
    --node "${NODE}"
    --auto-start-router
    --router-listen "${ROUTER_LISTEN}"
    --require-serial
    --install-missing-cli-deps
    --output text
  )
  if [[ ${ROUTER_DEBUG} -eq 1 ]]; then
    preflight_cmd+=(--router-debug)
  fi
  if [[ -n "${ROUTER_RUST_LOG}" ]]; then
    preflight_cmd+=(--router-rust-log "${ROUTER_RUST_LOG}")
  fi
  "${preflight_cmd[@]}"
} 2>&1)"
printf '%s\n' "${preflight_output}"

query_output="$(python3 "${CLI_SCRIPT}" --output json --node "${NODE}" query device)"
printf '%s\n' "${query_output}"
verify_query_device_board "${query_output}"