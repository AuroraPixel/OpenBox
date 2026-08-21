"""Alibaba Cloud access-key loading, shared by the ECD (cloud desktop) and
OSS (asset transfer) integrations.

Order: ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET env, then the aliyun CLI profile
(~/.aliyun/config.json) — the same chain the reference integration in bossip
uses, so a dev machine with `aliyun configure` just works.
"""
import json
import os
from pathlib import Path


class AliyunCredentialsError(Exception):
    pass


def load_credentials() -> dict:
    key_id = (os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID") or os.environ.get("ALICLOUD_ACCESS_KEY_ID") or "").strip()
    key_secret = (
        os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET") or os.environ.get("ALICLOUD_ACCESS_KEY_SECRET") or ""
    ).strip()
    if key_id and key_secret:
        return {"access_key_id": key_id, "access_key_secret": key_secret}

    config_path = Path(os.environ.get("ALIYUN_CLI_CONFIG") or Path.home() / ".aliyun" / "config.json")
    try:
        parsed = json.loads(config_path.read_text())
    except FileNotFoundError:
        raise AliyunCredentialsError("No Alibaba Cloud credentials (env or aliyun CLI profile)")
    profiles = parsed.get("profiles") or []
    wanted = os.environ.get("ALIBABA_CLOUD_PROFILE") or parsed.get("current") or "default"
    profile = next((p for p in profiles if p.get("name") == wanted), None)
    if not profile or not profile.get("access_key_id") or not profile.get("access_key_secret"):
        raise AliyunCredentialsError(f"aliyun CLI profile '{wanted}' has no usable access key")
    creds = {"access_key_id": profile["access_key_id"], "access_key_secret": profile["access_key_secret"]}
    if profile.get("sts_token"):
        creds["security_token"] = profile["sts_token"]
    return creds
