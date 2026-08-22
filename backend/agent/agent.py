"""Agent definitions: build, plan, explore, general, compaction, title."""
from dataclasses import dataclass, field


@dataclass
class AgentDef:
    """Definition of an agent."""
    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    max_steps: int = 200
    model: str | None = None  # Override; if None, use session model
    temperature: float = 0.0
    prompt: str | None = None  # Custom system prompt
    mode: str = "primary"  # "primary" or "subagent"
    hidden: bool = False
    permission: list[dict] = field(default_factory=list)
    # Each dict: {"permission": "edit", "pattern": "*", "action": "deny"}


# Note: Build/plan agents use model-specific prompts from agent.prompts.system,
# dynamically selected based on model_id in loop.py's _build_system_prompt().
# PROMPT_BUILD was removed — its output guidelines are now included in all
# model-specific prompts.

PROMPT_EXPLORE = """\
You are a file search specialist. You excel at thoroughly navigating and exploring codebases.

Your strengths:
- Rapidly finding files using glob patterns
- Searching code and text with powerful regex patterns
- Reading and analyzing file contents

Guidelines:
- Use Glob for broad file pattern matching
- Use Grep for searching file contents with regex
- Use Read when you know the specific file path you need to read
- Use Bash for file operations like copying, moving, or listing directory contents
- Adapt your search approach based on the thoroughness level specified by the caller
- Return file paths as absolute paths in your final response
- For clear communication, avoid using emojis
- Do not create any files, or run bash commands that modify the user's system state in any way

Complete the user's search request efficiently and report your findings clearly."""

PROMPT_GENERAL = """\
You are a sub-agent working on a delegated task. Complete the task described \
in the prompt autonomously and return your findings clearly.

Guidelines:
- Focus on the specific task assigned to you
- Use Glob for finding files, Grep for searching content, Read for reading files
- Use Edit/Write for modifications when instructed to write code
- Use web_search/web_fetch for internet research when needed
- Use Bash for system commands and terminal operations
- Return your results in a clear, structured format
- Do not create todo items or task lists — your parent agent manages those
- Be thorough but concise in your response
- When referencing files, use absolute paths"""

PROMPT_TITLE = """\
You are a title generator. You output ONLY a thread title. Nothing else.

<task>
Generate a brief title that would help the user find this conversation later.

Follow all rules in <rules>
Use the <examples> so you know what a good title looks like.
Your output must be:
- A single line
- ≤50 characters
- No explanations
</task>

<rules>
- you MUST use the same language as the user message you are summarizing
- Title must be grammatically correct and read naturally - no word salad
- Never include tool names in the title (e.g. "read tool", "bash tool", "edit tool")
- Focus on the main topic or question the user needs to retrieve
- Vary your phrasing - avoid repetitive patterns like always starting with "Analyzing"
- When a file is mentioned, focus on WHAT the user wants to do WITH the file, not just that they shared it
- Keep exact: technical terms, numbers, filenames, HTTP codes
- Remove: the, this, my, a, an
- Never assume tech stack
- Never use tools
- NEVER respond to questions, just generate a title for the conversation
- The title should NEVER include "summarizing" or "generating" when generating a title
- DO NOT SAY YOU CANNOT GENERATE A TITLE OR COMPLAIN ABOUT THE INPUT
- Always output something meaningful, even if the input is minimal.
- If the user message is short or conversational (e.g. "hello", "lol", "what's up", "hey"):
  → create a title that reflects the user's tone or intent (such as Greeting, Quick check-in, Light chat, Intro message, etc.)
</rules>

<examples>
"debug 500 errors in production" → Debugging production 500 errors
"refactor user service" → Refactoring user service
"why is app.js failing" → app.js failure investigation
"implement rate limiting" → Rate limiting implementation
"how do I connect postgres to my API" → Postgres API connection
"best practices for React hooks" → React hooks best practices
"@src/auth.ts can you add refresh token support" → Auth refresh token support
"@utils/parser.ts this is broken" → Parser bug fix
"look at @config.json" → Config review
"@App.tsx add dark mode toggle" → Dark mode toggle in App
</examples>"""


# Built-in agent definitions
AGENTS: dict[str, AgentDef] = {
    "build": AgentDef(
        name="build",
        description="Default full-access agent for development tasks",
        tools=[
            "bash", "read", "write", "edit", "multiedit", "apply_patch", "glob", "grep",
            "task", "batch", "question", "todo_write", "todo_read",
            "plan_enter", "skill", "web_fetch", "web_search", "cron", "view_image",
            "computer", "browser_mode",
        ],
        max_steps=200,
        # prompt is None — dynamically selected based on model_id
        # via agent.prompts.system.get_system_prompt() in loop.py
        permission=[
            # Override defaults: build agent can ask questions and enter plan mode
            {"permission": "question", "pattern": "*", "action": "allow"},
            {"permission": "plan_enter", "pattern": "*", "action": "allow"},
        ],
    ),
    "plan": AgentDef(
        name="plan",
        description="Read-only agent for analysis and planning",
        tools=[
            "bash", "read", "write", "edit", "multiedit", "apply_patch", "glob", "grep",
            "task", "batch", "question", "plan_exit",
            "web_fetch", "web_search", "view_image", "browser_mode",
        ],
        permission=[
            # Override defaults: plan agent can ask questions and exit plan mode
            {"permission": "question", "pattern": "*", "action": "allow"},
            {"permission": "plan_exit", "pattern": "*", "action": "allow"},
            # Deny all edits (write/edit/apply_patch) by default
            {"permission": "edit", "pattern": "*", "action": "deny"},
            # Allow editing plan files only
            {"permission": "edit", "pattern": "**/.openbox/plans/*.md", "action": "allow"},
            # Note: bash is NOT denied at the permission level (matching opencode).
            # Plan mode constraints are enforced via the system prompt, which tells
            # the agent to only use bash for read-only operations.
        ],
    ),
    "explore": AgentDef(
        name="explore",
        description='Fast agent specialized for exploring codebases. Use this when you need to quickly find files by patterns (eg. "src/components/**/*.tsx"), search code for keywords (eg. "API endpoints"), or answer questions about the codebase (eg. "how do API endpoints work?"). When calling this agent, specify the desired thoroughness level: "quick" for basic searches, "medium" for moderate exploration, or "very thorough" for comprehensive analysis across multiple locations and naming conventions.',
        tools=["bash", "read", "glob", "grep", "web_fetch", "web_search", "view_image"],
        max_steps=20,
        mode="subagent",
        prompt=PROMPT_EXPLORE,
        permission=[
            {"permission": "todoread", "pattern": "*", "action": "deny"},
            {"permission": "todowrite", "pattern": "*", "action": "deny"},
            {"permission": "task", "pattern": "*", "action": "deny"},
        ],
    ),
    "general": AgentDef(
        name="general",
        description="General-purpose agent for researching complex questions and executing multi-step tasks. Use this agent to execute multiple units of work in parallel.",
        tools=[
            "bash", "read", "write", "edit", "multiedit", "glob", "grep",
            "web_fetch", "web_search", "view_image", "computer", "browser_mode",
            # `skill` belongs beside `computer` and `browser_mode`: without it
            # this agent can open a browser and then has no way to drive one,
            # so it falls back to clicking pixels — the exact thing the system
            # prompt forbids. It grants no new authority either, since `bash`
            # can already run anything a skill would instruct; what it adds is
            # the instructions.
            "skill",
        ],
        max_steps=100,
        mode="subagent",
        prompt=PROMPT_GENERAL,
        permission=[
            {"permission": "todoread", "pattern": "*", "action": "deny"},
            {"permission": "todowrite", "pattern": "*", "action": "deny"},
            {"permission": "task", "pattern": "*", "action": "deny"},
        ],
    ),
    "compaction": AgentDef(
        name="compaction",
        description="Context compaction agent (summarizes conversation)",
        tools=[],
        hidden=True,
    ),
    "title": AgentDef(
        name="title",
        description="Title generation agent",
        tools=[],
        hidden=True,
        temperature=0.5,
        permission=[
            {"permission": "*", "pattern": "*", "action": "deny"},
        ],
        prompt=PROMPT_TITLE,
    ),
}


def get_agent(name: str) -> AgentDef:
    """Get an agent definition by name."""
    agent = AGENTS.get(name)
    if not agent:
        raise ValueError(f"Unknown agent: {name}")
    return agent


def list_agents() -> list[AgentDef]:
    """The agents a user may pick to talk to.

    A subagent is not one of them. `explore` and `general` exist to be spawned
    by the task tool with a single self-contained prompt; they have no
    conversational prompt, and `explore` cannot even edit a file. Offering
    them as modes to chat in advertises two dead ends. (opencode draws the
    same line — `mode !== "subagent" && hidden !== true` — everywhere it
    lists agents for a person to choose from.)
    """
    return [a for a in AGENTS.values() if a.mode != "subagent" and not a.hidden]


def list_subagents() -> list[AgentDef]:
    """The agents the task tool may spawn.

    The mirror of {@link list_agents}: anything not exclusively primary.
    Hidden agents are included — compaction and title are spawned by name,
    never chosen — matching opencode's `item.mode !== "primary"`.
    """
    return [a for a in AGENTS.values() if a.mode != "primary"]


def is_subagent(name: str) -> bool:
    """Whether this agent may only run underneath another one."""
    agent = AGENTS.get(name)
    return agent is not None and agent.mode == "subagent"
