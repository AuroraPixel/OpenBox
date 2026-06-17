"""YAML frontmatter parsing for Skill and Command files."""
from typing import Any

try:
    import frontmatter
except ImportError:
    frontmatter = None


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse a markdown file with YAML frontmatter.

    Returns (metadata_dict, body_content).
    """
    if frontmatter:
        post = frontmatter.loads(content)
        return dict(post.metadata), post.content

    # Fallback: manual parsing
    if not content.startswith("---"):
        return {}, content

    end = content.find("---", 3)
    if end == -1:
        return {}, content

    import yaml
    try:
        metadata = yaml.safe_load(content[3:end]) or {}
    except yaml.YAMLError:
        metadata = {}

    body = content[end + 3:].lstrip("\n")
    return metadata, body
