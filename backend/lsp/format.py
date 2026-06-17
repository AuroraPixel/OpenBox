"""Auto-format files in the sandbox using detected formatters.

After edit/write operations, this module attempts to run the project's
configured formatter (prettier, black, gofmt, etc.) on the modified file.
"""
import os

from core.log import create_logger

log = create_logger("lsp.format")

# File extension -> list of formatter commands (tried in order, first available wins)
FORMATTERS: dict[str, list[list[str]]] = {
    ".py":   [["black", "--quiet", "{file}"], ["autopep8", "--in-place", "{file}"]],
    ".js":   [["prettier", "--write", "{file}"], ["biome", "format", "--write", "{file}"]],
    ".ts":   [["prettier", "--write", "{file}"], ["biome", "format", "--write", "{file}"]],
    ".tsx":  [["prettier", "--write", "{file}"]],
    ".jsx":  [["prettier", "--write", "{file}"]],
    ".json": [["prettier", "--write", "{file}"]],
    ".css":  [["prettier", "--write", "{file}"]],
    ".scss": [["prettier", "--write", "{file}"]],
    ".html": [["prettier", "--write", "{file}"]],
    ".vue":  [["prettier", "--write", "{file}"]],
    ".svelte": [["prettier", "--write", "{file}"]],
    ".go":   [["gofmt", "-w", "{file}"]],
    ".rs":   [["rustfmt", "{file}"]],
    ".yaml": [["prettier", "--write", "{file}"]],
    ".yml":  [["prettier", "--write", "{file}"]],
    ".md":   [["prettier", "--write", "{file}"]],
    ".rb":   [["rubocop", "-A", "--fail-level", "fatal", "{file}"]],
    ".java": [["google-java-format", "-i", "{file}"]],
    ".kt":   [["ktlint", "-F", "{file}"]],
    ".swift": [["swiftformat", "{file}"]],
    ".c":    [["clang-format", "-i", "{file}"]],
    ".cpp":  [["clang-format", "-i", "{file}"]],
    ".h":    [["clang-format", "-i", "{file}"]],
}


async def auto_format(sandbox, file_path: str) -> str | None:
    """Format a file in-place inside the sandbox.

    Tries formatters in order for the file's extension.
    Returns the formatter name used, or None if none available.
    """
    _, ext = os.path.splitext(file_path)
    candidates = FORMATTERS.get(ext.lower(), [])
    if not candidates:
        return None

    for cmd_template in candidates:
        cmd = [c.replace("{file}", file_path) for c in cmd_template]
        formatter_name = cmd[0]

        # Check if formatter is installed
        check = await sandbox.execute(f"which {formatter_name} 2>/dev/null", timeout=5)
        if check.exit_code != 0:
            continue

        # Run formatter
        result = await sandbox.execute(" ".join(cmd), timeout=30)
        if result.exit_code == 0:
            log.debug(f"Formatted {file_path} with {formatter_name}")
            return formatter_name
        else:
            stderr = getattr(result, "stderr", "") or ""
            log.debug(f"{formatter_name} failed on {file_path}: {stderr[:200]}")

    return None
