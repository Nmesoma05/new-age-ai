#!/usr/bin/env bash
# Wait until the API reports the expected release AND is ready (DB, schema, storage, scanner). 15-minute limit.
# Usage: ops/wait_release.sh <api-base-url> <release>
set -euo pipefail
api="$1"; want="$2"
for _ in $(seq 90); do
  got=$(curl -sf "$api/health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("release",""))' 2>/dev/null || true)
  if [ "$got" = "$want" ] && curl -sf -o /dev/null "$api/ready"; then echo "live and ready: $want"; exit 0; fi
  sleep 10
done
echo "timed out waiting for $want (last seen: ${got:-none})"; exit 1
