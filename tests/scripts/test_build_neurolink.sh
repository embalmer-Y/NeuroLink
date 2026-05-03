#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/build_neurolink.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

assert_contains() {
  local haystack="$1"
  local needle="$2"

  if [[ "${haystack}" != *"${needle}"* ]]; then
    echo "expected to find '${needle}' in output:" >&2
    printf '%s\n' "${haystack}" >&2
    exit 1
  fi
}

run_expect_fail() {
  local expected_rc="$1"
  shift
  local output
  local rc

  set +e
  output="$(bash "${SCRIPT}" "$@" 2>&1)"
  rc=$?
  set -e

  if [[ ${rc} -ne ${expected_rc} ]]; then
    echo "expected rc=${expected_rc}, got rc=${rc}" >&2
    printf '%s\n' "${output}" >&2
    exit 1
  fi

  printf '%s' "${output}"
}

invalid_preset_output="$(run_expect_fail 2 --preset invalid --no-c-style-check)"
assert_contains "${invalid_preset_output}" "invalid preset 'invalid'"

invalid_build_dir_output="$(run_expect_fail 2 --build-dir ../oops --no-c-style-check)"
assert_contains "${invalid_build_dir_output}" "parent traversal is not allowed"

invalid_app_output="$(run_expect_fail 2 --app '../bad' --no-c-style-check)"
assert_contains "${invalid_app_output}" "invalid app id '../bad'"

missing_app_output="$(run_expect_fail 2 --app neuro_demo_missing --no-c-style-check)"
assert_contains "${missing_app_output}" "app source dir not found"

invalid_app_source_output="$(run_expect_fail 2 --app-source-dir ../bad --no-c-style-check)"
assert_contains "${invalid_app_source_output}" "parent traversal is not allowed"

script_text="$(<"${SCRIPT}")"
assert_contains "${script_text}" "--overlay-config <path>"
assert_contains "${script_text}" "--strip-llext-debug"
assert_contains "${script_text}" "--app <app-id>"
assert_contains "${script_text}" "--app-source-dir <path>"
assert_contains "${script_text}" "subprojects/\${UNIT_APP_ID}"
assert_contains "${script_text}" "\${UNIT_APP_ID}.llext"
assert_contains "${script_text}" "-DEXTRA_CONF_FILE="
assert_contains "${script_text}" "parent traversal is not allowed"

candidate_overlay="${ROOT_DIR}/applocation/NeuroLink/neuro_unit/overlays/external_staging_candidate.conf"
[[ -f "${candidate_overlay}" ]] || {
  echo "missing external staging candidate overlay: ${candidate_overlay}" >&2
  exit 1
}
grep -q "CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=y" "${candidate_overlay}"
grep -q "CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n" "${candidate_overlay}"

gpio_internal_overlay="${ROOT_DIR}/applocation/NeuroLink/neuro_unit/overlays/gpio_internal_staging_candidate.conf"
[[ -f "${gpio_internal_overlay}" ]] || {
  echo "missing GPIO internal staging candidate overlay: ${gpio_internal_overlay}" >&2
  exit 1
}
grep -q "CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=n" "${gpio_internal_overlay}"
grep -q "CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=28672" "${gpio_internal_overlay}"
grep -q "CONFIG_NEUROLINK_APP_MAX_LOADED=1" "${gpio_internal_overlay}"
grep -q "CONFIG_NEUROLINK_APP_MAX_RUNNING=1" "${gpio_internal_overlay}"
grep -q "CONFIG_LLEXT_EXPORT_DEVICES=y" "${gpio_internal_overlay}"

gpio_heap_trim_overlay="${ROOT_DIR}/applocation/NeuroLink/neuro_unit/overlays/gpio_llext_heap_trim_candidate.conf"
[[ -f "${gpio_heap_trim_overlay}" ]] || {
  echo "missing GPIO LLEXT heap trim candidate overlay: ${gpio_heap_trim_overlay}" >&2
  exit 1
}
grep -q "CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=28672" "${gpio_heap_trim_overlay}"
grep -q "CONFIG_NEUROLINK_APP_MAX_LOADED=1" "${gpio_heap_trim_overlay}"
grep -q "CONFIG_LLEXT_HEAP_SIZE=32" "${gpio_heap_trim_overlay}"
grep -q "CONFIG_LLEXT_EXPORT_DEVICES=y" "${gpio_heap_trim_overlay}"

gpio_exec_guard_overlay="${ROOT_DIR}/applocation/NeuroLink/neuro_unit/overlays/gpio_exec_guard_candidate.conf"
[[ -f "${gpio_exec_guard_overlay}" ]] || {
  echo "missing GPIO executable guard candidate overlay: ${gpio_exec_guard_overlay}" >&2
  exit 1
}
grep -q "CONFIG_NEUROLINK_APP_REJECT_STAGING_TEXT_EXEC=y" "${gpio_exec_guard_overlay}"
grep -q "CONFIG_LLEXT_HEAP_SIZE=32" "${gpio_exec_guard_overlay}"
grep -q "CONFIG_LLEXT_EXPORT_DEVICES=y" "${gpio_exec_guard_overlay}"

gpio_exec_alias_overlay="${ROOT_DIR}/applocation/NeuroLink/neuro_unit/overlays/gpio_exec_alias_candidate.conf"
[[ -f "${gpio_exec_alias_overlay}" ]] || {
  echo "missing GPIO executable alias candidate overlay: ${gpio_exec_alias_overlay}" >&2
  exit 1
}
grep -q "CONFIG_NEUROLINK_APP_REJECT_STAGING_TEXT_EXEC=y" "${gpio_exec_alias_overlay}"
grep -q "CONFIG_NEUROLINK_APP_FIXUP_STAGING_TEXT_ALIAS=y" "${gpio_exec_alias_overlay}"
grep -q "CONFIG_LLEXT_HEAP_SIZE=32" "${gpio_exec_alias_overlay}"
grep -q "CONFIG_LLEXT_EXPORT_DEVICES=y" "${gpio_exec_alias_overlay}"

dynamic_heap_overlay="${ROOT_DIR}/applocation/NeuroLink/neuro_unit/overlays/llext_dynamic_heap_candidate.conf"
[[ -f "${dynamic_heap_overlay}" ]] || {
  echo "missing LLEXT dynamic heap candidate overlay: ${dynamic_heap_overlay}" >&2
  exit 1
}
grep -q "CONFIG_LLEXT_HEAP_DYNAMIC=y" "${dynamic_heap_overlay}"
grep -q "CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=n" "${dynamic_heap_overlay}"
grep -q "CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n" "${dynamic_heap_overlay}"
grep -q "CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576" "${dynamic_heap_overlay}"

heap_trim_overlay="${ROOT_DIR}/applocation/NeuroLink/neuro_unit/overlays/heap_trim_candidate.conf"
[[ -f "${heap_trim_overlay}" ]] || {
  echo "missing heap trim candidate overlay: ${heap_trim_overlay}" >&2
  exit 1
}
grep -q "CONFIG_HEAP_MEM_POOL_SIZE=53248" "${heap_trim_overlay}"
grep -q "CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=n" "${heap_trim_overlay}"
grep -q "CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER=n" "${heap_trim_overlay}"
grep -q "CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576" "${heap_trim_overlay}"

net_buf_trim_overlay="${ROOT_DIR}/applocation/NeuroLink/neuro_unit/overlays/net_buf_trim_candidate.conf"
[[ -f "${net_buf_trim_overlay}" ]] || {
  echo "missing net buffer trim candidate overlay: ${net_buf_trim_overlay}" >&2
  exit 1
}
grep -q "CONFIG_NET_BUF_RX_COUNT=44" "${net_buf_trim_overlay}"
grep -q "CONFIG_NET_BUF_TX_COUNT=44" "${net_buf_trim_overlay}"
grep -q "CONFIG_NET_PKT_RX_COUNT=20" "${net_buf_trim_overlay}"
grep -q "CONFIG_NET_PKT_TX_COUNT=20" "${net_buf_trim_overlay}"
grep -q "CONFIG_HEAP_MEM_POOL_SIZE=53248" "${net_buf_trim_overlay}"

main_stack_trim_overlay="${ROOT_DIR}/applocation/NeuroLink/neuro_unit/overlays/main_stack_trim_candidate.conf"
[[ -f "${main_stack_trim_overlay}" ]] || {
  echo "missing main stack trim candidate overlay: ${main_stack_trim_overlay}" >&2
  exit 1
}
grep -q "CONFIG_MAIN_STACK_SIZE=18432" "${main_stack_trim_overlay}"
grep -q "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=6144" "${main_stack_trim_overlay}"
grep -q "CONFIG_SHELL_STACK_SIZE=4096" "${main_stack_trim_overlay}"
grep -q "CONFIG_HEAP_MEM_POOL_SIZE=53248" "${main_stack_trim_overlay}"

workqueue_stack_trim_overlay="${ROOT_DIR}/applocation/NeuroLink/neuro_unit/overlays/workqueue_stack_trim_candidate.conf"
[[ -f "${workqueue_stack_trim_overlay}" ]] || {
  echo "missing workqueue stack trim candidate overlay: ${workqueue_stack_trim_overlay}" >&2
  exit 1
}
grep -q "CONFIG_MAIN_STACK_SIZE=18432" "${workqueue_stack_trim_overlay}"
grep -q "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=5120" "${workqueue_stack_trim_overlay}"
grep -q "CONFIG_SHELL_STACK_SIZE=4096" "${workqueue_stack_trim_overlay}"
grep -q "CONFIG_HEAP_MEM_POOL_SIZE=53248" "${workqueue_stack_trim_overlay}"

cache_file="${TMP_DIR}/CMakeCache.txt"
cat >"${cache_file}" <<'EOF'
CMAKE_C_COMPILER:FILEPATH=/usr/bin/clang
CMAKE_C_COMPILER_LAUNCHER:STRING=ccache
EOF

resolved_value="$(awk -F= -v cache_key='CMAKE_C_COMPILER' '
  index($0, cache_key ":") == 1 {
    sub(/^[^=]*=/, "", $0)
    print
    exit
  }
' "${cache_file}")"

if [[ "${resolved_value}" != "/usr/bin/clang" ]]; then
  echo "cmake cache resolution regression: expected /usr/bin/clang got '${resolved_value}'" >&2
  exit 1
fi

echo "test_build_neurolink.sh: PASS"
