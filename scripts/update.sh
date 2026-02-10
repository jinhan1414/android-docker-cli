#!/data/data/com.termux/files/usr/bin/sh

# Update helper for Termux: reinstall android-docker-cli to the latest GitHub release.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/main/scripts/update.sh | sh
#
# Notes:
# - This intentionally reuses scripts/install.sh so update behavior stays consistent.

set -e

OWNER_REPO="jinhan1414/android-docker-cli"
API_URL="https://api.github.com/repos/${OWNER_REPO}/releases/latest"
INSTALL_URL="https://raw.githubusercontent.com/${OWNER_REPO}/main/scripts/install.sh"

echo "[INFO] Checking latest release for ${OWNER_REPO}..."
TAG="$(curl -fsSL "${API_URL}" | python -c "import sys, json; print(json.load(sys.stdin)['tag_name'])")"

if [ -z "${TAG}" ]; then
  echo "[ERROR] Failed to determine latest release tag." >&2
  exit 1
fi

echo "[INFO] Updating to ${TAG}..."
INSTALL_VERSION="${TAG}" curl -fsSL "${INSTALL_URL}" | sh

