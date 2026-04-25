#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/setup_neurolink_env.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

HOME="${TMP_DIR}/home"
MOCK_BIN="${TMP_DIR}/bin"
mkdir -p "${MOCK_BIN}"
mkdir -p "${HOME}/zephyr-sdk-0.16.8/cmake" "${HOME}/zephyr-sdk-0.17.0/cmake"
touch "${HOME}/zephyr-sdk-0.16.8/cmake/Zephyr-sdkConfig.cmake"
touch "${HOME}/zephyr-sdk-0.17.0/cmake/Zephyr-sdkConfig.cmake"

ln -sf /usr/bin/python3 "${MOCK_BIN}/python3"
for cmd in cmake ninja west clang-format perl gcovr qemu-system-x86_64; do
  cat >"${MOCK_BIN}/${cmd}" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "${MOCK_BIN}/${cmd}"
done

set +e
output="$(HOME="${HOME}" PATH="${MOCK_BIN}:${PATH}" bash "${SCRIPT}" --strict 2>&1)"
rc=$?
set -e

if [[ ${rc} -eq 0 ]]; then
  echo "expected strict setup to fail when multiple SDKs are auto-detected" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

if [[ "${output}" != *"multiple Zephyr SDK installations detected"* ]]; then
  echo "missing multiple-sdk diagnostic" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

set +e
ok_output="$(HOME="${HOME}" PATH="${MOCK_BIN}:${PATH}" ZEPHYR_SDK_INSTALL_DIR="${HOME}/zephyr-sdk-0.16.8" bash "${SCRIPT}" --strict 2>&1)"
ok_rc=$?
set -e

if [[ ${ok_rc} -ne 0 ]]; then
  echo "expected explicit SDK path to pass strict setup" >&2
  printf '%s\n' "${ok_output}" >&2
  exit 1
fi

if [[ "${ok_output}" != *"zephyr_sdk_install_dir=${HOME}/zephyr-sdk-0.16.8"* ]]; then
  echo "explicit SDK path not reported" >&2
  printf '%s\n' "${ok_output}" >&2
  exit 1
fi

echo "test_setup_neurolink_env.sh: PASS"
