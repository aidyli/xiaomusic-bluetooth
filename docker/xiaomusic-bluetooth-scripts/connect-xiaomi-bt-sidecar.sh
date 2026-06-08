#!/usr/bin/env sh
set -eu

BASE="${BT_SIDECAR_BASE:-http://127.0.0.1:58091}"
TIMEOUT="${BT_SIDECAR_CONNECT_TIMEOUT:-60}"

exec wget -qO- --timeout="$TIMEOUT" "$BASE/connect?async=0"
