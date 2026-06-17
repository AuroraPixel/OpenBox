"""Edit tool: find-and-replace editing in sandbox files.

Implements 9 progressive replacer strategies matching opencode's replacer.ts:
1. SimpleReplacer - exact match
2. LineTrimmedReplacer - right-trim lines
3. BlockAnchorReplacer - Levenshtein similarity on line blocks
4. WhitespaceNormalizedReplacer - collapse whitespace
5. IndentationFlexibleReplacer - strip common indentation
6. EscapeNormalizedReplacer - unescape \n \t etc
7. TrimmedBoundaryReplacer - trim leading/trailing whitespace
8. ContextAwareReplacer - match by first/last line anchors
9. MultiOccurrenceReplacer - yield all exact matches
"""
import re
import unicodedata
from typing import Generator

from pydantic import BaseModel, Field

from tool.tool import ToolResult, ToolContext, define_tool

Replacer = Generator[str, None, None]


def _strip_line_numbers(raw: str) -> str:
    """Strip line number prefixes from read_file output."""
    lines = raw.split("\n")
    content_lines = []
    for line in lines:
        tab_idx = line.find("\t")
        if tab_idx >= 0:
            content_lines.append(line[tab_idx + 1:])
        else:
            content_lines.append(line)
    return "\n".join(content_lines)


# ─── Levenshtein distance for BlockAnchorReplacer ───

def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev[j + 1] + 1
            deletions = curr[j] + 1
            substitutions = prev[j] + (0 if c1 == c2 else 1)
            curr.append(min(insertions, deletions, substitutions))
        prev = curr
    return prev[-1]


def _similarity(s1: str, s2: str) -> float:
    """Return similarity ratio 0..1 using Levenshtein."""
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    return 1.0 - _levenshtein(s1, s2) / max_len


# ─── Replacer Strategies ───

SINGLE_CANDIDATE_SIMILARITY = 0.0
MULTIPLE_CANDIDATES_SIMILARITY = 0.3


def simple_replacer(content: str, find: str) -> Replacer:
    """Strategy 1: exact substring match."""
    if find in content:
        yield find


def line_trimmed_replacer(content: str, find: str) -> Replacer:
    """Strategy 2: trim each line before matching, yield original text."""
    find_lines = find.split("\n")
    content_lines = content.split("\n")
    trimmed_find = [l.strip() for l in find_lines]

    # Try to find a contiguous block in content where trimmed lines match
    for i in range(len(content_lines) - len(find_lines) + 1):
        block = content_lines[i:i + len(find_lines)]
        if [l.strip() for l in block] == trimmed_find:
            yield "\n".join(block)


def block_anchor_replacer(content: str, find: str) -> Replacer:
    """Strategy 3: anchor-based matching using first/last lines + Levenshtein.

    Matches opencode's BlockAnchorReplacer:
    - Uses first and last lines (trimmed) as anchors
    - For single candidate: very relaxed threshold (0.0)
    - For multiple candidates: picks best above 0.3 similarity
    """
    find_lines = find.split("\n")
    if len(find_lines) < 3:
        return

    content_lines = content.split("\n")
    first_anchor = find_lines[0].strip()
    last_anchor = find_lines[-1].strip()

    # Find all blocks bounded by first/last anchors
    candidates = []
    for i in range(len(content_lines)):
        if content_lines[i].strip() != first_anchor:
            continue
        for j in range(i + 2, len(content_lines)):
            if content_lines[j].strip() == last_anchor:
                candidates.append((i, j))
                break  # Only first matching end for each start

    if not candidates:
        return

    if len(candidates) == 1:
        # Single candidate: very relaxed threshold
        start, end = candidates[0]
        block = "\n".join(content_lines[start:end + 1])
        sim = _similarity(find, block)
        if sim >= SINGLE_CANDIDATE_SIMILARITY:
            yield block
    else:
        # Multiple candidates: pick best above threshold
        best_sim = 0.0
        best_block = None
        for start, end in candidates:
            # Compare middle lines using Levenshtein
            middle_find = "\n".join(find_lines[1:-1])
            middle_block = "\n".join(content_lines[start + 1:end])
            sim = _similarity(middle_find, middle_block)
            if sim > best_sim:
                best_sim = sim
                best_block = "\n".join(content_lines[start:end + 1])
        if best_sim >= MULTIPLE_CANDIDATES_SIMILARITY and best_block:
            yield best_block


def whitespace_normalized_replacer(content: str, find: str) -> Replacer:
    """Strategy 4: collapse all whitespace before matching."""
    def normalize_ws(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    normalized_find = normalize_ws(find)
    lines = content.split("\n")

    # Single line matches
    for line in lines:
        if normalize_ws(line) == normalized_find:
            yield line
        else:
            normalized_line = normalize_ws(line)
            if normalized_find in normalized_line:
                # Find the actual substring via regex
                words = find.strip().split()
                if words:
                    pattern = r"\s+".join(re.escape(w) for w in words)
                    m = re.search(pattern, line)
                    if m:
                        yield m.group(0)

    # Multi-line matches
    find_lines = find.split("\n")
    if len(find_lines) > 1:
        for i in range(len(lines) - len(find_lines) + 1):
            block = lines[i:i + len(find_lines)]
            if normalize_ws("\n".join(block)) == normalized_find:
                yield "\n".join(block)


def indentation_flexible_replacer(content: str, find: str) -> Replacer:
    """Strategy 5: strip common leading indentation before comparing."""
    def remove_indent(text: str) -> str:
        text_lines = text.split("\n")
        non_empty = [l for l in text_lines if l.strip()]
        if not non_empty:
            return text
        min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
        return "\n".join(
            l if not l.strip() else l[min_indent:]
            for l in text_lines
        )

    normalized_find = remove_indent(find)
    content_lines = content.split("\n")
    find_lines = find.split("\n")

    for i in range(len(content_lines) - len(find_lines) + 1):
        block = "\n".join(content_lines[i:i + len(find_lines)])
        if remove_indent(block) == normalized_find:
            yield block


def escape_normalized_replacer(content: str, find: str) -> Replacer:
    """Strategy 6: unescape common escape sequences before comparing."""
    _escape_map = {
        "n": "\n", "t": "\t", "r": "\r",
        "'": "'", '"': '"', "`": "`",
        "\\": "\\", "\n": "\n", "$": "$",
    }

    def unescape(s: str) -> str:
        def repl(m):
            ch = m.group(1)
            return _escape_map.get(ch, m.group(0))
        return re.sub(r"\\([ntr'\"`\\\n$])", repl, s)

    unescaped_find = unescape(find)

    # Direct match with unescaped find
    if unescaped_find in content:
        yield unescaped_find

    # Block-level matching
    lines = content.split("\n")
    find_lines = unescaped_find.split("\n")

    for i in range(len(lines) - len(find_lines) + 1):
        block = "\n".join(lines[i:i + len(find_lines)])
        if unescape(block) == unescaped_find:
            yield block


def trimmed_boundary_replacer(content: str, find: str) -> Replacer:
    """Strategy 7: trim leading/trailing whitespace from find."""
    trimmed = find.strip()
    if trimmed == find:
        return  # Already trimmed, skip

    if trimmed in content:
        yield trimmed

    # Block-level: find blocks where trimmed content matches
    lines = content.split("\n")
    find_lines = find.split("\n")

    for i in range(len(lines) - len(find_lines) + 1):
        block = "\n".join(lines[i:i + len(find_lines)])
        if block.strip() == trimmed:
            yield block


def context_aware_replacer(content: str, find: str) -> Replacer:
    """Strategy 8: use first/last lines as anchors, fuzzy-match middle."""
    find_lines = find.split("\n")
    if len(find_lines) < 3:
        return

    # Remove trailing empty line
    if find_lines[-1] == "":
        find_lines = find_lines[:-1]

    content_lines = content.split("\n")
    first_line = find_lines[0].strip()
    last_line = find_lines[-1].strip()

    for i in range(len(content_lines)):
        if content_lines[i].strip() != first_line:
            continue

        for j in range(i + 2, len(content_lines)):
            if content_lines[j].strip() == last_line:
                block_lines = content_lines[i:j + 1]

                # Check if same line count and >= 50% middle lines match
                if len(block_lines) == len(find_lines):
                    matching = 0
                    total_non_empty = 0
                    for k in range(1, len(block_lines) - 1):
                        bl = block_lines[k].strip()
                        fl = find_lines[k].strip()
                        if bl or fl:
                            total_non_empty += 1
                            if bl == fl:
                                matching += 1

                    if total_non_empty == 0 or matching / total_non_empty >= 0.5:
                        yield "\n".join(block_lines)
                        return  # Only first occurrence
                break  # Only check first matching last-line


def multi_occurrence_replacer(content: str, find: str) -> Replacer:
    """Strategy 9: yield all exact occurrences (for replace_all)."""
    start = 0
    while True:
        idx = content.find(find, start)
        if idx < 0:
            break
        yield find
        start = idx + len(find)


# Ordered list of all replacer strategies
ALL_REPLACERS = [
    simple_replacer,
    line_trimmed_replacer,
    block_anchor_replacer,
    whitespace_normalized_replacer,
    indentation_flexible_replacer,
    escape_normalized_replacer,
    trimmed_boundary_replacer,
    context_aware_replacer,
    multi_occurrence_replacer,
]


def replace(content: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Replace old_string with new_string using progressive matching.

    Tries each replacer strategy in order until one finds a match.
    Raises ValueError if not found or ambiguous.
    """
    if old_string == new_string:
        raise ValueError("No changes to apply: oldString and newString are identical.")

    not_found = True

    for replacer in ALL_REPLACERS:
        for search in replacer(content, old_string):
            idx = content.find(search)
            if idx < 0:
                continue
            not_found = False
            if replace_all:
                return content.replace(search, new_string)
            # Check uniqueness: only one occurrence allowed
            last_idx = content.rfind(search)
            if idx != last_idx:
                continue  # Multiple matches, try next replacer
            return content[:idx] + new_string + content[idx + len(search):]

    if not_found:
        raise ValueError(
            "Could not find oldString in the file. "
            "It must match exactly, including whitespace, indentation, and line endings."
        )
    raise ValueError(
        "Found multiple matches for oldString. "
        "Provide more surrounding context to make the match unique."
    )


# ─── Tool Definition ───

class EditArgs(BaseModel):
    file_path: str = Field(description="Path to the file to edit")
    old_string: str = Field(description="The text to find and replace")
    new_string: str = Field(description="The replacement text")
    replace_all: bool = Field(default=False, description="Replace all occurrences")


async def execute(args: EditArgs, ctx: ToolContext) -> ToolResult:
    """Edit a file using find-and-replace with progressive matching."""
    # F9: Check for stale file
    stale_warning = ""
    try:
        from tool.filetime import get_tracker
        tracker = get_tracker(ctx.session_id)
        recorded_mtime = tracker.get(args.file_path)
        if recorded_mtime is not None:
            stat_result = await ctx.sandbox.execute(
                f"stat -c %Y {args.file_path} 2>/dev/null", timeout=5
            )
            if stat_result.exit_code == 0 and stat_result.stdout.strip():
                current_mtime = float(stat_result.stdout.strip())
                if current_mtime != recorded_mtime:
                    stale_warning = (
                        "WARNING: File has been modified since last read. "
                        "The edit was applied, but you should re-read the file to verify.\n"
                    )
    except Exception:
        pass

    try:
        raw_content = await ctx.sandbox.read_file(args.file_path, offset=0, limit=100000)
        content = _strip_line_numbers(raw_content)
    except Exception as e:
        return ToolResult(title=f"Error reading {args.file_path}", output=str(e))

    try:
        new_content = replace(content, args.old_string, args.new_string, args.replace_all)
    except ValueError as e:
        return ToolResult(
            title="Edit failed",
            output=f"{e} (file: {args.file_path})",
        )

    count = content.count(args.old_string) or 1 if args.replace_all else 1

    try:
        await ctx.sandbox.write_file(args.file_path, new_content)
    except Exception as e:
        return ToolResult(title=f"Error writing {args.file_path}", output=str(e))

    output = f"{stale_warning}Replaced {count} occurrence(s)"

    # F6: Auto-format (best-effort)
    try:
        from core.config import get_config
        if getattr(get_config(), "auto_format", True):
            from lsp.format import auto_format
            formatter = await auto_format(ctx.sandbox, args.file_path)
            if formatter:
                output += f"\n(auto-formatted with {formatter})"
    except Exception:
        pass

    # F5: LSP diagnostics (best-effort)
    try:
        from core.config import get_config
        if getattr(get_config(), "lsp_diagnostics", True):
            from lsp.diagnostics import run_diagnostics, format_diagnostics
            diags = await run_diagnostics(ctx.sandbox, args.file_path)
            diag_str = format_diagnostics(diags)
            if diag_str:
                output += diag_str
    except Exception:
        pass

    # F9: Update mtime after write
    try:
        from tool.filetime import get_tracker
        stat_result = await ctx.sandbox.execute(
            f"stat -c %Y {args.file_path} 2>/dev/null", timeout=5
        )
        if stat_result.exit_code == 0 and stat_result.stdout.strip():
            get_tracker(ctx.session_id).record(args.file_path, float(stat_result.stdout.strip()))
    except Exception:
        pass

    return ToolResult(
        title=f"Edited {args.file_path}",
        output=output,
    )


EDIT_DESCRIPTION = """\
Performs exact string replacements in files.

Usage:
- You must use your Read tool at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file.
- When editing text from Read tool output, ensure you preserve the exact indentation (tabs/spaces) as it appears AFTER the line number prefix. The line number prefix format is: line number + tab. Everything after that tab is the actual file content to match. Never include any part of the line number prefix in the old_string or new_string.
- ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required.
- Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.
- The edit will FAIL if `old_string` is not found in the file.
- The edit will FAIL if `old_string` is found multiple times in the file. Either provide a larger string with more surrounding context to make it unique or use `replace_all` to change every instance.
- Use `replace_all` for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance."""

edit_tool = define_tool(
    "edit",
    description=EDIT_DESCRIPTION,
    parameters=EditArgs,
    execute=execute,
)
