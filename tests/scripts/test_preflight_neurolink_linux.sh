#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/preflight_neurolink_linux.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

mock_bin="${TMP_DIR}/bin"
router_helper="${TMP_DIR}/router-helper.sh"
valid_artifact="${TMP_DIR}/valid-default.llext"
mkdir -p "${mock_bin}"
printf '\177ELF\001\001fake llext\n' >"${valid_artifact}"

cat >"${mock_bin}/ss" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "${mock_bin}/ss"

for cmd in cmake ninja west clang-format perl; do
  cat >"${mock_bin}/${cmd}" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "${mock_bin}/${cmd}"
done

cat >"${mock_bin}/python3" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *"import zenoh"* ]]; then
  exit 0
fi
if [[ "$1" == "/home/emb/project/zephyrproject/applocation/NeuroLink/neuro_cli/src/neuro_cli.py" ]]; then
  echo '{"status": "no_reply"}'
  exit 1
fi
exec /usr/bin/python3 "$@"
EOF
chmod +x "${mock_bin}/python3"

cat >"${router_helper}" <<'EOF'
#!/usr/bin/env bash
echo 'pid=1234'
exit 0
EOF
chmod +x "${router_helper}"

set +e
output="$(NEUROLINK_ROUTER_SCRIPT="${router_helper}" PATH="${mock_bin}:${PATH}" bash "${SCRIPT}" --artifact-file "${valid_artifact}" --auto-start-router --output json 2>&1)"
rc=$?
set -e

if [[ ${rc} -eq 0 ]]; then
  echo "expected preflight to fail when router helper never makes port ready" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

if [[ "${output}" != *'"status": "router_failed_to_start"'* ]]; then
  echo "missing router_failed_to_start status" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

empty_artifact="${TMP_DIR}/empty.llext"
touch "${empty_artifact}"

set +e
output="$(PATH="${mock_bin}:${PATH}" bash "${SCRIPT}" --artifact-file "${empty_artifact}" --output json 2>&1)"
rc=$?
set -e

if [[ ${rc} -eq 0 ]]; then
  echo "expected preflight to fail for an empty custom artifact" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

if [[ "${output}" != *'"status": "artifact_invalid"'* ]]; then
  echo "missing artifact_invalid status" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

placeholder_artifact="${TMP_DIR}/placeholder.llext"
printf '\177ELFfake llext\n' >"${placeholder_artifact}"

set +e
output="$(PATH="${mock_bin}:${PATH}" bash "${SCRIPT}" --artifact-file "${placeholder_artifact}" --output json 2>&1)"
rc=$?
set -e

if [[ ${rc} -eq 0 ]]; then
  echo "expected preflight to fail for an ELF-like placeholder artifact" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

if [[ "${output}" != *'"status": "artifact_invalid"'* ]]; then
  echo "missing artifact_invalid status for ELF-like placeholder artifact" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

echo "test_preflight_neurolink_linux.sh: PASS"
