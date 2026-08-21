"""Presigned-URL client for the asset-transfer OSS bucket.

Files move browser→OSS and OSS→cloud desktop directly, so bytes never squeeze
through the backend or the sandbox tunnel — the backend only signs URLs and
keeps the upload records. Signing is hand-written OSS V1 (HMAC-SHA1 query
signature), the same ~40 lines the reference integration in bossip uses; a
whole SDK buys nothing here.

Signing trap (inherited from bossip, verified there the hard way): the
Content-Type line of the string-to-sign must match what the client actually
sends. PUT URLs are therefore signed WITH the declared mime and the uploader
must send exactly that header; GET/HEAD sign the line empty.
"""
import base64
import hashlib
import hmac
import time
from urllib.parse import quote

from core.aliyun import AliyunCredentialsError, load_credentials
from core.config import get_config


class OssNotConfigured(Exception):
    pass


class OssClient:
    def __init__(self, bucket: str, region: str, endpoint: str, key_id: str, key_secret: str):
        self.bucket = bucket
        self.region = region
        self.endpoint = endpoint
        self._key_id = key_id
        self._key_secret = key_secret

    @property
    def host(self) -> str:
        return f"{self.bucket}.{self.endpoint}"

    def _sign(self, string_to_sign: str) -> str:
        digest = hmac.new(self._key_secret.encode(), string_to_sign.encode(), hashlib.sha1).digest()
        return base64.b64encode(digest).decode()

    def _presign(
        self,
        method: str,
        key: str,
        expires_sec: int,
        content_type: str = "",
        subresource: dict[str, str] | None = None,
    ) -> str:
        expires = int(time.time()) + expires_sec
        sub = subresource or {}
        canonical = f"/{self.bucket}/{key}"
        if sub:
            canonical += "?" + "&".join(f"{k}={sub[k]}" for k in sorted(sub))
        string_to_sign = f"{method}\n\n{content_type}\n{expires}\n{canonical}"
        signature = self._sign(string_to_sign)
        query = [f"{quote(k)}={quote(sub[k])}" for k in sorted(sub)]
        query += [
            f"OSSAccessKeyId={quote(self._key_id)}",
            f"Expires={expires}",
            f"Signature={quote(signature)}",
        ]
        encoded_key = quote(key, safe="/")
        return f"https://{self.host}/{encoded_key}?{'&'.join(query)}"

    def presign_put(self, key: str, content_type: str, expires_sec: int = 1800) -> str:
        """Direct browser upload; the client must send exactly this Content-Type."""
        return self._presign("PUT", key, expires_sec, content_type=content_type)

    def presign_get(self, key: str, expires_sec: int = 3600, download_name: str | None = None) -> str:
        sub = None
        if download_name:
            sub = {"response-content-disposition": f'attachment; filename="{download_name}"'}
        return self._presign("GET", key, expires_sec, subresource=sub)

    def presign_head(self, key: str, expires_sec: int = 120) -> str:
        return self._presign("HEAD", key, expires_sec)

    async def head(self, key: str) -> dict | None:
        """Existence + size check after a client-side upload. None if absent."""
        import httpx

        url = self.presign_head(key)
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.head(url)
        if resp.status_code == 200:
            return {
                "size": int(resp.headers.get("content-length", 0)),
                "mime": resp.headers.get("content-type", ""),
            }
        return None


def get_oss() -> OssClient:
    """The configured asset bucket, or raises OssNotConfigured (→ 503)."""
    config = get_config()
    bucket = config.oss_bucket
    if not bucket:
        raise OssNotConfigured("OSS_BUCKET is not set")
    region = config.oss_region
    endpoint = config.oss_endpoint or f"oss-{region}.aliyuncs.com"
    try:
        creds = load_credentials()
    except AliyunCredentialsError as e:
        raise OssNotConfigured(str(e))
    return OssClient(bucket, region, endpoint, creds["access_key_id"], creds["access_key_secret"])
