#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
TEST_DIR="${ROOT_DIR}/applocation/NeuroLink/tests/scripts"
pass_count=0
fail_count=0

for test_script in \
  "${TEST_DIR}/test_build_neurolink.sh" \
  "${TEST_DIR}/test_collect_neurolink_memory_evidence.sh" \
  "${TEST_DIR}/test_style_scripts.sh" \
  "${TEST_DIR}/test_setup_neurolink_env.sh" \
  "${TEST_DIR}/test_preflight_neurolink_linux.sh" \
  "${TEST_DIR}/test_smoke_neurolink_linux.sh" \
  "${TEST_DIR}/test_linux_scripts_help.sh" \
  "${TEST_DIR}/test_run_zenoh_router_wsl.sh" \
  "${TEST_DIR}/test_install_zenoh_router_wsl.sh"
 do
  echo "[SCRIPT-TEST] $(basename "${test_script}")"
  if bash "${test_script}"; then
    pass_count=$((pass_count + 1))
  else
    fail_count=$((fail_count + 1))
  fi
 done

echo "script_tests_passed=${pass_count}"
echo "script_tests_failed=${fail_count}"

if [[ ${fail_count} -ne 0 ]]; then
  exit 1
fi
