#!/usr/bin/env sh
set -eu

URL="${1:?missing audio url}"
BASE="${BT_SIDECAR_BASE:-http://127.0.0.1:58091}"
TIMEOUT="${BT_SIDECAR_TIMEOUT:-20}"

ENC="$(python3 - "$URL" <<'PY'
import sys
import urllib.parse
print(urllib.parse.quote(sys.argv[1], safe=''))
PY
)"

exec wget -qO- --timeout="$TIMEOUT" "$BASE/play?url=$ENC"
