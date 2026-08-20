#!/usr/bin/env python3
"""Provision an Alibaba Cloud WUYING desktop as an OpenBox sandbox.

The desktop has no inbound route and is not reachable by SSH from outside its
managed VPC, so every step here goes through `aliyun ecd run-command`, which
executes as root on the desktop. That is also why files are shipped as gzip +
base64 chunks: run-command caps its payload at 16KB.

Idempotent — safe to re-run to repair or upgrade an existing desktop.

    export ALIYUN_PROFILE=...            # optional, uses the CLI's active profile
    python scripts/wuying_bootstrap.py \
        --desktop-id ecd-xxxxxxxxxxxxxxxxx \
        --relay root@203.0.113.10

Prints the WUYING_* values to put in backend/.env when it finishes.

See docs/WUYING_SANDBOX.md for the surrounding architecture.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import pathlib
import secrets
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[2]
MAX_CHUNK = 11_000          # run-command caps command-content at 16KB base64
TUNNEL_PORT = 18_000        # loopback port on the relay host


# --------------------------------------------------------------------------- CLI

def aliyun(*args: str, retries: int = 4) -> str:
    """Call the aliyun CLI, retrying the transient EOF/5xx failures it throws."""
    last = ""
    for attempt in range(retries):
        r = subprocess.run(["aliyun", *args], capture_output=True, text=True)
        out = r.stdout if r.stdout.strip() else r.stderr
        if out.lstrip().startswith("{"):
            return out
        last = out
        if any(m in out for m in ("EOF", "Timeout", "connection")):
            time.sleep(2 * (attempt + 1))
            continue
        return out
    return last


class Desktop:
    """Runs shell on the WUYING desktop via the ECD command channel."""

    def __init__(self, desktop_id: str, region: str):
        self.id, self.region = desktop_id, region

    def run(self, script: str, timeout: int = 300, check: bool = True) -> str:
        out = aliyun(
            "ecd", "run-command", "--api-version", "2020-09-30",
            "--region", self.region, "--biz-region-id", self.region,
            "--desktop-id", self.id, "--type", "RunShellScript",
            "--timeout", str(timeout), "--content-encoding", "Base64",
            "--command-content", base64.b64encode(script.encode()).decode(),
        )
        try:
            invoke_id = json.loads(out)["InvokeId"]
        except Exception:
            raise SystemExit(f"run-command rejected: {out[:400]}")

        for _ in range(max(30, timeout // 4)):
            res = aliyun(
                "ecd", "describe-invocations", "--api-version", "2020-09-30",
                "--region", self.region, "--biz-region-id", self.region,
                "--invoke-id", invoke_id, "--include-output", "true",
            )
            try:
                dt = json.loads(res)["Invocations"][0]["InvokeDesktops"][0]
            except Exception:
                time.sleep(4)
                continue
            if dt.get("InvocationStatus") in ("Success", "Failed", "Timeout"):
                text = base64.b64decode(dt.get("Output") or "").decode("utf-8", "replace")
                if check and dt.get("ExitCode") != 0:
                    raise SystemExit(f"remote command failed (exit {dt.get('ExitCode')}):\n{text}")
                return text
            time.sleep(4)
        raise SystemExit(f"invocation {invoke_id} never settled")

    def put(self, local: pathlib.Path, remote: str, mode: str = "644") -> None:
        b64 = base64.b64encode(gzip.compress(local.read_bytes(), 9)).decode()
        chunks = [b64[i:i + MAX_CHUNK] for i in range(0, len(b64), MAX_CHUNK)]
        stage = f"/tmp/.upload.{pathlib.PurePath(remote).name}.b64"
        print(f"  upload {local.name} -> {remote} ({len(b64) / 1024:.0f}KB, {len(chunks)} chunks)")
        for i, c in enumerate(chunks):
            self.run(f"printf '%s' '{c}' {'>' if i == 0 else '>>'} {stage}", timeout=120)
        self.run(
            f"mkdir -p $(dirname {remote}) && base64 -d {stage} | gunzip > {remote} && "
            f"chmod {mode} {remote} && rm -f {stage}",
            timeout=120,
        )


def ecs_run(instance: str, region: str, script: str, timeout: int = 300) -> str:
    """Runs shell on the relay ECS via Cloud Assistant (no SSH credentials needed)."""
    out = aliyun(
        "ecs", "RunCommand", "--RegionId", region, "--InstanceId.1", instance,
        "--Type", "RunShellScript", "--Timeout", str(timeout),
        "--ContentEncoding", "Base64",
        "--CommandContent", base64.b64encode(script.encode()).decode(),
    )
    try:
        invoke_id = json.loads(out)["InvokeId"]
    except Exception:
        raise SystemExit(f"ecs RunCommand rejected: {out[:400]}")
    for _ in range(90):
        res = aliyun("ecs", "DescribeInvocationResults", "--RegionId", region, "--InvokeId", invoke_id)
        try:
            r = json.loads(res)["Invocation"]["InvocationResults"]["InvocationResult"][0]
        except Exception:
            time.sleep(4)
            continue
        if r.get("InvocationStatus") in ("Success", "Failed", "Timeout"):
            return base64.b64decode(r.get("Output") or "").decode("utf-8", "replace")
        time.sleep(4)
    raise SystemExit("ecs invocation never settled")


# ----------------------------------------------------------------------- stages

def install_runtime(d: Desktop) -> None:
    print("[1/5] runtime")
    # Node comes from the npmmirror binary mirror, not NodeSource: from a
    # mainland VPC, GitHub and NodeSource measure in single-digit KB/s.
    d.run(r"""
set -e
export PATH=/usr/local/bin:$PATH
mkdir -p /workspace /data/skills /data/mcp/logs
if ! command -v node >/dev/null 2>&1; then
  cd /tmp
  VER=$(curl -s -m 30 https://cdn.npmmirror.com/binaries/node/index.json \
        | python3 -c "import sys,json;print([v['version'] for v in json.load(sys.stdin) if v['version'].startswith('v20.')][0])")
  curl -sL -m 600 -o node.tar.xz "https://cdn.npmmirror.com/binaries/node/$VER/node-$VER-linux-x64.tar.xz"
  tar -xJf node.tar.xz && rm -f node.tar.xz
  rm -rf /usr/local/lib/nodejs && mkdir -p /usr/local/lib/nodejs
  mv "node-$VER-linux-x64" /usr/local/lib/nodejs/node
  for b in node npm npx; do ln -sf /usr/local/lib/nodejs/node/bin/$b /usr/local/bin/$b; done
  npm config set registry https://registry.npmmirror.com
fi
echo "python $(python3 -V 2>&1 | cut -d' ' -f2)  node $(node -v)"
""", timeout=900)


def install_action_server(d: Desktop) -> None:
    print("[2/5] action server")
    d.put(REPO / "container" / "action_server.py", "/opt/action_server/action_server.py")
    d.run(r"""
set -e
cat > /opt/action_server/requirements.txt <<'EOF'
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
psutil>=6.0.0
python-multipart>=0.0.12
sse-starlette>=2.0
httpx>=0.27.0
pyyaml>=6.0
websockets>=13.0
mcp>=1.0.0
EOF
pip3 install -q --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
     -r /opt/action_server/requirements.txt
python3 -c "import fastapi,uvicorn,psutil,yaml,sse_starlette,httpx,websockets" && echo "deps ok"
""", timeout=900)


def install_dev_browser(d: Desktop) -> None:
    """The browser-automation relay. Optional, but /dev-browser/start 500s without it."""
    print("[3/5] dev-browser relay")
    tgz = pathlib.Path("/tmp/openbox-dev-browser.tgz")
    subprocess.run(
        ["tar", "czf", str(tgz), "--exclude=node_modules", "--exclude=.git", "dev-browser"],
        cwd=REPO / "container", check=True,
    )
    d.put(tgz, "/tmp/dev-browser.tgz")
    # PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: the relay only imports hono, and the
    # client attaches with connectOverCDP, so no bundled browser is ever used.
    d.run(r"""
set -e
export PATH=/usr/local/bin:$PATH PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
mkdir -p /opt/openbox/skills
rm -rf /opt/openbox/skills/dev-browser
tar xzf /tmp/dev-browser.tgz -C /opt/openbox/skills 2>/dev/null
cd /opt/openbox/skills/dev-browser
npm install --omit=dev --no-audit --no-fund 2>&1 | tail -3
""", timeout=1200)


def install_services(d: Desktop, api_key: str, relay: str) -> str:
    print("[4/5] systemd units")
    pub = d.run(r"""
mkdir -p /root/.ssh && chmod 700 /root/.ssh
[ -f /root/.ssh/openbox_tunnel ] || ssh-keygen -t ed25519 -N "" -C openbox-tunnel -f /root/.ssh/openbox_tunnel -q
cat /root/.ssh/openbox_tunnel.pub
""", timeout=120).strip().splitlines()[-1]

    d.run(f"""
set -e
cat > /etc/systemd/system/openbox-action-server.service <<'EOF'
[Unit]
Description=OpenBox action server (sandbox execution plane)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=SESSION_API_KEY={api_key}
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=/workspace
ExecStart=/usr/bin/python3 /opt/action_server/action_server.py --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/openbox-tunnel.service <<'EOF'
[Unit]
Description=OpenBox reverse tunnel to the relay host
After=network-online.target openbox-action-server.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -N -T \\
  -o StrictHostKeyChecking=accept-new -o ExitOnForwardFailure=yes \\
  -o ServerAliveInterval=20 -o ServerAliveCountMax=3 -o TCPKeepAlive=yes \\
  -i /root/.ssh/openbox_tunnel \\
  -R 127.0.0.1:{TUNNEL_PORT}:127.0.0.1:8000 {relay}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now openbox-action-server
systemctl restart openbox-action-server
sleep 3
systemctl enable --now openbox-tunnel
systemctl restart openbox-tunnel
sleep 4
systemctl is-active openbox-action-server openbox-tunnel | paste -sd' ' -
curl -s -m 5 http://127.0.0.1:8000/alive
""", timeout=300)
    return pub


def authorize_relay(instance: str, region: str, desktop_pub: str) -> None:
    """Install the desktop's key on the relay, scoped to port forwarding only."""
    print("[5/5] relay authorization")
    out = ecs_run(instance, region, f"""
set -e
mkdir -p /root/.ssh && chmod 700 /root/.ssh
touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys
sed -i '/openbox-tunnel/d' /root/.ssh/authorized_keys
# restrict = no shell/agent/x11; permitlisten pins it to the one loopback port.
# Note the explicit port: an empty host in permitlisten means loopback only,
# which is what we want here, but it silently overrides GatewayPorts.
echo 'restrict,port-forwarding,permitlisten="{TUNNEL_PORT}" {desktop_pub}' >> /root/.ssh/authorized_keys
grep -c openbox-tunnel /root/.ssh/authorized_keys
""")
    print(f"  authorized_keys entries: {out.strip().splitlines()[-1] if out.strip() else '?'}")


# ------------------------------------------------------------------------ main

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--desktop-id", required=True, help="ecd-xxxxxxxx")
    p.add_argument("--region", default="cn-hangzhou")
    p.add_argument("--relay", required=True, help="user@host of the relay ECS, e.g. root@203.0.113.10")
    p.add_argument("--relay-instance", help="ECS instance id; enables automatic authorized_keys install")
    p.add_argument("--api-key", help="SESSION_API_KEY to use (generated when omitted)")
    p.add_argument("--skip-dev-browser", action="store_true", help="skip the browser-automation relay")
    args = p.parse_args()

    api_key = args.api_key or secrets.token_hex(24)
    d = Desktop(args.desktop_id, args.region)

    install_runtime(d)
    install_action_server(d)
    if not args.skip_dev_browser:
        install_dev_browser(d)
    pub = install_services(d, api_key, args.relay)

    if args.relay_instance:
        authorize_relay(args.relay_instance, args.region, pub)
    else:
        print("\n  Add this to the relay host's /root/.ssh/authorized_keys:\n")
        print(f'    restrict,port-forwarding,permitlisten="{TUNNEL_PORT}" {pub}\n')

    print(f"""
Done. Put this in backend/.env:

    SANDBOX_PROVIDER=wuying
    WUYING_ENDPOINT=http://127.0.0.1:{TUNNEL_PORT}
    WUYING_API_KEY={api_key}
    WUYING_DESKTOP_ID={args.desktop_id}

Then open the laptop-side tunnel and verify:

    backend/scripts/wuying_tunnel.sh
    curl http://127.0.0.1:{TUNNEL_PORT}/alive
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
