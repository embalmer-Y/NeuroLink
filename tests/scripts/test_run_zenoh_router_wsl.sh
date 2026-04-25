#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

mock_zenohd="${TMP_DIR}/zenohd"
cat >"${mock_zenohd}" <<'EOF'
#!/usr/bin/env bash
sleep 3
EOF
chmod +x "${mock_zenohd}"

output="$(bash "${SCRIPT}" --zenohd "${mock_zenohd}" --background --output-base "${TMP_DIR}/router" 2>&1)"

pid_file="$(printf '%s\n' "${output}" | awk -F= '/^pid_file=/{print $2}')"
router_pid="$(printf '%s\n' "${output}" | awk -F= '/^pid=/{print $2}')"

if [[ -z "${pid_file}" || ! -f "${pid_file}" ]]; then
  echo "pid file was not created" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

if [[ -z "${router_pid}" ]]; then
  echo "router pid not reported" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

if [[ "$(cat "${pid_file}")" != "${router_pid}" ]]; then
  echo "pid file content mismatch" >&2
  exit 1
fi

kill "${router_pid}" >/dev/null 2>&1 || true

echo "test_run_zenoh_router_wsl.sh: PASS"
