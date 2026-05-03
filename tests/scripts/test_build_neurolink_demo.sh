#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/build_neurolink_demo.sh"
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

missing_demo_output="$(run_expect_fail 2 --no-c-style-check)"
assert_contains "${missing_demo_output}" "demo id is required"

missing_catalog_demo_output="$(run_expect_fail 2 --demo neuro_demo_missing --no-c-style-check)"
assert_contains "${missing_catalog_demo_output}" "demo 'neuro_demo_missing' is not defined"

help_output="$(bash "${SCRIPT}" --help)"
assert_contains "${help_output}" "Usage: bash applocation/NeuroLink/scripts/build_neurolink_demo.sh"
assert_contains "${help_output}" "--demo <app-id>"
assert_contains "${help_output}" "--print-artifact-path"

stub_build_script="${TMP_DIR}/build_stub.sh"
stub_log="${TMP_DIR}/build_stub.log"
cat >"${stub_build_script}" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" >"${NEUROLINK_BUILD_LOG}"
EOF
chmod +x "${stub_build_script}"

wrapper_output="$(NEUROLINK_BUILD_NEUROLINK_SCRIPT="${stub_build_script}" \
  NEUROLINK_BUILD_LOG="${stub_log}" \
  bash "${SCRIPT}" \
    --demo neuro_demo_net_event \
    --board native_sim \
    --build-dir build/demo_wrapper_check \
    --pristine-always \
    --overlay-config applocation/NeuroLink/neuro_unit/overlays/external_staging_candidate.conf \
    --extra-west-arg -v \
    --extra-cmake-arg -DEXAMPLE=1 \
    --no-c-style-check)"

assert_contains "${wrapper_output}" "demo_app_id=neuro_demo_net_event"
assert_contains "${wrapper_output}" "demo_status=implemented_local"
assert_contains "${wrapper_output}" "source_dir=applocation/NeuroLink/subprojects/neuro_demo_net_event"
assert_contains "${wrapper_output}" "artifact_file=build/demo_wrapper_check/llext/neuro_demo_net_event.llext"

stub_args="$(<"${stub_log}")"
assert_contains "${stub_args}" "--preset"
assert_contains "${stub_args}" "unit-app"
assert_contains "${stub_args}" "--app"
assert_contains "${stub_args}" "neuro_demo_net_event"
assert_contains "${stub_args}" "--app-source-dir"
assert_contains "${stub_args}" "applocation/NeuroLink/subprojects/neuro_demo_net_event"
assert_contains "${stub_args}" "--board"
assert_contains "${stub_args}" "native_sim"
assert_contains "${stub_args}" "--build-dir"
assert_contains "${stub_args}" "build/demo_wrapper_check"
assert_contains "${stub_args}" "--pristine-always"
assert_contains "${stub_args}" "--overlay-config"
assert_contains "${stub_args}" "external_staging_candidate.conf"
assert_contains "${stub_args}" "--extra-west-arg"
assert_contains "${stub_args}" $'\n-v\n'
assert_contains "${stub_args}" "--extra-cmake-arg"
assert_contains "${stub_args}" "-DEXAMPLE=1"
assert_contains "${stub_args}" "--no-c-style-check"

artifact_path_output="$(NEUROLINK_BUILD_NEUROLINK_SCRIPT="${stub_build_script}" \
  NEUROLINK_BUILD_LOG="${stub_log}" \
  bash "${SCRIPT}" --demo neuro_demo_net_event --print-artifact-path --no-c-style-check)"

if [[ "${artifact_path_output}" != "build/neurolink_unit/llext/neuro_demo_net_event.llext" ]]; then
  echo "unexpected artifact path output: ${artifact_path_output}" >&2
  exit 1
fi

echo "test_build_neurolink_demo.sh: PASS"