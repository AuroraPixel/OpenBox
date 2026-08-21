"""Todo tools: TodoWrite and TodoRead for session task tracking.

Uses full-replacement semantics (like opencode): the LLM provides the
complete todo list on every call, and the backend atomically replaces
all items.  This makes duplicate items structurally impossible.

Every write also appends a TodoPart to the conversation, which is what the
UI renders the task card from. The part stream is append-only on purpose:
it is the only record of *when* each task was running, and therefore the
only way to tell which tool calls belong under which task.
"""
from pydantic import BaseModel, Field

from tool.tool import ToolResult, ToolContext, define_tool

VALID_STATUS = ("pending", "in_progress", "completed", "cancelled")
VALID_PRIORITY = ("high", "medium", "low")


# ─── TodoWrite ───

class TodoItemInput(BaseModel):
    """A single todo item provided by the LLM."""
    content: str = Field(description="Brief description of the task")
    status: str = Field(
        default="pending",
        description="Current status of the task: pending, in_progress, completed, cancelled",
    )
    priority: str = Field(
        default="medium",
        description="Priority level of the task: high, medium, low",
    )
    active_form: str | None = Field(
        default=None,
        description=(
            "Present-tense wording for this task while it runs, e.g. "
            "'Computing the year-on-year split'. Shown as the heading while "
            "the task is in progress."
        ),
    )


class TodoWriteArgs(BaseModel):
    todos: list[TodoItemInput] = Field(description="The complete, updated todo list")


async def _publish_todo_part(ctx: ToolContext, items: list) -> None:
    """Append this snapshot of the list to the conversation."""
    from models.message import TodoPart
    from session.session import save_part

    if not ctx.message_id:
        return
    await save_part(
        TodoPart(
            items=items,
            source="model",
            session_id=ctx.session_id,
            message_id=ctx.message_id,
        ),
        is_new=True,
    )


async def execute_write(args: TodoWriteArgs, ctx: ToolContext) -> ToolResult:
    """Replace the entire todo list atomically."""
    from session.todo import replace_todos
    from models.message import TodoItem

    items = [
        TodoItem(
            subject=t.content,
            # An unrecognised status used to fall back to "pending", which
            # quietly resurrected tasks the model had cancelled — and a
            # pending task keeps the loop alive. Anything unknown is treated
            # as pending only because it has to be something; "cancelled" is
            # now a status in its own right rather than a typo.
            status=t.status if t.status in VALID_STATUS else "pending",
            priority=t.priority if t.priority in VALID_PRIORITY else "medium",
            active_form=t.active_form,
        )
        for t in args.todos
    ]

    todo = await replace_todos(ctx.session_id, items, user_id=ctx.user_id or "default")
    await _publish_todo_part(ctx, todo.items)
    active = sum(1 for t in todo.items if t.status not in ("completed", "cancelled"))
    return ToolResult(
        title=f"{active} todos",
        output="\n".join(
            f"[{t.status}] {t.subject}" for t in todo.items
        ) or "Todo list cleared.",
    )


TODO_WRITE_DESCRIPTION = """\
Use this tool to create and manage a structured task list for your current coding session. \
This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

IMPORTANT: This tool uses full-replacement semantics. Every time you call this tool, you must \
provide the COMPLETE updated todo list — not just one item. Include ALL existing items (with \
their current statuses) plus any new items. Items you omit will be removed.

## When to Use This Tool
Use this tool proactively in these scenarios:

1. Complex multistep tasks — When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks — Tasks that require careful planning or multiple operations
3. User explicitly requests todo list — When the user directly asks you to use the todo list
4. User provides multiple tasks — When users provide a list of things to be done (numbered or comma-separated)
5. After receiving new instructions — Immediately capture user requirements as todos. Feel free to edit the todo list based on new information.
6. After completing a task — Mark it complete and add any new follow-up tasks
7. When you start working on a new task, mark the todo as in_progress. Ideally you should only have one todo as in_progress at a time. Complete existing tasks before starting new ones.
8. When all tasks are done, call this tool one final time to mark all remaining items as completed. Do not leave items in in_progress status.

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

NOTE that you should not use this tool if there is only one trivial task to do. In this case you are better off just doing the task directly.

## Examples of When to Use the Todo List

<example>
User: I want to add a dark mode toggle to the application settings. Make sure you run the tests and build when you're done!
Assistant: I'll help add a dark mode toggle to your application settings. Let me create a todo list to track this implementation.
*Creates todo list with the following items:*
1. Create dark mode toggle component in Settings page
2. Add dark mode state management (context/store)
3. Implement CSS-in-JS styles for dark theme
4. Update existing components to support theme switching
5. Run tests and build process, addressing any failures or errors that occur
*Begins working on the first task*

<reasoning>
The assistant used the todo list because:
1. Adding dark mode is a multi-step feature requiring UI, state management, and styling changes
2. The user explicitly requested tests and build be run afterward
3. The assistant inferred that tests and build need to pass by adding "Ensure tests and build succeed" as the final task
</reasoning>
</example>

<example>
User: Help me rename the function getCwd to getCurrentWorkingDirectory across my project
Assistant: Let me first search through your codebase to find all occurrences of 'getCwd'.
*Uses grep or search tools to locate all instances of getCwd in the codebase*
Assistant: I've found 15 instances of 'getCwd' across 8 different files. Let me create a todo list to track these changes.
*Creates todo list with specific items for each file that needs updating*

<reasoning>
The assistant used the todo list because:
1. First, the assistant searched to understand the scope of the task
2. Upon finding multiple occurrences across different files, it determined this was a complex task with multiple steps
3. The todo list helps ensure every instance is tracked and updated systematically
4. This approach prevents missing any occurrences and maintains code consistency
</reasoning>
</example>

<example>
User: I need to implement these features for my e-commerce site: user registration, product catalog, shopping cart, and checkout flow.
Assistant: I'll help implement these features. First, let's add all the features to the todo list.
*Creates a todo list breaking down each feature into specific tasks based on the project architecture*
Assistant: Let's start with user registration. This will involve creating database models, API endpoints, and frontend forms that integrate with your existing authentication system.

<reasoning>
The assistant used the todo list because:
1. The user provided multiple complex features to implement in a comma separated list
2. The todo list helps organize these large features into manageable tasks
3. This approach allows for tracking progress across the entire implementation
</reasoning>
</example>

<example>
User: Can you help optimize my React application? It's rendering slowly and has performance issues.
Assistant: I'll help optimize your React application. First, let me examine your codebase to identify potential performance bottlenecks.
*Reviews component structure, render patterns, state management, and data fetching*
Assistant: After analyzing your codebase, I've identified several performance issues. Let me create a todo list to track our optimization efforts.
*Creates todo list with items like: 1) Implement memoization for expensive calculations in ProductList, 2) Add virtualization for long lists in Dashboard, 3) Optimize image loading in Gallery component, 4) Fix state update loops in ShoppingCart, 5) Review bundle size and implement code splitting*
Let's start by implementing memoization for the expensive calculations in your ProductList component.

<reasoning>
The assistant used the todo list because:
1. First, the assistant examined the codebase to identify specific performance issues
2. Based on this analysis, it identified multiple optimization opportunities
3. Performance optimization is a non-trivial task requiring multiple steps
4. The todo list helps methodically track improvements across different components
5. This systematic approach ensures all performance bottlenecks are addressed
</reasoning>
</example>

## Examples of When NOT to Use the Todo List

<example>
User: How do I print 'Hello World' in Python?
Assistant: In Python, you can print "Hello World" with this simple code:

```python
print("Hello World")
```

This will output the text "Hello World" to the console when executed.

<reasoning>
The assistant did not use the todo list because this is a single, trivial task that can be completed in one step. There's no need to track multiple tasks or steps for such a straightforward request.
</reasoning>
</example>

<example>
User: What does the git status command do?
Assistant: The git status command shows the current state of your working directory and staging area. It displays which changes have been staged, which haven't, and which files aren't being tracked by Git. This is a fundamental command for understanding the current state of your repository before making commits.

<reasoning>
The assistant did not use the todo list because this is an informational request with no actual coding task to complete. The user is simply asking for an explanation, not for the assistant to perform multiple steps or tasks.
</reasoning>
</example>

<example>
User: Can you add a comment to the calculateTotal function to explain what it does?
Assistant: Sure, let me add a comment to the calculateTotal function to explain what it does.
*Uses the Edit tool to add a comment to the calculateTotal function*

<reasoning>
The assistant did not use the todo list because this is a single, straightforward task confined to one location in the code. Adding a comment doesn't require tracking multiple steps or systematic organization.
</reasoning>
</example>

<example>
User: Run npm install for me and tell me what happens.
Assistant: I'll run the npm install command for you.
*Executes: npm install*
The command completed successfully. All dependencies have been installed according to your package.json file.

<reasoning>
The assistant did not use the todo list because this is a single command execution with immediate results. There are no multiple steps to track or organize, making the todo list unnecessary for this straightforward task.
</reasoning>
</example>

## Task States and Management

1. **Task States**: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (limit to ONE task at a time)
   - completed: Task finished successfully
   - cancelled: Task no longer needed

2. **Task Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Only have ONE task in_progress at any time
   - Complete current tasks before starting new ones
   - Cancel tasks that become irrelevant

3. **Items the user added**:
   The user can add tasks to this list themselves, and can cancel tasks you \
planned. Items they added are marked "(added by user)" when you read the list, \
and you will be told when they add one. Carry those items in your writes like \
your own, and do the work they describe. A task the user cancelled stays \
cancelled even if your write says otherwise — drop it from your list rather \
than trying to revive it.

4. **Task Breakdown**:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Use clear, descriptive task names

When in doubt, use this tool. Being proactive with task management demonstrates attentiveness \
and ensures you complete all requirements successfully."""

todo_write_tool = define_tool(
    "todo_write",
    description=TODO_WRITE_DESCRIPTION,
    parameters=TodoWriteArgs,
    execute=execute_write,
    sandbox_required=False,
)


# ─── TodoRead ───
class TodoReadArgs(BaseModel):
    pass


async def execute_read(args: TodoReadArgs, ctx: ToolContext) -> ToolResult:
    """Read the current todo list."""
    from session.todo import get_todo

    todo = await get_todo(ctx.session_id)
    if not todo.items:
        return ToolResult(title="Todo list empty", output="No todo items.")

    lines = []
    for item in todo.items:
        status_icon = {
            "pending": "[ ]", "in_progress": "[~]", "completed": "[x]", "cancelled": "[-]",
        }.get(item.status, "[ ]")
        # The model needs to see which items it did not put there, or it will
        # drop them from its next full-replacement write.
        who = " (added by user)" if item.source == "user" else ""
        lines.append(f"{status_icon} {item.subject}{who}")

    return ToolResult(
        title=f"Todo: {len(todo.items)} items",
        output="\n".join(lines),
    )


TODO_READ_DESCRIPTION = """\
Use this tool to read the current to-do list for the session. Use this tool proactively and \
frequently to ensure you are aware of the status of the current task list.

Use this tool especially in these situations:
- At the beginning of conversations to see what's pending
- Before starting new tasks to prioritize work
- When the user asks about previous tasks or plans
- Whenever you're uncertain about what to do next
- After completing tasks to update your understanding of remaining work
- After every few messages to ensure you're on track"""

todo_read_tool = define_tool(
    "todo_read",
    description=TODO_READ_DESCRIPTION,
    parameters=TodoReadArgs,
    execute=execute_read,
    sandbox_required=False,
)
