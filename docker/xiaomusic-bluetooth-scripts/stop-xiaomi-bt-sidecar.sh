#!/usr/bin/env sh
set -eu

BASE="${BT_SIDECAR_BASE:-http://127.0.0.1:58091}"
TIMEOUT="${BT_SIDECAR_TIMEOUT:-20}"

exec wget -qO- --timeout="$TIMEOUT" "$BASE/stop"
