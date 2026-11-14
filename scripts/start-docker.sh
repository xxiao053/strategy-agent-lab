#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
if ! docker info --format '{{.OSType}}'; then
  echo 'Start Docker with Linux containers, then retry. Data volumes were not removed.' >&2
  exit 1
fi
case "${1:-start}" in
  start) docker compose build worker controller; docker compose up -d --wait --wait-timeout 90 controller ;;
  stop) docker compose stop; exit 0 ;;
  restart) docker compose restart controller ;;
  *) echo 'Usage: sh scripts/start-docker.sh [start|stop|restart]' >&2; exit 2 ;;
esac
echo 'Open http://127.0.0.1:8765. Stop: sh scripts/start-docker.sh stop. Restart: sh scripts/start-docker.sh restart. Data is preserved.'
