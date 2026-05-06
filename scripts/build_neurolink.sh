#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/setup_neurolink_env.sh"
STYLE_SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/check_neurolink_linux_c_style.sh"
UNIT_SOURCE_DIR="applocation/NeuroLink/neuro_unit"
UNIT_APP_ID="neuro_unit_app"
UNIT_APP_SOURCE_DIR=""
PRESET="unit"
BOARD="dnesp32s3b/esp32s3/procpu"
BUILD_DIR=""
PRISTINE_ALWAYS=0
ESP_DEVICE=""
CHECK_C_STYLE=1
EXTRA_WEST_ARGS=()
EXTRA_CMAKE_ARGS=()
OVERLAY_CONFIGS=()
STRIP_LLEXT_DEBUG=0
ZENOH_PICO_MODULE_FILE="${ROOT_DIR}/modules/lib/zenoh-pico/zephyr/CMakeLists.txt"

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/build_neurolink.sh [options]
  --preset <unit|unit-ut|unit-edk|unit-app|unit-ext|flash-unit>
  --board <board>
  --build-dir <build/path>
  --pristine-always
  --esp-device <device>
  --no-c-style-check
  --overlay-config <path>
  --strip-llext-debug
  --app <app-id>
  --app-source-dir <path>
  --extra-west-arg <arg>
  --extra-cmake-arg <arg>
EOF
}

assert_app_id() {
  local candidate="$1"

  [[ -n "${candidate}" ]] || {
    echo "app id is required" >&2
    exit 2
  }

  [[ "${candidate}" =~ ^[A-Za-z0-9_][A-Za-z0-9_-]*$ ]] || {
    echo "invalid app id '${candidate}': use letters, numbers, underscore, and dash only" >&2
    exit 2
  }
}

resolve_unit_app_source_dir() {
  local candidate="$1"
  local normalized
  local path

  if [[ -z "${candidate}" ]]; then
    candidate="applocation/NeuroLink/subprojects/${UNIT_APP_ID}"
  fi

  normalized="$(printf '%s' "${candidate}" | tr '\\' '/' | sed 's/[[:space:]]*$//')"
  [[ -n "${normalized}" ]] || {
    echo "app source dir is required" >&2
    exit 2
  }
  [[ ! "${normalized}" =~ \.\. ]] || {
    echo "invalid app source dir '${candidate}': parent traversal is not allowed" >&2
    exit 2
  }

  if [[ "${normalized}" = /* ]]; then
    path="${normalized}"
  else
    path="${ROOT_DIR}/${normalized}"
  fi

  [[ -d "${path}" ]] || {
    echo "app source dir not found: ${candidate}" >&2
    exit 2
  }
  [[ -f "${path}/CMakeLists.txt" ]] || {
    echo "app source dir missing CMakeLists.txt: ${candidate}" >&2
    exit 2
  }

  printf '%s' "${path}"
}

join_by_semicolon() {
  local IFS=';'
  printf '%s' "$*"
}

append_overlay_cmake_arg() {
  local resolved=()
  local candidate
  local normalized
  local path

  [[ ${#OVERLAY_CONFIGS[@]} -gt 0 ]] || return 0

  for candidate in "${OVERLAY_CONFIGS[@]}"; do
    normalized="$(printf '%s' "${candidate}" | tr '\\' '/' | sed 's/[[:space:]]*$//')"
    [[ -n "${normalized}" ]] || {
      echo "overlay config path is empty" >&2
      exit 2
    }
    [[ ! "${normalized}" =~ \.\. ]] || {
      echo "invalid overlay config '${candidate}': parent traversal is not allowed" >&2
      exit 2
    }
    if [[ "${normalized}" = /* ]]; then
      path="${normalized}"
    else
      path="${ROOT_DIR}/${normalized}"
    fi
    [[ -f "${path}" ]] || {
      echo "overlay config not found: ${candidate}" >&2
      exit 2
    }
    resolved+=("${path}")
  done

  EXTRA_CMAKE_ARGS+=("-DEXTRA_CONF_FILE=$(join_by_semicolon "${resolved[@]}")")
}

assert_build_dir() {
  local candidate="$1"
  local normalized

  [[ -n "${candidate}" ]] || {
    echo "build dir is required" >&2
    exit 2
  }

  normalized="$(printf '%s' "${candidate}" | tr '\\' '/' | sed 's/[[:space:]]*$//')"
  [[ ! "${normalized}" =~ \.\. ]] || {
    echo "invalid build dir '${candidate}': parent traversal is not allowed" >&2
    exit 2
  }
  [[ ! "${normalized}" =~ ^build_ ]] || {
    echo "invalid build dir '${candidate}': root-level build_* is forbidden" >&2
    exit 2
  }
  [[ "${normalized}" =~ ^build/.+ ]] || {
    echo "invalid build dir '${candidate}': only build/<target> is allowed" >&2
    exit 2
  }
}

assert_zenoh_pico_module() {
  [[ -f "${ZENOH_PICO_MODULE_FILE}" ]] && return 0

  echo "missing zenoh-pico Zephyr module at ${ZENOH_PICO_MODULE_FILE}" >&2
  echo "run 'west update zenoh-pico' or 'west update' after keeping zephyr/submanifests/zenoh-pico.yaml in the workspace" >&2
  exit 2
}

get_unit_app_build_dir() {
  local parent_dir
  local base_name
  local normalized_app_id

  parent_dir="$(dirname "${BUILD_DIR}")"
  base_name="$(basename "${BUILD_DIR}")"

  if [[ "${UNIT_APP_ID}" == "neuro_unit_app" ]]; then
    printf '%s/%s_app' "${parent_dir}" "${base_name}"
    return 0
  fi

  normalized_app_id="$(printf '%s' "${UNIT_APP_ID}" | tr '-' '_')"
  printf '%s/%s_%s_app' "${parent_dir}" "${base_name}" "${normalized_app_id}"
}

ensure_unit_build_configured() {
  if [[ ${PRISTINE_ALWAYS} -eq 0 ]] && [[ -f "${BUILD_DIR}/CMakeCache.txt" ]]; then
    return 0
  fi

  local cmd=(west build)

  [[ ${PRISTINE_ALWAYS} -eq 1 ]] && cmd+=(-p always)
  cmd+=("${EXTRA_WEST_ARGS[@]}" -b "${BOARD}" -s "${UNIT_SOURCE_DIR}" -d "${BUILD_DIR}")
  if [[ ${#EXTRA_CMAKE_ARGS[@]} -gt 0 ]]; then
    cmd+=(-- "${EXTRA_CMAKE_ARGS[@]}")
  fi
  "${cmd[@]}"
}

cmake_cache_value() {
  local cache_file="$1"
  local key="$2"

  awk -F= -v cache_key="${key}" '
    index($0, cache_key ":") == 1 {
      sub(/^[^=]*=/, "", $0)
      print
      exit
    }
  ' "${cache_file}"
}

artifact_is_nonempty_file() {
  [[ -f "$1" ]] && [[ -s "$1" ]]
}

artifact_has_valid_elf_header() {
  local header
  local elf_class
  local elf_version

  [[ -f "$1" ]] || return 1
  header="$(LC_ALL=C od -An -tx1 -N6 "$1" 2>/dev/null | tr -d ' \n')"
  [[ ${#header} -eq 12 ]] || return 1
  [[ "${header:0:8}" == "7f454c46" ]] || return 1

  elf_class="${header:8:2}"
  elf_version="${header:10:2}"
  [[ "${elf_class}" == "01" || "${elf_class}" == "02" ]] || return 1
  [[ "${elf_version}" == "01" ]]
}

artifact_is_valid_llext_file() {
  artifact_is_nonempty_file "$1" && artifact_has_valid_elf_header "$1"
}

build_unit_edk() {
  ensure_unit_build_configured
  west build -d "${BUILD_DIR}" -t llext-edk "${EXTRA_WEST_ARGS[@]}"
}

extract_unit_edk() {
  local edk_archive="${BUILD_DIR}/zephyr/llext-edk.tar.xz"
  local zephyr_dir="${BUILD_DIR}/zephyr"

  [[ -f "${edk_archive}" ]] || {
    echo "missing llext EDK archive at ${edk_archive}" >&2
    exit 2
  }

  rm -rf "${zephyr_dir}/llext-edk"
  tar -xf "${edk_archive}" -C "${zephyr_dir}"
}

build_unit_app_external() {
  local cache_file="${BUILD_DIR}/CMakeCache.txt"
  local app_build_dir
  local c_compiler
  local edk_install_dir
  local staged_artifact_dir="${BUILD_DIR}/llext"
  local staged_artifact_file="${staged_artifact_dir}/${UNIT_APP_ID}.llext"
  local source_artifact_file
  local stripped_artifact_file
  local objcopy

  app_build_dir="$(get_unit_app_build_dir)"
  assert_build_dir "${app_build_dir}"
  source_artifact_file="${app_build_dir}/${UNIT_APP_ID}.llext"

  if [[ ${PRISTINE_ALWAYS} -eq 1 ]]; then
    rm -rf "${app_build_dir}"
  elif [[ -f "${source_artifact_file}" ]] && ! artifact_is_valid_llext_file "${source_artifact_file}"; then
    rm -f "${source_artifact_file}"
  fi

  build_unit_edk
  extract_unit_edk

  c_compiler="$(cmake_cache_value "${cache_file}" CMAKE_C_COMPILER)"
  [[ -n "${c_compiler}" ]] || {
    echo "failed to resolve C compiler from ${cache_file}" >&2
    exit 2
  }
  edk_install_dir="$(cd "${BUILD_DIR}/zephyr/llext-edk" && pwd)"

  cmake -S "${UNIT_APP_SOURCE_DIR}" -B "${app_build_dir}" \
    -DCMAKE_TOOLCHAIN_FILE="${UNIT_APP_SOURCE_DIR}/toolchain.cmake" \
    -DCMAKE_C_COMPILER="${c_compiler}" \
    -DLLEXT_EDK_INSTALL_DIR="${edk_install_dir}"
  cmake --build "${app_build_dir}"

  source_artifact_file="${app_build_dir}/${UNIT_APP_ID}.llext"
  artifact_is_valid_llext_file "${source_artifact_file}" || {
    echo "unit app build produced missing, empty, or invalid artifact: ${source_artifact_file}" >&2
    exit 2
  }

  if [[ ${STRIP_LLEXT_DEBUG} -eq 1 ]]; then
    objcopy="${c_compiler%-gcc}-objcopy"
    [[ -x "${objcopy}" ]] || {
      echo "failed to resolve objcopy from compiler ${c_compiler}" >&2
      exit 2
    }
    stripped_artifact_file="${app_build_dir}/${UNIT_APP_ID}.stripped.llext"
    "${objcopy}" \
      --remove-section=.debug_info \
      --remove-section=.debug_abbrev \
      --remove-section=.debug_aranges \
      --remove-section=.debug_line \
      --remove-section=.debug_str \
      --remove-section=.comment \
      --remove-section=.xtensa.info \
      "${source_artifact_file}" "${stripped_artifact_file}"
    [[ -s "${stripped_artifact_file}" ]] || {
      echo "failed to produce stripped unit app artifact: ${stripped_artifact_file}" >&2
      exit 2
    }
    source_artifact_file="${stripped_artifact_file}"
  fi

  mkdir -p "${staged_artifact_dir}"
  cp "${source_artifact_file}" "${staged_artifact_file}"
  artifact_is_valid_llext_file "${staged_artifact_file}" || {
    echo "failed to stage valid unit app artifact: ${staged_artifact_file}" >&2
    exit 2
  }
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --preset)
      PRESET="$2"
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
    --esp-device)
      ESP_DEVICE="$2"
      shift 2
      ;;
    --no-c-style-check)
      CHECK_C_STYLE=0
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
    --app)
      UNIT_APP_ID="$2"
      shift 2
      ;;
    --app-source-dir)
      UNIT_APP_SOURCE_DIR="$2"
      shift 2
      ;;
    --extra-west-arg)
      EXTRA_WEST_ARGS+=("$2")
      shift 2
      ;;
    --extra-cmake-arg)
      EXTRA_CMAKE_ARGS+=("$2")
      shift 2
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

case "${PRESET}" in
  unit|unit-ut|unit-edk|unit-app|unit-ext|flash-unit)
    ;;
  *)
    echo "invalid preset '${PRESET}'" >&2
    exit 2
    ;;
esac

assert_app_id "${UNIT_APP_ID}"
UNIT_APP_SOURCE_DIR="$(resolve_unit_app_source_dir "${UNIT_APP_SOURCE_DIR}")"

if [[ -n "${BUILD_DIR}" ]]; then
  assert_build_dir "${BUILD_DIR}"
fi

# shellcheck disable=SC1090
source "${ENV_SCRIPT}" --activate --strict
cd "${ROOT_DIR}"

if [[ ${CHECK_C_STYLE} -eq 1 ]]; then
  bash "${STYLE_SCRIPT}"
fi

if [[ -z "${BUILD_DIR}" ]]; then
  case "${PRESET}" in
    unit|unit-edk|unit-app|unit-ext|flash-unit)
      BUILD_DIR="build/neurolink_unit"
      ;;
    unit-ut)
      BUILD_DIR="build/neurolink_unit_ut"
      ;;
  esac
fi

assert_build_dir "${BUILD_DIR}"
append_overlay_cmake_arg

case "${PRESET}" in
  unit|unit-edk|unit-app|unit-ext)
    assert_zenoh_pico_module
    ;;
esac

case "${PRESET}" in
  unit)
    cmd=(west build)
    [[ ${PRISTINE_ALWAYS} -eq 1 ]] && cmd+=(-p always)
    cmd+=("${EXTRA_WEST_ARGS[@]}" -b "${BOARD}" -s "${UNIT_SOURCE_DIR}" -d "${BUILD_DIR}")
    if [[ ${#EXTRA_CMAKE_ARGS[@]} -gt 0 ]]; then
      cmd+=(-- "${EXTRA_CMAKE_ARGS[@]}")
    fi
    "${cmd[@]}"
    ;;
  unit-ut)
    cmd=(west build)
    [[ ${PRISTINE_ALWAYS} -eq 1 ]] && cmd+=(-p always)
    cmd+=("${EXTRA_WEST_ARGS[@]}" -b "${BOARD}" -s "applocation/NeuroLink/neuro_unit/tests/unit" -d "${BUILD_DIR}")
    if [[ ${#EXTRA_CMAKE_ARGS[@]} -gt 0 ]]; then
      cmd+=(-- "${EXTRA_CMAKE_ARGS[@]}")
    fi
    "${cmd[@]}"
    ;;
  unit-edk)
    build_unit_edk
    extract_unit_edk
    ;;
  unit-app|unit-ext)
    build_unit_app_external
    ;;
  flash-unit)
    cmd=(west flash -d "${BUILD_DIR}")
    [[ -n "${ESP_DEVICE}" ]] && cmd+=(--esp-device "${ESP_DEVICE}")
    cmd+=("${EXTRA_WEST_ARGS[@]}")
    "${cmd[@]}"
    ;;
esac
