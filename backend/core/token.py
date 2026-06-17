"""Simple token estimation."""

CHARS_PER_TOKEN = 4


def token_estimate(text: str | None) -> int:
    """Estimate token count from text length.
    Simple heuristic: ~4 chars per token."""
    return max(0, round(len(text or "") / CHARS_PER_TOKEN))
