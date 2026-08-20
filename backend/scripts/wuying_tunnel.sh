#!/bin/bash
# Opens the tunnel that WUYING_ENDPOINT points at, and keeps it open.
#
#   backend  ->  127.0.0.1:18000            (this forward)
#            ->  relay host 127.0.0.1:18000 (reverse tunnel held by the desktop)
#            ->  WUYING desktop 127.0.0.1:8000   (action server, systemd)
#
# Two hops rather than one because the desktop sits on a WUYING-managed VPC with
# no inbound route, and because a laptop running a TUN-mode proxy will happily
# swallow traffic to non-standard ports — loopback is the one address that is
# never intercepted. See docs/WUYING_SANDBOX.md.
#
# The desktop half is a systemd unit (openbox-tunnel.service) and needs no
# babysitting; only this laptop-side forward has to be started by hand.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${WUYING_ENV_FILE:-$HERE/../.env}"

# Environment-specific values live in backend/.env, which is not committed.
# Only the three keys this script needs are read, and anything already exported
# wins — so an override on the command line still takes effect.
if [ -f "$ENV_FILE" ]; then
  while IFS='=' read -r key value; do
    case "$key" in
      WUYING_RELAY|WUYING_TUNNEL_PORT|WUYING_TUNNEL_KEY)
        [ -z "${!key:-}" ] && export "$key=$value" ;;
    esac
  done < <(grep -E '^[[:space:]]*WUYING_(RELAY|TUNNEL_PORT|TUNNEL_KEY)=' "$ENV_FILE" | sed 's/^[[:space:]]*//')
fi

KEY="${WUYING_TUNNEL_KEY:-$HOME/.ssh/openbox_wuying}"
RELAY="${WUYING_RELAY:-}"
PORT="${WUYING_TUNNEL_PORT:-18000}"

if [ -z "$RELAY" ]; then
  cat >&2 <<'EOF'
error: no relay host configured.

  Set WUYING_RELAY to the user@host of the machine holding the reverse tunnel,
  either in backend/.env or in the environment:

      WUYING_RELAY=root@203.0.113.10

  See docs/WUYING_SANDBOX.md for how the relay fits in.
EOF
  exit 1
fi

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
