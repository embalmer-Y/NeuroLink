#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

scripts=(
  "applocation/NeuroLink/scripts/build_neurolink.sh"
  "applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh"
  "applocation/NeuroLink/scripts/clean_zone_identifier.sh"
  "applocation/NeuroLink/scripts/format_neurolink_c_style.sh"
  "applocation/NeuroLink/scripts/install_zenoh_router_wsl.sh"
  "applocation/NeuroLink/scripts/monitor_neurolink_uart.sh"
  "applocation/NeuroLink/scripts/preflight_neurolink_linux.sh"
  "applocation/NeuroLink/scripts/prepare_dnesp32s3b_wsl.sh"
  "applocation/NeuroLink/scripts/run_zenoh_router_wsl.sh"
  "applocation/NeuroLink/scripts/setup_neurolink_env.sh"
  "applocation/NeuroLink/scripts/smoke_neurolink_linux.sh"
)

for script_path in "${scripts[@]}"; do
  output="$(bash "${ROOT_DIR}/${script_path}" --help 2>&1)"
  if [[ "${output}" != *"Usage:"* ]]; then
    echo "help output missing Usage for ${script_path}" >&2
    printf '%s\n' "${output}" >&2
    exit 1
  fi
done

preview_output="$(bash "${ROOT_DIR}/applocation/NeuroLink/scripts/clean_zone_identifier.sh" "${TMP_DIR}" 2>&1)"
if [[ "${preview_output}" != *"No Zone.Identifier sidecar files found"* && \
      "${preview_output}" != *"Preview only"* && \
      "${preview_output}" != *"no matches found for *:Zone.Identifier"* ]]; then
  echo "clean_zone_identifier preview output unexpected" >&2
  printf '%s\n' "${preview_output}" >&2
  exit 1
fi

echo "test_linux_scripts_help.sh: PASS"
