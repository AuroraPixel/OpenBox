"""Plan mode prompts — ported from opencode's experimental plan agent."""


def build_plan_reminder(plan_path: str, plan_exists: bool) -> str:
    """Build the full 5-phase workflow reminder for plan mode entry.

    Injected as a system-reminder on the last user message when first
    entering plan mode.  Ported from opencode's prompt.ts experimental path.
    """
    if plan_exists:
        plan_status = (
            f"A plan file already exists at {plan_path}. "
            "You can read it and make incremental edits using the edit tool."
        )
    else:
        plan_status = (
            f"No plan file exists yet. You should create your plan at "
            f"{plan_path} using the write tool."
        )

    return (
        "<system-reminder>\n"
        "Plan mode is active. The user indicated that they do not want you to "
        "execute yet -- you MUST NOT make any edits (with the exception of the "
        "plan file mentioned below), run any non-readonly tools (including "
        "changing configs or making commits), or otherwise make any changes to "
        "the system. This supersedes any other instructions you have received.\n\n"
        "## Plan File Info:\n"
        f"{plan_status}\n"
        "You should build your plan incrementally by writing to or editing this "
        "file. NOTE that this is the only file you are allowed to edit - other "
        "than this you are only allowed to take READ-ONLY actions.\n\n"
        "## Plan Workflow\n\n"
        "### Phase 1: Initial Understanding\n"
        "Goal: Gain a comprehensive understanding of the user's request by "
        "reading through code and asking them questions. Critical: In this "
        "phase you should only use the explore subagent type.\n\n"
        "1. Focus on understanding the user's request and the code associated "
        "with their request\n\n"
        "2. **Launch up to 3 explore agents IN PARALLEL** (single message, "
        "multiple tool calls) to efficiently explore the codebase.\n"
        "   - Use 1 agent when the task is isolated to known files, the user "
        "provided specific file paths, or you're making a small targeted change.\n"
        "   - Use multiple agents when: the scope is uncertain, multiple areas "
        "of the codebase are involved, or you need to understand existing "
        "patterns before planning.\n"
        "   - Quality over quantity - 3 agents maximum, but you should try to "
        "use the minimum number of agents necessary (usually just 1)\n"
        "   - If using multiple agents: Provide each agent with a specific "
        "search focus or area to explore. Example: One agent searches for "
        "existing implementations, another explores related components, a "
        "third investigates testing patterns\n\n"
        "3. After exploring the code, use the question tool to clarify "
        "ambiguities in the user request up front.\n\n"
        "### Phase 2: Design\n"
        "Goal: Design an implementation approach.\n\n"
        "Launch general agent(s) to design the implementation based on the "
        "user's intent and your exploration results from Phase 1.\n\n"
        "You can launch up to 1 agent(s) in parallel.\n\n"
        "**Guidelines:**\n"
        "- **Default**: Launch at least 1 Plan agent for most tasks - it helps "
        "validate your understanding and consider alternatives\n"
        "- **Skip agents**: Only for truly trivial tasks (typo fixes, "
        "single-line changes, simple renames)\n\n"
        "Examples of when to use multiple agents:\n"
        "- The task touches multiple parts of the codebase\n"
        "- It's a large refactor or architectural change\n"
        "- There are many edge cases to consider\n"
        "- You'd benefit from exploring different approaches\n\n"
        "Example perspectives by task type:\n"
        "- New feature: simplicity vs performance vs maintainability\n"
        "- Bug fix: root cause vs workaround vs prevention\n"
        "- Refactoring: minimal change vs clean architecture\n\n"
        "In the agent prompt:\n"
        "- Provide comprehensive background context from Phase 1 exploration "
        "including filenames and code path traces\n"
        "- Describe requirements and constraints\n"
        "- Request a detailed implementation plan\n\n"
        "### Phase 3: Review\n"
        "Goal: Review the plan(s) from Phase 2 and ensure alignment with the "
        "user's intentions.\n"
        "1. Read the critical files identified by agents to deepen your "
        "understanding\n"
        "2. Ensure that the plans align with the user's original request\n"
        "3. Use question tool to clarify any remaining questions with the "
        "user\n\n"
        "### Phase 4: Final Plan\n"
        "Goal: Write your final plan to the plan file (the only file you can "
        "edit).\n"
        "- Include only your recommended approach, not all alternatives\n"
        "- Ensure that the plan file is concise enough to scan quickly, but "
        "detailed enough to execute effectively\n"
        "- Include the paths of critical files to be modified\n"
        "- Include a verification section describing how to test the changes "
        "end-to-end (run the code, use MCP tools, run tests)\n\n"
        "### Phase 5: Call plan_exit tool\n"
        "At the very end of your turn, once you have asked the user questions "
        "and are happy with your final plan file - you should always call "
        "plan_exit to indicate to the user that you are done planning.\n"
        "This is critical - your turn should only end with either asking the "
        "user a question or calling plan_exit. Do not stop unless it's for "
        "these 2 reasons.\n\n"
        "**Important:** Use question tool to clarify requirements/approach, "
        "use plan_exit to request plan approval. Do NOT use question tool to "
        'ask "Is this plan okay?" - that\'s what plan_exit does.\n\n'
        "NOTE: At any point in time through this workflow you should feel free "
        "to ask the user questions or clarifications. Don't make large "
        "assumptions about user intent. The goal is to present a well "
        "researched plan to the user, and tie any loose ends before "
        "implementation begins.\n"
        "</system-reminder>"
    )


# ---------------------------------------------------------------------------
# Build switch prompt (from opencode build-switch.txt)
# ---------------------------------------------------------------------------

BUILD_SWITCH_PROMPT = (
    "<system-reminder>\n"
    "Your operational mode has changed from plan to build.\n"
    "You are no longer in read-only mode.\n"
    "You are permitted to make file changes, run shell commands, "
    "and utilize your arsenal of tools as needed.\n"
    "</system-reminder>"
)


def build_switch_reminder(plan_path: str) -> str:
    """Build the transition reminder when switching from plan to build agent.

    Mirrors opencode: BUILD_SWITCH + plan file reference.
    """
    return (
        BUILD_SWITCH_PROMPT + "\n\n"
        f"A plan file exists at {plan_path}. "
        "You should execute on the plan defined within it"
    )
