"""LSP diagnostics: check files for errors after edit/write.

Runs language-specific compile/lint checks inside the sandbox and parses
the output into structured diagnostics that get injected into tool results,
allowing the LLM to self-correct errors.
"""
import os
import re
from dataclasses import dataclass

from core.log import create_logger

log = create_logger("lsp.diagnostics")


@dataclass
class Diagnostic:
    line: int
    column: int
    severity: str  # "error", "warning", "info"
    message: str
    source: str


# File extension -> list of check commands (first one that produces output wins)
LANGUAGE_CHECKS: dict[str, list[str]] = {
    ".py": [
        "python3 -m py_compile {file} 2>&1",
    ],
    ".ts": [
        "npx tsc --noEmit --pretty false {file} 2>&1",
    ],
    ".tsx": [
        "npx tsc --noEmit --pretty false {file} 2>&1",
    ],
    ".js": [
        "node --check {file} 2>&1",
    ],
    ".go": [
        "go vet {file} 2>&1",
    ],
    ".rs": [
        "cargo check --message-format=short 2>&1 | head -20",
    ],
}

# Common patterns for parsing compiler/linter output
# file:line:col: severity: message
_PATTERN_COLON = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<sev>error|warning|info|note):\s*(?P<msg>.+)$"
)
# file(line,col): error TSxxxx: message
_PATTERN_PAREN = re.compile(
    r"^(?P<file>[^(]+)\((?P<line>\d+),(?P<col>\d+)\):\s*(?P<sev>error|warning)\s+\w+:\s*(?P<msg>.+)$"
)
# SyntaxError: ...  (Python py_compile output)
_PATTERN_PYTHON = re.compile(
    r"^\s*File \"(?P<file>[^\"]+)\", line (?P<line>\d+)"
)
_PATTERN_PYTHON_MSG = re.compile(
    r"^(?:SyntaxError|IndentationError|TabError):\s*(?P<msg>.+)$"
)


def _parse_output(output: str, file_path: str) -> list[Diagnostic]:
    """Parse compiler/linter output into Diagnostic objects."""
    diagnostics = []
    lines = output.strip().split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Try colon pattern: file:line:col: error: msg
        m = _PATTERN_COLON.match(line)
        if m:
            diagnostics.append(Diagnostic(
                line=int(m.group("line")),
                column=int(m.group("col")),
                severity=m.group("sev"),
                message=m.group("msg").strip(),
                source="compiler",
            ))
            i += 1
            continue

        # Try paren pattern: file(line,col): error TSxxxx: msg
        m = _PATTERN_PAREN.match(line)
        if m:
            diagnostics.append(Diagnostic(
                line=int(m.group("line")),
                column=int(m.group("col")),
                severity=m.group("sev"),
                message=m.group("msg").strip(),
                source="tsc",
            ))
            i += 1
            continue

        # Try Python pattern: File "...", line N + next line SyntaxError
        m = _PATTERN_PYTHON.match(line)
        if m:
            py_line = int(m.group("line"))
            # Look ahead for the error message
            msg = "Syntax error"
            for j in range(i + 1, min(i + 4, len(lines))):
                m2 = _PATTERN_PYTHON_MSG.match(lines[j].strip())
                if m2:
                    msg = m2.group("msg")
                    break
            diagnostics.append(Diagnostic(
                line=py_line, column=0, severity="error",
                message=msg, source="python",
            ))
            i += 1
            continue

        # Fallback: if line contains "error" (case-insensitive), treat as generic error
        if "error" in line.lower() and file_path.split("/")[-1] in line:
            diagnostics.append(Diagnostic(
                line=0, column=0, severity="error",
                message=line[:200], source="generic",
            ))

        i += 1

    return diagnostics


async def run_diagnostics(sandbox, file_path: str, timeout: int = 15) -> list[Diagnostic]:
    """Run language-specific diagnostics on a file in the sandbox."""
    _, ext = os.path.splitext(file_path)
    checks = LANGUAGE_CHECKS.get(ext.lower(), [])
    if not checks:
        return []

    for cmd_template in checks:
        cmd = cmd_template.replace("{file}", file_path)
        try:
            result = await sandbox.execute(cmd, timeout=timeout)
            if result.exit_code != 0:
                output = (getattr(result, "stdout", "") or "") + (getattr(result, "stderr", "") or "")
                return _parse_output(output, file_path)
        except Exception as e:
            log.debug(f"Diagnostic check failed for {file_path}: {e}")

    return []


def format_diagnostics(diagnostics: list[Diagnostic]) -> str:
    """Format diagnostics as a string for tool output."""
    if not diagnostics:
        return ""

    errors = [d for d in diagnostics if d.severity == "error"]
    warnings = [d for d in diagnostics if d.severity == "warning"]

    lines = []
    if errors:
        lines.append(f"\n--- {len(errors)} error(s) detected ---")
        for e in errors[:10]:
            loc = f"Line {e.line}" if e.line > 0 else "Unknown location"
            lines.append(f"  {loc}: {e.message}")

    if warnings:
        lines.append(f"\n--- {len(warnings)} warning(s) ---")
        for w in warnings[:5]:
            loc = f"Line {w.line}" if w.line > 0 else "Unknown location"
            lines.append(f"  {loc}: {w.message}")

    return "\n".join(lines)
