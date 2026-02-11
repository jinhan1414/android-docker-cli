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
CACHE_DIR="${CACHE_DIR:-$PWD/.cache/issue4}"
COMPOSE_FILE="$WORK_DIR/docker-compose.yml"
LOG_FILE="$WORK_DIR/repro.log"

mkdir -p "$WORK_DIR/data" "$CACHE_DIR"

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
echo "Cache: $CACHE_DIR"

set +e
python -m android_docker.docker_compose_cli --cache-dir "$CACHE_DIR" -f "$COMPOSE_FILE" up 2>&1 | tee "$LOG_FILE"
exit_code=${PIPESTATUS[0]}
set -e

if grep -q "proot error: '/bin/bash' is not executable" "$LOG_FILE"; then
  echo "REPRODUCED: found target error in logs."
  exit 0
fi

echo "NOT REPRODUCED: target error not found."
echo "docker_compose_cli exit code: $exit_code"
echo "log file: $LOG_FILE"
exit 2
