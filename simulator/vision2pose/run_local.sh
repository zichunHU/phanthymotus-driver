#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")" && pwd)"
driver_root="$(cd "$project_dir/../.." && pwd)"
export PHANTHYMOTUS_CORE="${PHANTHYMOTUS_CORE:-$driver_root/../phanthymotus}"
export MOTUS_PORT="${MOTUS_PORT:-15678}"
compose=(docker compose -f "$project_dir/compose.yaml")

case "${1:-start}" in
  start)
    if [[ ! -f "$PHANTHYMOTUS_CORE/agent-core/deploy/dds-local.xml" ]]; then
      printf 'Core checkout not found at %s. Set PHANTHYMOTUS_CORE to its absolute path.\n' "$PHANTHYMOTUS_CORE" >&2
      exit 2
    fi
    python3 "$project_dir/prepare_assets.py"
    "${compose[@]}" build vision2pose
    "${compose[@]}" up -d --no-build --wait pose3d vision2pose
    printf 'Motus http://127.0.0.1:%s\n' "$MOTUS_PORT"
    ;;
  stop) "${compose[@]}" stop ;;
  status) "${compose[@]}" ps ;;
  logs) "${compose[@]}" logs --tail=100 ;;
  *) printf 'Usage: bash run_local.sh [start|stop|status|logs]\n' >&2; exit 2 ;;
esac
