#!/usr/bin/env bash
set -euo pipefail

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

archive="${TMP_DIR}/unsafe.zip"
python3 - <<'PY' "${archive}"
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1], 'w') as zf:
    zf.writestr('../escape.txt', 'bad')
PY

set +e
output="$(python3 - <<'PY' "${archive}" "${TMP_DIR}/out" 2>&1
from pathlib import PurePosixPath
import sys
import zipfile

archive = sys.argv[1]
target = sys.argv[2]
with zipfile.ZipFile(archive) as zf:
    for member in zf.infolist():
        path = member.filename
        parts = PurePosixPath(path).parts
        if path.startswith(("/", "\\")) or ".." in parts:
            raise SystemExit(f"unsafe archive member: {path}")
    zf.extractall(target)
PY
)"
rc=$?
set -e

if [[ ${rc} -eq 0 ]]; then
  echo "expected unsafe archive guard to fail" >&2
  exit 1
fi

if [[ "${output}" != *"unsafe archive member: ../escape.txt"* ]]; then
  echo "unexpected unsafe-archive output" >&2
  printf '%s\n' "${output}" >&2
  exit 1
fi

echo "test_install_zenoh_router_wsl.sh: PASS"
