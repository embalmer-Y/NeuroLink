#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
USER_LOCAL_ROOT_DEFAULT="${HOME}/.local/zenoh"
PACKAGE_URL_DEFAULT="https://download.eclipse.org/zenoh/zenoh/latest/zenoh-1.7.2-x86_64-unknown-linux-gnu-standalone.zip"
MODE="auto"
USER_LOCAL_ROOT="${USER_LOCAL_ROOT_DEFAULT}"
PACKAGE_URL="${PACKAGE_URL_DEFAULT}"

usage() {
  cat <<'EOF'
Usage: bash applocation/NeuroLink/scripts/install_zenoh_router_wsl.sh

Install the official Eclipse Zenoh Debian package inside WSL Ubuntu/Debian and
verify that `zenohd --help` succeeds.

Options:
  --mode <auto|apt|user-local>   Installation mode (default: auto)
  --user-local-root <path>       Root directory for standalone install fallback
  --package-url <url>            Standalone package URL for user-local install
EOF
}

is_wsl() {
  [[ -n "${WSL_DISTRO_NAME:-}" ]] || grep -qi microsoft /proc/version 2>/dev/null
}

run_privileged() {
  if [[ ${EUID} -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 2
  fi
}

install_user_local() {
  local archive_dir archive_file version_name install_dir current_link bin_dir

  archive_dir="${ROOT_DIR}/build/zenoh-router-downloads"
  mkdir -p "${archive_dir}"
  mkdir -p "${USER_LOCAL_ROOT}"

  archive_file="${archive_dir}/$(basename "${PACKAGE_URL}")"
  version_name="$(basename "${archive_file}" .zip)"
  install_dir="${USER_LOCAL_ROOT}/${version_name}"
  current_link="${USER_LOCAL_ROOT}/current"
  bin_dir="${HOME}/.local/bin"

  require_cmd curl
  require_cmd python3

  if [[ ! -f "${archive_file}" ]]; then
    curl -fsSL "${PACKAGE_URL}" -o "${archive_file}"
  fi

  rm -rf "${install_dir}"
  mkdir -p "${install_dir}"

  python3 - <<'PY' "${archive_file}" "${install_dir}"
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

  ln -sfn "${install_dir}" "${current_link}"
  mkdir -p "${bin_dir}"
  ln -sfn "${current_link}/zenohd" "${bin_dir}/zenohd"
  chmod +x "${current_link}/zenohd" "${bin_dir}/zenohd" 2>/dev/null || true

  "${current_link}/zenohd" --help >/dev/null

  echo "zenoh router installation completed (user-local mode)"
  echo "zenohd=${current_link}/zenohd"
  echo "path_hint=export PATH=\"${bin_dir}:\$PATH\""
}

install_via_apt() {
  require_cmd apt-get
  require_cmd tee

  run_privileged apt-get update
  run_privileged apt-get install -y ca-certificates curl gpg
  run_privileged install -d -m 0755 /etc/apt/keyrings

  curl -fsSL https://download.eclipse.org/zenoh/debian-repo/zenoh-public-key \
    | run_privileged gpg --dearmor --yes --output /etc/apt/keyrings/zenoh-public-key.gpg

  printf '%s\n' \
    'deb [signed-by=/etc/apt/keyrings/zenoh-public-key.gpg] https://download.eclipse.org/zenoh/debian-repo/ /' \
    | run_privileged tee /etc/apt/sources.list.d/zenoh.list >/dev/null

  run_privileged apt-get update
  run_privileged apt-get install -y zenoh

  command -v zenohd >/dev/null 2>&1 || {
    echo "zenohd was not installed successfully" >&2
    exit 1
  }

  zenohd --help >/dev/null

  echo "zenoh router installation completed (apt mode)"
  echo "zenohd=$(command -v zenohd)"
}

has_noninteractive_sudo() {
  sudo -n true >/dev/null 2>&1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --user-local-root)
      USER_LOCAL_ROOT="$2"
      shift 2
      ;;
    --package-url)
      PACKAGE_URL="$2"
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

is_wsl || {
  echo "this installer is intended for WSL Ubuntu/Debian hosts" >&2
  exit 2
}

case "${MODE}" in
  apt)
    install_via_apt
    ;;
  user-local)
    install_user_local
    ;;
  auto)
    if has_noninteractive_sudo; then
      install_via_apt
    else
      echo "sudo is unavailable without a password prompt; falling back to user-local install" >&2
      install_user_local
    fi
    ;;
  *)
    echo "invalid mode: ${MODE}" >&2
    exit 2
    ;;
esac
