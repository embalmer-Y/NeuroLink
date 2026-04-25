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
