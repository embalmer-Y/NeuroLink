#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/setup_neurolink_env.sh"
DEVICE="/dev/ttyACM0"
BAUD="115200"
EOL="LF"
OUTPUT_BASE="applocation/NeuroLink/smoke-evidence/serial-diag"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/monitor_neurolink_uart.sh [options]

Options:
  --device <path>         Serial device path (default: /dev/ttyACM0)
  --baud <rate>           Baud rate (default: 115200)
  --eol <CR|LF|CRLF>      Miniterm line ending mode (default: LF)
  --output-base <path>    Evidence-relative log directory base

This helper starts pyserial miniterm inside a `script` capture session so the
interactive serial console is preserved in a timestamped log file.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --device)
      DEVICE="$2"
      shift 2
      ;;
    --baud)
      BAUD="$2"
      shift 2
      ;;
    --eol)
      EOL="$2"
      shift 2
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

[[ -f "${ENV_SCRIPT}" ]] || {
  echo "setup script not found at ${ENV_SCRIPT}" >&2
  exit 2
}

[[ -e "${DEVICE}" ]] || {
  echo "serial device not found: ${DEVICE}" >&2
  exit 2
}

# shellcheck disable=SC1090
source "${ENV_SCRIPT}" --activate --strict

python3 -c 'import serial.tools.miniterm' >/dev/null 2>&1 || {
  echo "pyserial miniterm is not available in the active environment" >&2
  exit 2
}

cd "${ROOT_DIR}"

LOG_DIR="${ROOT_DIR}/${OUTPUT_BASE}"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/miniterm-${TIMESTAMP}.log"

echo "log_file=${LOG_FILE}"
echo "device=${DEVICE}"
echo "baud=${BAUD}"

if ! script -q -f -c "python3 -m serial.tools.miniterm ${DEVICE} ${BAUD} --eol ${EOL}" "${LOG_FILE}"; then
  echo "serial capture failed; inspect ${LOG_FILE}" >&2
  exit 1
fi
