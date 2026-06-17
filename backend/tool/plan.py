"""Plan mode tools: switch between build and plan agents."""
from pydantic import BaseModel

from core.log import create_logger
from tool.tool import ToolResult, ToolContext, define_tool

log = create_logger("tool.plan")

PLAN_EXIT_DESCRIPTION = """\
Use this tool when you have completed the planning phase and are ready to exit plan agent.

This tool will ask the user if they want to switch to build agent to start implementing the plan.

Call this tool:
- After you have written a complete plan to the plan file
- After you have clarified any questions with the user
- When you are confident the plan is ready for implementation

Do NOT call this tool:
- Before you have created or finalized the plan
- If you still have unanswered questions about the implementation
- If the user has indicated they want to continue planning\
"""


class PlanRejectedError(Exception):
    """Raised when the user rejects the plan transition."""
    pass


PLAN_ENTER_DESCRIPTION = """\
Use this tool to suggest switching to plan agent when the user's request would benefit from planning before implementation.

If they explicitly mention wanting to create a plan ALWAYS call this tool first.

This tool will ask the user if they want to switch to plan agent.

Call this tool when:
- The user's request is complex and would benefit from planning first
- You want to research and design before making changes
- The task involves multiple files or significant architectural decisions

Do NOT call this tool:
- For simple, straightforward tasks
- When the user explicitly wants immediate implementation\
"""


class PlanEnterArgs(BaseModel):
    pass


async def execute_enter(args: PlanEnterArgs, ctx: ToolContext) -> ToolResult:
    """Ask user for confirmation, then create a synthetic plan message."""
    from question.question import ask, Question, QuestionOption
    from session.session import get_session, plan_path, create_user_message

    session = await get_session(ctx.session_id, user_id=ctx.user_id or "default")
    if session:
        pp = plan_path(session)
        rel_path = pp.replace("/workspace/", "")
    else:
        rel_path = ".openbox/plans/plan.md"

    answers = await ask(
        session_id=ctx.session_id,
        questions=[Question(
            question=(
                f"Would you like to switch to the plan agent and "
                f"create a plan saved to {rel_path}?"
            ),
            header="Plan Mode",
            options=[
                QuestionOption(
                    label="Yes",
                    description="Switch to plan agent for research and planning",
                ),
                QuestionOption(
                    label="No",
                    description="Stay with build agent to continue making changes",
                ),
            ],
            custom=False,
        )],
        tool={"messageID": ctx.message_id, "callID": ctx.part_id} if ctx.part_id else None,
    )

    first_answer = answers[0][0] if answers and answers[0] else "No"
    if first_answer == "No":
        raise PlanRejectedError("User chose to stay in build mode.")

    # Create a synthetic user message that switches the agent to plan.
    await create_user_message(
        session_id=ctx.session_id,
        text="User has requested to enter plan mode. Switch to plan mode and begin planning.",
        agent="plan",
        model=session.model if session else None,
        synthetic=True,
        user_id=ctx.user_id or "default",
    )

    return ToolResult(
        title="Switching to plan agent",
        output=(
            f"User confirmed to switch to plan mode. A new message has been "
            f"created to switch you to plan mode. The plan file will be at "
            f"{rel_path}. Begin planning."
        ),
        metadata={},
    )


plan_enter_tool = define_tool(
    "plan_enter",
    description=PLAN_ENTER_DESCRIPTION,
    parameters=PlanEnterArgs,
    execute=execute_enter,
    sandbox_required=False,
)


async def _update_plan_part_status(session_id: str, status: str, message_id: str = "") -> None:
    """Find the most recent PlanPart in the session and update its status.

    If no PlanPart exists yet, create one by extracting content from write tool
    parts that wrote to the plan file.
    """
    from session.session import get_messages, save_part, get_session, plan_path
    from models.message import PlanPart

    messages = await get_messages(session_id)
    # Search from most recent message backward for existing PlanPart
    for msg in reversed(messages):
        for part in reversed(msg.parts):
            part_data = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else part)
            if isinstance(part_data, dict) and part_data.get("type") == "plan":
                plan_part = PlanPart(
                    id=part_data["id"],
                    path=part_data.get("path", ""),
                    status=status,
                    content=part_data.get("content", ""),
                    session_id=session_id,
                    message_id=part_data.get("message_id", msg.id),
                )
                await save_part(plan_part, is_new=False)
                log.info(f"Updated PlanPart {plan_part.id} status to '{status}'")
                return

    # No PlanPart found — create one from write tool content
    session = await get_session(session_id, user_id=ctx.user_id or "default")
    plan_file = plan_path(session) if session else ""
    content = ""
    target_msg_id = message_id

    for msg in reversed(messages):
        for part in reversed(msg.parts):
            part_data = part if isinstance(part, dict) else (part.model_dump() if hasattr(part, "model_dump") else part)
            if (
                isinstance(part_data, dict)
                and part_data.get("type") == "tool"
                and part_data.get("tool") == "write"
                and ".openbox/plans/" in (part_data.get("input") or {}).get("file_path", "")
            ):
                content = (part_data.get("input") or {}).get("content", "")
                if not target_msg_id:
                    target_msg_id = msg.id
                break
        if content:
            break

    if content:
        plan_part = PlanPart(
            path=plan_file,
            status=status,
            content=content,
            session_id=session_id,
            message_id=target_msg_id,
        )
        await save_part(plan_part, is_new=True)
        log.info(f"Created PlanPart with status '{status}' from write tool content ({len(content)} chars)")
    else:
        log.warning(f"No PlanPart found in session {session_id} to update status to '{status}'")


class PlanExitArgs(BaseModel):
    pass


async def execute_exit(args: PlanExitArgs, ctx: ToolContext) -> ToolResult:
    """Mark plan as ready for user review. Does NOT block — user accepts/rejects via PlanCard UI."""
    # Mark plan as ready
    await _update_plan_part_status(ctx.session_id, "ready", message_id=ctx.message_id)

    return ToolResult(
        title="Plan ready for review",
        output=(
            "Plan marked as ready. The user will review and accept or reject it. "
            "Do NOT continue — stop here and wait for the user's decision."
        ),
        metadata={"plan_ready": True},
    )


plan_exit_tool = define_tool(
    "plan_exit",
    description=PLAN_EXIT_DESCRIPTION,
    parameters=PlanExitArgs,
    execute=execute_exit,
    sandbox_required=False,
)
