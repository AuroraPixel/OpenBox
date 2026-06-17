"""Wildcard pattern matching for permission rules."""
import re


def match(text: str, pattern: str) -> bool:
    """Match text against a wildcard pattern.

    Supports:
    - * matches any sequence of characters (non-greedy)
    - ** matches anything (greedy, including path separators)
    - Exact match when no wildcards
    """
    if pattern == "*" or pattern == "**":
        return True
    if "*" not in pattern:
        return text == pattern

    # Convert glob pattern to regex
    regex_parts = []
    i = 0
    while i < len(pattern):
        if i < len(pattern) - 1 and pattern[i] == "*" and pattern[i + 1] == "*":
            regex_parts.append(".*")
            i += 2
        elif pattern[i] == "*":
            regex_parts.append("[^/]*")
            i += 1
        else:
            regex_parts.append(re.escape(pattern[i]))
            i += 1

    regex = "^" + "".join(regex_parts) + "$"
    return bool(re.match(regex, text))
