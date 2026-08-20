#!/bin/bash
# Opens the tunnel that WUYING_ENDPOINT points at, and keeps it open.
#
#   backend  ->  127.0.0.1:18000            (this forward)
#            ->  ECS relay 127.0.0.1:18000  (reverse tunnel held by the desktop)
#            ->  WUYING desktop 127.0.0.1:8000   (action server, systemd)
#
# Two hops rather than one because the desktop sits on a WUYING-managed VPC with
# no inbound route, and because a laptop running a TUN-mode proxy will happily
# swallow traffic to non-standard ports — loopback is the one address that is
# never intercepted.
#
# The desktop half is a systemd unit (openbox-tunnel.service) and needs no
# babysitting; only this laptop-side forward has to be started by hand.
set -euo pipefail

KEY="${WUYING_TUNNEL_KEY:-$HOME/.ssh/openbox_wuying}"
RELAY="${WUYING_RELAY:-root@47.110.66.89}"
PORT="${WUYING_TUNNEL_PORT:-18000}"

if [ ! -f "$KEY" ]; then
  echo "error: ssh key not found at $KEY" >&2
  echo "       set WUYING_TUNNEL_KEY, or install the key that the relay's" >&2
  echo "       authorized_keys was provisioned with." >&2
  exit 1
fi

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "port $PORT is already listening — tunnel appears to be up already"
  exit 0
fi

echo "forwarding 127.0.0.1:$PORT -> $RELAY -> WUYING desktop:8000  (ctrl-c to stop)"
while true; do
  ssh -N -T \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=20 -o ServerAliveCountMax=3 \
    -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=15 \
    -i "$KEY" \
    -L "127.0.0.1:${PORT}:127.0.0.1:${PORT}" \
    "$RELAY" || true
  echo "[$(date +%H:%M:%S)] tunnel dropped, reconnecting in 5s" >&2
  sleep 5
done
