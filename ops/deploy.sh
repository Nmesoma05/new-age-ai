#!/usr/bin/env bash
# Trigger a deploy of an exact image on Render via the service's deploy hook (a secret URL).
# Usage: ops/deploy.sh <deploy-hook-url> <image-url>
# [verify on staging] Render deploy hooks accept ?imgURL=<url-encoded image> for image-backed services.
set -euo pipefail
hook="$1"; image="$2"
enc=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$image")
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${hook}&imgURL=${enc}")
[ "$code" -ge 200 ] && [ "$code" -lt 300 ] || { echo "deploy hook returned $code"; exit 1; }
echo "deploy requested: $image"
