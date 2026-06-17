"""Remote skill index fetching."""
import httpx

from core.log import create_logger

log = create_logger("skill.discovery")


async def fetch_remote_skills(url: str) -> list[dict]:
    """Fetch skill index from a remote URL."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        log.warning(f"Failed to fetch skills from {url}: {e}")
        return []
