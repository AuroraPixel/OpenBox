"""Question tool: LLM asks user structured questions."""
from pydantic import BaseModel, Field

from tool.tool import ToolResult, ToolContext, define_tool

QUESTION_DESCRIPTION = """\
Use this tool when you need to ask the user questions during execution. This allows you to:
1. Gather user preferences or requirements
2. Clarify ambiguous instructions
3. Get decisions on implementation choices as you work
4. Offer choices to the user about what direction to take.

Usage notes:
- When `custom` is enabled (default), a "Type your own answer" option is added automatically; don't include "Other" or catch-all options
- Answers are returned as arrays of labels; set `multiple: true` to allow selecting more than one
- If you recommend a specific option, make that the first option in the list and add "(Recommended)" at the end of the label\
"""


class QuestionOption(BaseModel):
    label: str
    description: str = ""


class QuestionItem(BaseModel):
    question: str
    header: str = ""
    options: list[QuestionOption] = []
    multiple: bool = False


class QuestionArgs(BaseModel):
    questions: list[QuestionItem] = Field(description="1-4 questions to ask the user")


async def execute(args: QuestionArgs, ctx: ToolContext) -> ToolResult:
    """Ask the user questions and wait for answers."""
    from question.question import ask, Question as QModel, QuestionOption as QOpt

    questions = [
        QModel(
            question=q.question,
            header=q.header,
            options=[QOpt(label=o.label, description=o.description) for o in q.options],
            multiple=q.multiple,
        )
        for q in args.questions
    ]

    answers = await ask(
        session_id=ctx.session_id,
        questions=questions,
        tool={"messageID": ctx.message_id, "callID": ctx.part_id} if ctx.part_id else None,
        user_id=ctx.user_id or "default",
    )

    def format_answer(answer):
        if not answer:
            return "Unanswered"
        return ", ".join(answer)

    formatted = ", ".join(
        f'"{q.question}"="{format_answer(answers[i] if i < len(answers) else None)}"'
        for i, q in enumerate(args.questions)
    )

    return ToolResult(
        title=f"Asked {len(args.questions)} question{'s' if len(args.questions) > 1 else ''}",
        output=f"User has answered your questions: {formatted}. You can now continue with the user's answers in mind.",
        # Both halves, so the conversation can show what was asked next to what
        # was chosen. Reconstructing the pairing from the output string means
        # parsing quotes back out of prose the model also reads.
        metadata={
            "answers": answers,
            "questions": [q.question for q in args.questions],
        },
    )


question_tool = define_tool(
    "question",
    description=QUESTION_DESCRIPTION,
    parameters=QuestionArgs,
    execute=execute,
    sandbox_required=False,
)
