#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/preflight_neurolink_linux.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

mock_bin="${TMP_DIR}/bin"
router_helper="${TMP_DIR}/router-helper.sh"
mkdir -p "${mock_bin}" "${ROOT_DIR}/build/neurolink_unit/llext"
touch "${ROOT_DIR}/build/neurolink_unit/llext/neuro_unit_app.llext"

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
output="$(NEUROLINK_ROUTER_SCRIPT="${router_helper}" PATH="${mock_bin}:${PATH}" bash "${SCRIPT}" --auto-start-router --output json 2>&1)"
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

echo "test_preflight_neurolink_linux.sh: PASS"
