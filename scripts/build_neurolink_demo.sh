#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BUILD_SCRIPT="${NEUROLINK_BUILD_NEUROLINK_SCRIPT:-${ROOT_DIR}/applocation/NeuroLink/scripts/build_neurolink.sh}"
CATALOG_FILE="${NEUROLINK_DEMO_CATALOG_FILE:-${ROOT_DIR}/applocation/NeuroLink/subprojects/demo_catalog.json}"
DEMO_APP_ID=""
BUILD_DIR=""
BOARD=""
PRINT_ARTIFACT_PATH=0
CHECK_C_STYLE=1
PRISTINE_ALWAYS=0
EXTRA_WEST_ARGS=()
EXTRA_CMAKE_ARGS=()
OVERLAY_CONFIGS=()
STRIP_LLEXT_DEBUG=0

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/build_neurolink_demo.sh [options]

Options:
  --demo <app-id>                  Demo app id from subprojects/demo_catalog.json
  --board <board>                  Override Zephyr board
  --build-dir <build/path>         Override Unit build directory
  --pristine-always                Force pristine Unit build reconfiguration
  --overlay-config <path>          Forward Kconfig overlay to build_neurolink.sh
  --strip-llext-debug              Strip non-loader debug sections from the staged LLEXT
  --extra-west-arg <arg>           Forward extra west build arg
  --extra-cmake-arg <arg>          Forward extra cmake arg
  --no-c-style-check               Skip Linux kernel style gate before build
  --print-artifact-path            Print the resolved artifact path after build
EOF
}

resolve_demo_entry() {
  local app_id="$1"

  python3 - <<'PY' "${CATALOG_FILE}" "${app_id}"
import json
import sys

catalog_path = sys.argv[1]
app_id = sys.argv[2]

with open(catalog_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

for entry in payload.get("entries", []):
    if entry.get("app_id") != app_id:
        continue
    source_dir = entry.get("source_dir")
    artifact = entry.get("artifact")
    status = entry.get("status")
    missing = [
        field_name
        for field_name, value in (
            ("source_dir", source_dir),
            ("artifact", artifact),
            ("status", status),
        )
        if not value
    ]
    if missing:
        print(
            f"demo '{app_id}' is missing required field(s) {', '.join(missing)} in {catalog_path}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print(source_dir)
    print(artifact)
    print(status)
    raise SystemExit(0)

print(f"demo '{app_id}' is not defined in {catalog_path}", file=sys.stderr)
raise SystemExit(2)
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --demo)
      DEMO_APP_ID="$2"
      shift 2
      ;;
    --board)
      BOARD="$2"
      shift 2
      ;;
    --build-dir)
      BUILD_DIR="$2"
      shift 2
      ;;
    --pristine-always)
      PRISTINE_ALWAYS=1
      shift
      ;;
    --overlay-config)
      OVERLAY_CONFIGS+=("$2")
      shift 2
      ;;
    --strip-llext-debug)
      STRIP_LLEXT_DEBUG=1
      shift
      ;;
    --extra-west-arg)
      EXTRA_WEST_ARGS+=("$2")
      shift 2
      ;;
    --extra-cmake-arg)
      EXTRA_CMAKE_ARGS+=("$2")
      shift 2
      ;;
    --no-c-style-check)
      CHECK_C_STYLE=0
      shift
      ;;
    --print-artifact-path)
      PRINT_ARTIFACT_PATH=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "${DEMO_APP_ID}" ]] || {
  echo "demo id is required; use --demo <app-id>" >&2
  exit 2
}

[[ -f "${BUILD_SCRIPT}" ]] || {
  echo "build script not found at ${BUILD_SCRIPT}" >&2
  exit 2
}

[[ -f "${CATALOG_FILE}" ]] || {
  echo "demo catalog not found at ${CATALOG_FILE}" >&2
  exit 2
}

demo_entry_output="$(resolve_demo_entry "${DEMO_APP_ID}")"
mapfile -t demo_entry <<<"${demo_entry_output}"
DEMO_SOURCE_DIR="${demo_entry[0]}"
CATALOG_ARTIFACT_FILE="${demo_entry[1]}"
DEMO_STATUS="${demo_entry[2]}"

ARTIFACT_FILE="${CATALOG_ARTIFACT_FILE}"
if [[ -n "${BUILD_DIR}" ]]; then
  ARTIFACT_FILE="${BUILD_DIR}/llext/${DEMO_APP_ID}.llext"
fi

cmd=(
  bash "${BUILD_SCRIPT}"
  --preset unit-app
  --app "${DEMO_APP_ID}"
  --app-source-dir "${DEMO_SOURCE_DIR}"
)

if [[ -n "${BOARD}" ]]; then
  cmd+=(--board "${BOARD}")
fi
if [[ -n "${BUILD_DIR}" ]]; then
  cmd+=(--build-dir "${BUILD_DIR}")
fi
if [[ ${PRISTINE_ALWAYS} -eq 1 ]]; then
  cmd+=(--pristine-always)
fi
if [[ ${CHECK_C_STYLE} -eq 0 ]]; then
  cmd+=(--no-c-style-check)
fi
if [[ ${STRIP_LLEXT_DEBUG} -eq 1 ]]; then
  cmd+=(--strip-llext-debug)
fi
for overlay_config in "${OVERLAY_CONFIGS[@]}"; do
  cmd+=(--overlay-config "${overlay_config}")
done
for extra_west_arg in "${EXTRA_WEST_ARGS[@]}"; do
  cmd+=(--extra-west-arg "${extra_west_arg}")
done
for extra_cmake_arg in "${EXTRA_CMAKE_ARGS[@]}"; do
  cmd+=(--extra-cmake-arg "${extra_cmake_arg}")
done

"${cmd[@]}"

if [[ ${PRINT_ARTIFACT_PATH} -eq 1 ]]; then
  printf '%s\n' "${ARTIFACT_FILE}"
  exit 0
fi

echo "demo_app_id=${DEMO_APP_ID}"
echo "demo_status=${DEMO_STATUS}"
echo "source_dir=${DEMO_SOURCE_DIR}"
echo "artifact_file=${ARTIFACT_FILE}"