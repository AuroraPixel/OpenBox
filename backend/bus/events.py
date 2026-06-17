"""Event type constants matching frontend types/sse.ts."""

# Session events
SESSION_STATUS = "session.status"
SESSION_FINALIZING = "session.finalizing"
SESSION_TITLE = "session.title"
SESSION_ERROR = "session.error"
SESSION_DIFF = "session.diff"
SESSION_COMPACTION_START = "session.compaction.start"
SESSION_COMPACTION_COMPLETE = "session.compaction.complete"
SESSION_UPDATED = "session.updated"

# Message events
MESSAGE_CREATED = "message.created"
MESSAGE_UPDATED = "message.updated"
MESSAGE_TEXT_DELTA = "message.text_delta"

# Part events
PART_CREATED = "part.created"
PART_UPDATED = "part.updated"
PART_DELTA = "part.delta"

# Tool events
TOOL_RUNNING = "tool.running"
TOOL_COMPLETED = "tool.completed"
TOOL_ERROR = "tool.error"

# Interaction events
PERMISSION_ASKED = "permission.asked"
PERMISSION_REPLIED = "permission.replied"
QUESTION_ASKED = "question.asked"
QUESTION_REPLIED = "question.replied"
QUESTION_REJECTED = "question.rejected"
TODO_UPDATED = "todo.updated"

# Toast notifications (F10)
TOAST = "toast"

# Cron events
CRON_JOB_CREATED = "cron.job.created"
CRON_JOB_UPDATED = "cron.job.updated"
CRON_JOB_STARTED = "cron.job.started"
CRON_JOB_COMPLETED = "cron.job.completed"
CRON_JOB_FAILED = "cron.job.failed"
CRON_JOB_INJECTED = "cron.job.injected"

# Dev-browser events
DEVBROWSER_STATUS = "devbrowser.status"

# Server internal events
SERVER_CONNECTED = "server.connected"
SERVER_HEARTBEAT = "server.heartbeat"
