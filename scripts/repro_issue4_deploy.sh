#!/usr/bin/env bash
set -euo pipefail

# Reproduce issue #4 from deployment flow:
# "proot error: '/bin/bash' is not executable"

if [ "$(id -u)" -eq 0 ]; then
  echo "ERROR: this script must run as non-root to mirror Android constraints."
  exit 1
fi

IMAGE="${IMAGE:-registry.cn-hangzhou.aliyuncs.com/hass-panel/hass-panel:latest}"
WORK_DIR="${WORK_DIR:-$PWD/.repro-issue4}"
REPRO_TIMEOUT_SECONDS="${REPRO_TIMEOUT_SECONDS:-240}"
COMPOSE_FILE="$WORK_DIR/docker-compose.yml"
LOG_FILE="$WORK_DIR/repro.log"

if ! command -v docker-compose >/dev/null 2>&1; then
  echo "ERROR: docker-compose command not found."
  echo "Install with README command first:"
  echo "  INSTALL_VERSION=main curl -sSL https://raw.githubusercontent.com/jinhan1414/android-docker-cli/main/scripts/install.sh | sh"
  exit 1
fi

mkdir -p "$WORK_DIR/data"

cat > "$COMPOSE_FILE" <<YAML
version: '3'
services:
  hass-panel:
    container_name: hass-panel
    image: ${IMAGE}
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./data:/config/hass-panel
YAML

# Simulate Android/Termux indicators used by ProotRunner._is_android_environment().
export ANDROID_DATA=/data
export TERMUX_VERSION=ci-simulated
export PREFIX=/data/data/com.termux/files/usr
export ANDROID_DOCKER_FAKE_ROOT=1
export ANDROID_DOCKER_LINK2SYMLINK=0

echo "== Reproducing issue #4 =="
echo "Image: $IMAGE"
echo "Compose: $COMPOSE_FILE"
echo "Timeout: ${REPRO_TIMEOUT_SECONDS}s"

set +e
if command -v timeout >/dev/null 2>&1; then
  timeout --kill-after=20s "${REPRO_TIMEOUT_SECONDS}s" \
    docker-compose -f "$COMPOSE_FILE" up >"$LOG_FILE" 2>&1
else
  docker-compose -f "$COMPOSE_FILE" up >"$LOG_FILE" 2>&1
fi
exit_code=$?
set -e

echo "---- deploy log (tail -n 120) ----"
tail -n 120 "$LOG_FILE" || true
echo "---- end deploy log ----"

if grep -q "proot error: '/bin/bash' is not executable" "$LOG_FILE"; then
  echo "REPRODUCED: found target error in logs."
  exit 0
fi

echo "NOT REPRODUCED: target error not found."
echo "docker-compose exit code: $exit_code"
if [ "$exit_code" -eq 124 ] || [ "$exit_code" -eq 137 ]; then
  echo "compose up reached timeout; treating as non-reproduced."
fi
echo "log file: $LOG_FILE"
exit 2
