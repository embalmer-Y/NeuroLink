#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VENV_PATH="${ROOT_DIR}/.venv"
NEURO_CLI_REQUIREMENTS="${ROOT_DIR}/applocation/NeuroLink/neuro_cli/requirements.txt"
ACTIVATE=0
STRICT=0
INSTALL_NEURO_CLI_DEPS=0
SDK_DETECTION_WARNING=""
RESOLVED_SDK_DIR=""

is_sourced() {
  [[ "${BASH_SOURCE[0]}" != "$0" ]]
}

finish() {
  local code="$1"
  if is_sourced; then
    return "$code"
  fi
  exit "$code"
}

usage() {
  cat <<'EOF'
Usage: source applocation/NeuroLink/scripts/setup_neurolink_env.sh [--activate] [--strict] [--install-neuro-cli-deps] [--venv <path>]
   or: bash applocation/NeuroLink/scripts/setup_neurolink_env.sh [--activate] [--strict] [--install-neuro-cli-deps] [--venv <path>]

Compatibility alias: --install-unit-cli-deps
EOF
}

collect_neuro_cli_requirement_specs() {
  local line

  [[ -f "${NEURO_CLI_REQUIREMENTS}" ]] || return 0

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="$(printf '%s' "${line}" | sed -E 's/[[:space:]]*#.*$//')"
    line="$(printf '%s' "${line}" | xargs)"
    [[ -n "${line}" ]] || continue
    printf '%s\n' "${line}"
  done <"${NEURO_CLI_REQUIREMENTS}"
}

extract_pip_package_name() {
  local requirement_spec="$1"

  requirement_spec="${requirement_spec%%;*}"
  requirement_spec="${requirement_spec%%[*}"
  printf '%s\n' "${requirement_spec}" | sed -E 's/^([A-Za-z0-9_.-]+).*$/\1/'
}

install_neuro_cli_dependencies() {
  [[ -f "${NEURO_CLI_REQUIREMENTS}" ]] || {
    warnings+=("Neuro CLI requirements file not found at ${NEURO_CLI_REQUIREMENTS}")
    return 0
  }

  if ! command -v python3 >/dev/null 2>&1; then
    missing_required+=("python3")
    return 1
  fi

  if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    warnings+=("--install-neuro-cli-deps requested without an active virtual environment; installing into $(python3 -c 'import sys; print(sys.executable)')")
  fi

  python3 -m pip install -r "${NEURO_CLI_REQUIREMENTS}"
}

resolve_sdk_dir() {
  local candidates=()
  local candidate

  if [[ -n "${ZEPHYR_SDK_INSTALL_DIR:-}" ]] && [[ -f "${ZEPHYR_SDK_INSTALL_DIR}/cmake/Zephyr-sdkConfig.cmake" ]]; then
    RESOLVED_SDK_DIR="${ZEPHYR_SDK_INSTALL_DIR}"
    return 0
  fi

  for candidate in "${HOME}"/zephyr-sdk-* /opt/zephyr-sdk-*; do
    if [[ -f "${candidate}/cmake/Zephyr-sdkConfig.cmake" ]]; then
      candidates+=("${candidate}")
    fi
  done

  if [[ ${#candidates[@]} -gt 0 ]]; then
    mapfile -t candidates < <(printf '%s\n' "${candidates[@]}" | sort -V)
    if [[ ${#candidates[@]} -gt 1 ]]; then
      SDK_DETECTION_WARNING="multiple Zephyr SDK installations detected (${candidates[*]})"
    fi
    RESOLVED_SDK_DIR="${candidates[$((${#candidates[@]} - 1))]}"
    return 0
  fi

  RESOLVED_SDK_DIR=""
  return 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --activate)
      ACTIVATE=1
      shift
      ;;
    --strict)
      STRICT=1
      shift
      ;;
    --install-neuro-cli-deps|--install-unit-cli-deps)
      INSTALL_NEURO_CLI_DEPS=1
      shift
      ;;
    --venv)
      [[ $# -ge 2 ]] || {
        echo "missing value for --venv" >&2
        finish 2
      }
      VENV_PATH="$2"
      shift 2
      ;;
    -h|--help)
      usage
      finish 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      finish 2
      ;;
  esac
done

cd "${ROOT_DIR}"

warnings=()
config_errors=()
missing_required=()
missing_optional=()
required_commands=(python3 cmake ninja west clang-format perl)
optional_commands=(gcovr qemu-system-x86_64)

if [[ ${ACTIVATE} -eq 1 ]]; then
  if [[ -f "${VENV_PATH}/bin/activate" ]]; then
    # shellcheck disable=SC1090
    source "${VENV_PATH}/bin/activate"
  else
    warnings+=("virtual environment not found at ${VENV_PATH}; continuing with current PATH")
  fi
fi

if [[ ${INSTALL_NEURO_CLI_DEPS} -eq 1 ]]; then
  install_neuro_cli_dependencies
fi

if [[ -z "${ZEPHYR_BASE:-}" ]] && [[ -d "${ROOT_DIR}/zephyr" ]]; then
  export ZEPHYR_BASE="${ROOT_DIR}/zephyr"
fi

if [[ -z "${ZEPHYR_SDK_INSTALL_DIR:-}" ]]; then
  resolve_sdk_dir || true
  if [[ -n "${RESOLVED_SDK_DIR}" ]]; then
    export ZEPHYR_SDK_INSTALL_DIR="${RESOLVED_SDK_DIR}"
    if [[ -n "${SDK_DETECTION_WARNING}" ]]; then
      if [[ ${STRICT} -eq 1 ]]; then
        config_errors+=("${SDK_DETECTION_WARNING}; export ZEPHYR_SDK_INSTALL_DIR explicitly before running strict checks")
      else
        warnings+=("${SDK_DETECTION_WARNING}; defaulting to ${RESOLVED_SDK_DIR}")
      fi
    fi
  else
    warnings+=("Zephyr SDK not auto-detected; export ZEPHYR_SDK_INSTALL_DIR if builds require it")
  fi
fi

for command_name in "${required_commands[@]}"; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    missing_required+=("${command_name}")
  fi
done

for command_name in "${optional_commands[@]}"; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    missing_optional+=("${command_name}")
  fi
done

if command -v python3 >/dev/null 2>&1 && [[ -f "${NEURO_CLI_REQUIREMENTS}" ]]; then
  missing_python_packages=()

  while IFS= read -r requirement_spec; do
    package_name="$(extract_pip_package_name "${requirement_spec}")"
    [[ -n "${package_name}" ]] || continue
    if ! python3 -m pip show "${package_name}" >/dev/null 2>&1; then
      missing_python_packages+=("${package_name}")
    fi
  done < <(collect_neuro_cli_requirement_specs)

  if [[ ${#missing_python_packages[@]} -gt 0 ]]; then
    warnings+=("missing Neuro CLI Python packages (${missing_python_packages[*]}); install with: python3 -m pip install -r applocation/NeuroLink/neuro_cli/requirements.txt")
  elif ! python3 -c 'import zenoh' >/dev/null 2>&1; then
    warnings+=("python module 'zenoh' missing; install Neuro CLI deps with: python3 -m pip install -r applocation/NeuroLink/neuro_cli/requirements.txt")
  fi
fi

echo "repo_root=${ROOT_DIR}"
echo "venv_path=${VENV_PATH}"
echo "zephyr_base=${ZEPHYR_BASE:-unset}"
echo "zephyr_sdk_install_dir=${ZEPHYR_SDK_INSTALL_DIR:-unset}"

if [[ ${#warnings[@]} -gt 0 ]]; then
  printf 'warning: %s\n' "${warnings[@]}"
fi

if [[ ${#config_errors[@]} -gt 0 ]]; then
  printf 'configuration error: %s\n' "${config_errors[@]}" >&2
  finish 1
fi

if [[ ${#missing_required[@]} -gt 0 ]]; then
  printf 'missing required command: %s\n' "${missing_required[@]}" >&2
  finish 1
fi

if [[ ${#missing_optional[@]} -gt 0 ]]; then
  printf 'missing optional command: %s\n' "${missing_optional[@]}"
fi

if [[ ${STRICT} -eq 1 ]] && [[ ${#missing_optional[@]} -gt 0 ]]; then
  echo "strict mode validated required build tools; optional capabilities remain unavailable" >&2
fi

if [[ ${ACTIVATE} -eq 1 ]] && ! is_sourced; then
  echo "warning: environment activation was applied only to this process; use 'source applocation/NeuroLink/scripts/setup_neurolink_env.sh --activate' to persist it in the current shell"
fi

finish 0
