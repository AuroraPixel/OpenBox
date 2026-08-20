# WUYING Cloud Desktop as a Sandbox

`SANDBOX_PROVIDER=wuying` runs the sandbox execution plane on an Alibaba Cloud
WUYING cloud desktop (无影云电脑) instead of a local Docker container or a
Kubernetes pod. The control plane — agent loop, permissions, event bus, the API
— still runs wherever you started the backend.

Use it when you want a persistent, full-fat Linux desktop as the agent's
workspace: it survives restarts, keeps installed tooling between sessions, and
can be attached to over the WUYING client to see what the agent did.

## Contents

- [Why the connection looks the way it does](#why-the-connection-looks-the-way-it-does)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Configuration](#configuration)
- [Daily use](#daily-use)
- [Operations](#operations)
- [Troubleshooting](#troubleshooting)
- [What differs from the Docker and Kubernetes providers](#what-differs-from-the-docker-and-kubernetes-providers)

---

## Why the connection looks the way it does

Two constraints shape the whole design, and neither is obvious:

**1. The desktop has no inbound route.** It sits on a WUYING-managed VPC with a
private address (`10.x.x.x`). There is no elastic IP, no port mapping, and no
security-group rule that will expose a port on it. Outbound works fine; inbound
does not exist. So the desktop has to *dial out* to somewhere the backend can
reach — hence a relay host and a reverse tunnel.

**2. A TUN-mode proxy on the developer machine eats non-standard ports.** Many
mainland-China setups run Clash/Surge-style transparent proxying, which hijacks
all TCP below the application layer. The symptom is confusing: `nc` reports a
port as open even when nothing is listening, and an HTTP request to a
non-standard port hangs and returns nothing. `curl --noproxy` does not help,
because the interception is at the routing layer, not in curl.

Loopback is the one address such proxies never intercept. That is why the
backend talks to `127.0.0.1:18000` and a local `ssh -L` carries it out — rather
than the backend connecting to the relay's public IP directly, which would be
one fewer hop but does not survive the proxy.

The same reasoning is why `SandboxClient` passes `trust_env=False`: without it,
httpx picks up `HTTP_PROXY` from the environment and routes sandbox traffic
through the developer's proxy, which fails with an opaque timeout.

> Even so, prefer the **local `ssh -L`** shape over exposing the relay port
> publicly. Nothing is reachable from the internet, so the action server's API
> key is defence in depth rather than the only thing standing between the
> sandbox and the world.

## Architecture

```
developer laptop                          Alibaba Cloud
┌───────────────────────────┐
│ frontend  :3000           │
│ backend   :8080           │
│   └─ WUYING_ENDPOINT      │
│      http://127.0.0.1:18000
│              │            │
│      ssh -L (wuying_tunnel.sh)
└──────────────┼────────────┘
               │  :22                    ┌──────────────────────────┐
               └────────────────────────►│ relay ECS (public IP)    │
                                         │   sshd, loopback :18000  │
                                         └────────────┬─────────────┘
                                                      │ reverse tunnel
                                                      │ (openbox-tunnel.service)
                                         ┌────────────┴─────────────┐
                                         │ WUYING desktop           │
                                         │   action_server   :8000  │
                                         │   dev-browser relay :9222│
                                         │   /workspace/sessions/…  │
                                         └──────────────────────────┘
```

The relay ECS forwards TCP and nothing else. It never holds an API key, never
sees decrypted traffic beyond what SSH carries, and its `authorized_keys` entry
for the desktop is scoped to a single forwarded port:

```
restrict,port-forwarding,permitlisten="18000" ssh-ed25519 AAAA…
```

`restrict` disables shell, agent forwarding, X11 and PTY allocation;
`port-forwarding` re-enables just the forward; `permitlisten` pins the port.

> **Gotcha:** `permitlisten="18000"` with no host means *loopback only*, and it
> silently overrides `GatewayPorts`. That is what we want here — the port must
> not be public — but if you ever do want a public bind you need
> `permitlisten="0.0.0.0:18000"` *and* `GatewayPorts clientspecified`.

## Prerequisites

| | |
|---|---|
| A WUYING desktop | Linux image. Ubuntu 22.04 is what this was built against. Note its `ecd-…` id. |
| A relay host | Any always-on host with a public IP and sshd that both the desktop and your laptop can reach. An ECS in the same account is the obvious choice. |
| `aliyun` CLI | Configured with credentials that can call `ecd` and (optionally) `ecs`. Check with `aliyun sts GetCallerIdentity`. |
| Outbound from the desktop | Package mirrors must be reachable. The bootstrap uses mainland mirrors throughout. |

The bootstrap needs **no SSH credentials for either machine**: it drives the
desktop through `aliyun ecd run-command` and the relay through `aliyun ecs
RunCommand`, both of which execute as root over the cloud-assistant channel.

## Setup

### 1. Bootstrap the desktop

```bash
python backend/scripts/wuying_bootstrap.py \
    --desktop-id ecd-xxxxxxxxxxxxxxxxx \
    --relay root@<relay-public-ip> \
    --relay-instance i-xxxxxxxxxxxxxxxxx
```

Idempotent — re-run it to repair or upgrade a desktop. It will:

1. Install Node 20 (from the npmmirror binary mirror) and create `/workspace`,
   `/data/skills`, `/data/mcp/logs`.
2. Upload `container/action_server.py` and install its Python dependencies from
   the Tsinghua PyPI mirror.
3. Install the `dev-browser` relay and its npm dependencies. Skip with
   `--skip-dev-browser` if you do not need browser automation.
4. Generate an ed25519 key on the desktop and install
   `openbox-action-server.service` + `openbox-tunnel.service`.
5. Add the desktop's public key to the relay's `authorized_keys`, scoped as
   above. Without `--relay-instance` it prints the line for you to add by hand.

Files are shipped as gzip + base64 chunks because `run-command` caps its payload
at 16KB; `action_server.py` alone is ~85KB.

It prints a generated `SESSION_API_KEY` at the end. Keep it — the backend and the
desktop must agree on it.

### 2. Configure the backend

```bash
# backend/.env
SANDBOX_PROVIDER=wuying
WUYING_ENDPOINT=http://127.0.0.1:18000
WUYING_API_KEY=<the key the bootstrap printed>
WUYING_DESKTOP_ID=ecd-xxxxxxxxxxxxxxxxx
```

### 3. Install the laptop's tunnel key

The laptop needs its own key on the relay, scoped to *opening* the forward
rather than *listening* on it:

```bash
ssh-keygen -t ed25519 -N "" -C openbox-mac -f ~/.ssh/openbox_wuying
```

Then add to the relay's `/root/.ssh/authorized_keys` — via `aliyun ecs
RunCommand` if you have no SSH access:

```
restrict,port-forwarding,permitopen="127.0.0.1:18000" ssh-ed25519 AAAA… openbox-mac
```

Note `permitopen` (limits `-L` destinations), not `permitlisten` (limits `-R`
bind addresses). The desktop and the laptop need different restrictions because
they use opposite halves of the tunnel.

### 4. Open the tunnel and verify

```bash
backend/scripts/wuying_tunnel.sh          # keeps reconnecting; leave it running
curl http://127.0.0.1:18000/alive
```

A healthy response names the desktop:

```json
{"status":"ok","uptime":1319.09,"hostname":"0zd5sxxe1uw10r6","timestamp":"…"}
```

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `SANDBOX_PROVIDER` | `docker` | Set to `wuying`. |
| `WUYING_ENDPOINT` | `http://127.0.0.1:18000` | Where the action server is reachable. Normally the local end of the tunnel. |
| `WUYING_API_KEY` | *(empty)* | Must equal `SESSION_API_KEY` on the desktop. Empty means every request is rejected with 403. |
| `WUYING_DESKTOP_ID` | *(empty)* | `ecd-…`, informational — surfaced in logs and the container listing. |

On startup the provider calls `/alive` and logs the result. A failure is logged
loudly but does **not** abort startup, so the backend still comes up with a dead
sandbox rather than refusing to boot.

## Daily use

Only the laptop-side forward needs starting by hand:

```bash
backend/scripts/wuying_tunnel.sh
```

Everything on the desktop is systemd and self-heals across reboots:

| Unit | Purpose |
|---|---|
| `openbox-action-server.service` | The execution plane on `:8000` |
| `openbox-tunnel.service` | Reverse tunnel to the relay |

The **dev-browser relay is not** a systemd unit. It is started on demand by
`POST /dev-browser/start` (the *Enable Dev Browser* button), and does not come
back on its own after a desktop reboot — press the button again.

## Operations

```bash
# Desktop service state
aliyun ecd run-command --api-version 2020-09-30 \
  --region cn-hangzhou --biz-region-id cn-hangzhou \
  --desktop-id "$WUYING_DESKTOP_ID" --type RunShellScript \
  --command-content 'systemctl status openbox-action-server openbox-tunnel --no-pager'

# Is the reverse tunnel actually bound on the relay?
aliyun ecs RunCommand --RegionId cn-hangzhou --InstanceId.1 <relay-instance> \
  --Type RunShellScript --CommandContent 'ss -lntp | grep 18000'
```

Expect `127.0.0.1:18000` on the relay. `0.0.0.0:18000` means the port is exposed
publicly — check `permitlisten` and `GatewayPorts`.

To rotate the API key, set it on both sides and restart:

```bash
python backend/scripts/wuying_bootstrap.py --desktop-id … --relay … --api-key <new>
# then update WUYING_API_KEY in backend/.env and restart the backend
```

## Troubleshooting

**`WUYING sandbox unreachable at …` on startup**
The laptop-side forward is down. Start `wuying_tunnel.sh`. If it exits
immediately, the relay rejected the key — check `permitopen` in its
`authorized_keys`.

**`/alive` hangs and returns nothing, but `nc` says the port is open**
A TUN-mode proxy is intercepting. Confirm by connecting to a port where nothing
listens; if that also "succeeds", everything is being hijacked. Use the loopback
tunnel rather than the relay's public IP, and make sure nothing has reintroduced
`trust_env=True` on a sandbox HTTP client.

**Every request comes back 403**
`WUYING_API_KEY` does not match `SESSION_API_KEY` in
`openbox-action-server.service`. Re-run the bootstrap with an explicit
`--api-key` to set both.

**Tunnel is up, relay listens, but the backend still cannot reach it**
Check which address the relay bound. `permitlisten` with no host restricts the
bind to loopback, which is correct for this layout but will not serve a backend
connecting from elsewhere.

**`dev-browser not installed in container` (HTTP 500)**
The desktop was bootstrapped with `--skip-dev-browser`, or the npm install
failed. Re-run the bootstrap without that flag.

**Sandbox reachable but browser automation never connects**
`GET /dev-browser/status` should report `{"status":"running","extensionConnected":true}`.
`stopped` means nobody pressed *Enable Dev Browser* (or the desktop rebooted).
`extensionConnected: false` points at the Chrome extension — check its Server URL
under *Advanced* in the popup.

## What differs from the Docker and Kubernetes providers

| | Docker / Kubernetes | WUYING |
|---|---|---|
| Lifecycle | OpenBox creates and destroys containers | The desktop is provisioned out of band; `create` is idempotent, `delete`/`stop` are **no-ops** |
| Isolation | Container per user (Docker) or pod (K8s) | One shared desktop; sessions separated by `/workspace/sessions/<id>` only |
| Reachability | Local port / in-cluster service | Two-hop tunnel |
| Clean slate | Docker starts fresh each boot | State persists — installed packages, files, everything |
| Startup | Docker cleans up; K8s reconciles | Reconciles (health-checks the endpoint) |

The no-op `delete_container` matters: `SandboxManager.release()` destroys a
container once its last session ends. Left alone, that would try to delete
someone's cloud desktop.

The shared-desktop model also means **there is no isolation boundary between
users** beyond the working directory, and the action server does not constrain
paths — an absolute path escapes the session directory. Treat a WUYING sandbox
as single-tenant.
