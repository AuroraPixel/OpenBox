"""Message and Part Pydantic models matching frontend types/session.ts."""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Literal, Union

from pydantic import BaseModel, Field

from core.identifier import ascending


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class SessionStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    RETRY = "retry"
    ERROR = "error"
    COMPACTING = "compacting"


class ToolStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


# ─── Token Usage ───
class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0
    cache: int = 0
    total: int = 0
    limit: int = 0
    cost: float = 0.0
    context: int = 0  # Current context window usage (last step's input tokens)


# ─── Part Types (matching frontend types/session.ts) ───
class TextPart(BaseModel):
    type: Literal["text"] = "text"
    id: str = Field(default_factory=lambda: ascending("part"))
    text: str = ""
    session_id: str = ""
    message_id: str = ""
    synthetic: bool = False
    ignored: bool = False


class ReasoningPart(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    id: str = Field(default_factory=lambda: ascending("part"))
    text: str = ""
    session_id: str = ""
    message_id: str = ""


class ToolTime(BaseModel):
    start: float = 0
    end: float = 0
    compacted: float | None = None


class ToolStateCompleted(BaseModel):
    status: Literal["completed"] = "completed"
    input: dict[str, Any] = {}
    output: str = ""
    title: str = ""
    metadata: dict[str, Any] = {}
    time: ToolTime = ToolTime()


class ToolStatePending(BaseModel):
    status: Literal["pending"] = "pending"
    input: dict[str, Any] = {}


class ToolStateRunning(BaseModel):
    status: Literal["running"] = "running"
    input: dict[str, Any] = {}
    time: ToolTime = ToolTime()


class ToolStateError(BaseModel):
    status: Literal["error"] = "error"
    input: dict[str, Any] = {}
    error: str = ""
    time: ToolTime = ToolTime()


ToolState = Union[ToolStateCompleted, ToolStatePending, ToolStateRunning, ToolStateError]


class ToolPartData(BaseModel):
    type: Literal["tool"] = "tool"
    id: str = Field(default_factory=lambda: ascending("part"))
    tool: str = ""
    status: ToolStatus = ToolStatus.PENDING
    input: dict[str, Any] | None = None
    output: str | None = None
    error: str | None = None
    title: str | None = None
    call_id: str = ""  # LLM's original tool_call_id (e.g. "call_xxx" for OpenAI, "functions.name:0" for Kimi)
    duration: float | None = None
    session_id: str = ""
    message_id: str = ""
    state: ToolState | None = None


class StepStartPart(BaseModel):
    type: Literal["step-start"] = "step-start"
    id: str = Field(default_factory=lambda: ascending("part"))
    step: int = 0
    session_id: str = ""
    message_id: str = ""
    snapshot: str | None = None


class StepFinishPart(BaseModel):
    type: Literal["step-finish"] = "step-finish"
    id: str = Field(default_factory=lambda: ascending("part"))
    step: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    duration: float = 0.0
    session_id: str = ""
    message_id: str = ""
    snapshot: str | None = None


class CompactionPart(BaseModel):
    type: Literal["compaction"] = "compaction"
    id: str = Field(default_factory=lambda: ascending("part"))
    summary: str | None = None
    auto: bool = False
    # First message kept verbatim after this compaction. None means the summary
    # replaces everything before the boundary (pre-tail behaviour).
    tail_start_id: str | None = None
    session_id: str = ""
    message_id: str = ""


class SubtaskPart(BaseModel):
    type: Literal["subtask"] = "subtask"
    id: str = Field(default_factory=lambda: ascending("part"))
    agent: str = ""
    description: str = ""
    status: ToolStatus = ToolStatus.PENDING
    output: str | None = None
    session_id: str = ""
    message_id: str = ""


class PatchFile(BaseModel):
    path: str
    additions: int = 0
    deletions: int = 0
    status: Literal["added", "modified", "deleted"] = "modified"


class PatchPart(BaseModel):
    type: Literal["patch"] = "patch"
    id: str = Field(default_factory=lambda: ascending("part"))
    files: list[PatchFile] = []
    session_id: str = ""
    message_id: str = ""


class FilePart(BaseModel):
    type: Literal["file"] = "file"
    id: str = Field(default_factory=lambda: ascending("part"))
    path: str = ""
    mime_type: str | None = None
    url: str | None = None
    session_id: str = ""
    message_id: str = ""


class AgentSwitchPart(BaseModel):
    type: Literal["agent"] = "agent"
    id: str = Field(default_factory=lambda: ascending("part"))
    agent: str = ""
    session_id: str = ""
    message_id: str = ""


class RetryPart(BaseModel):
    type: Literal["retry"] = "retry"
    id: str = Field(default_factory=lambda: ascending("part"))
    attempt: int = 0
    reason: str | None = None
    session_id: str = ""
    message_id: str = ""


class PlanPart(BaseModel):
    type: Literal["plan"] = "plan"
    id: str = Field(default_factory=lambda: ascending("part"))
    path: str = ""
    status: Literal["writing", "ready", "accepted", "rejected"] = "writing"
    content: str = ""
    session_id: str = ""
    message_id: str = ""


# Union of all part types
MessagePart = Union[
    TextPart,
    ReasoningPart,
    ToolPartData,
    StepStartPart,
    StepFinishPart,
    CompactionPart,
    SubtaskPart,
    PatchPart,
    FilePart,
    AgentSwitchPart,
    RetryPart,
    PlanPart,
]


# ─── Message Info (stored in storage) ───
class MessageInfo(BaseModel):
    """Internal message metadata stored to disk."""
    id: str
    session_id: str = Field(alias="sessionID", default="")
    role: MessageRole
    # User-specific fields
    agent: str | None = None
    model: str | None = None
    # {"type": "json_schema", "schema": {...}} on a user message; a bare
    # schema dict is also accepted. str is tolerated for older rows.
    format: dict | str | None = None
    system: str | None = None
    variant: str | None = None
    # Assistant-specific fields
    parent_id: str | None = Field(None, alias="parentID")
    model_id: str | None = None
    provider_id: str | None = None
    tokens: TokenUsage | None = None
    cost: float | None = None
    finish: str | None = None
    summary: bool | None = None
    structured: dict | None = None   # captured StructuredOutput payload
    error: dict[str, Any] | None = None

    class Config:
        populate_by_name = True


# ─── Message With Parts (returned to frontend) ───
class MessageWithParts(BaseModel):
    """Message with all its parts, returned to the frontend API."""
    id: str
    session_id: str
    role: MessageRole
    parts: list[MessagePart] = []
    created_at: str = ""
    client_message_id: str | None = None
    agent: str | None = None
    model: str | None = None
    variant: str | None = None
    # Fields needed for compaction boundary detection
    parent_id: str | None = None
    finish: str | None = None
    summary: bool | None = None
    tokens: TokenUsage | None = None
    error: dict | None = None
    # Structured output: the schema the user asked for, and what came back.
    format: dict | str | None = None
    structured: dict | None = None

    class Config:
        populate_by_name = True


# ─── Diff Types ───
class DiffLine(BaseModel):
    type: Literal["add", "del", "context"]
    content: str
    old_line: int | None = None
    new_line: int | None = None


class DiffHunk(BaseModel):
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[DiffLine] = []


class DiffEntry(BaseModel):
    path: str
    additions: int = 0
    deletions: int = 0
    status: Literal["added", "modified", "deleted"] = "modified"
    hunks: list[DiffHunk] = []


# ─── Todo Types ───
class TodoItem(BaseModel):
    id: str = Field(default_factory=lambda: ascending("todo"))
    subject: str = ""
    description: str | None = None
    status: Literal["pending", "in_progress", "completed"] = "pending"
    active_form: str | None = None


class TodoList(BaseModel):
    items: list[TodoItem] = []


# ─── Conversion Functions ───
def to_api_message(info: MessageInfo, parts: list[MessagePart]) -> MessageWithParts:
    """Convert internal message + parts to API response format."""
    return MessageWithParts(
        id=info.id,
        session_id=info.session_id,
        role=info.role,
        parts=parts,
        created_at=id_to_iso(info.id),
        agent=info.agent,
        model=info.model,
        parent_id=info.parent_id,
        finish=info.finish,
        summary=info.summary,
    )


def id_to_iso(id_str: str) -> str:
    """Extract ISO timestamp from a ULID-based ID like 'message_01JXYZ...'."""
    from datetime import datetime, timezone
    try:
        from ulid import ULID
        # Strip prefix (e.g. "message_", "part_")
        ulid_part = id_str.split("_", 1)[1] if "_" in id_str else id_str
        ulid_obj = ULID.from_str(ulid_part)
        dt = datetime.fromtimestamp(ulid_obj.timestamp, tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return id_str


def to_api_part(part: MessagePart) -> dict[str, Any]:
    """Convert a part to frontend-compatible dict."""
    data = part.model_dump(exclude={"session_id", "message_id", "state"})

    # For tool parts, flatten the state into the top-level
    if isinstance(part, ToolPartData) and part.state:
        if hasattr(part.state, "output"):
            data["output"] = part.state.output
        if hasattr(part.state, "error"):
            data["error"] = part.state.error
        if hasattr(part.state, "title"):
            data["title"] = part.state.title
        if hasattr(part.state, "time"):
            data["duration"] = part.state.time.end - part.state.time.start if part.state.time.end else None
        data["status"] = part.state.status
        data["input"] = part.state.input

    return data
