#!/bin/bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y git curl python3 python3-pip python3-venv

if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

if ! command -v codex >/dev/null 2>&1; then
  npm install -g @openai/codex
fi

repo_url="${JAKAL_FLOW_GIT_URL:-https://github.com/Ahnd6474/Jakal-flow.git}"
repo_ref="${JAKAL_FLOW_GIT_REF:-main}"
install_root="/opt/jakal-flow"

rm -rf "${install_root}"
if [ -d "${repo_url}" ] && [ -f "${repo_url}/pyproject.toml" ]; then
  python3 -m pip install --break-system-packages -e "${repo_url}"
else
  git clone --depth 1 --branch "${repo_ref}" "${repo_url}" "${install_root}"
  python3 -m pip install --break-system-packages -e "${install_root}"
fi
