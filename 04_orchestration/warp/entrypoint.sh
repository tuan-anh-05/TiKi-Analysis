#!/bin/bash
set -e

mkdir -p /run/cloudflare-warp /var/lib/cloudflare-warp

echo "[WARP] Starting warp-svc daemon..."
warp-svc &
WARP_SVC_PID=$!

echo "[WARP] Waiting for warp-svc socket..."
for i in $(seq 1 30); do
    if warp-cli --accept-tos status >/dev/null 2>&1 || [ -S /run/cloudflare-warp/warp_service ]; then
        break
    fi
    sleep 1
done

echo "[WARP] Registering client..."
warp-cli --accept-tos registration new || true

echo "[WARP] Setting proxy mode to SOCKS5 on port ${WARP_PORT:-1080}..."
warp-cli --accept-tos mode proxy
warp-cli --accept-tos proxy port ${WARP_PORT:-1080}

echo "[WARP] Connecting to Cloudflare..."
warp-cli --accept-tos connect

for i in $(seq 1 30); do
    STATUS=$(warp-cli --accept-tos status 2>/dev/null || true)
    if echo "$STATUS" | grep -qi "Connected"; then
        echo "[WARP] Connected successfully!"
        break
    fi
    sleep 1
done

echo "[WARP] Starting Rotate API on port ${API_PORT:-8000}..."
python3 /rotate_api.py &
API_PID=$!

trap "kill $API_PID $WARP_SVC_PID; exit 0" SIGTERM SIGINT

wait $WARP_SVC_PID
