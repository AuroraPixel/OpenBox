# OpenBox vs opencode - Feature Comparison & Roadmap

> Generated: 2026-02-28
> Purpose: Feature gap analysis between OpenBox and opencode, with prioritized implementation roadmap.

---

## Technology Stack

| Dimension | OpenBox | opencode |
|-----------|---------|----------|
| **Language** | Python (Backend) + TypeScript (Frontend) | TypeScript (Bun runtime) |
| **Backend Framework** | FastAPI | Hono |
| **Frontend/UI** | React + Vite (Web GUI) | SolidJS TUI + Web UI |
| **Database** | File-system JSON (XDG) | SQLite + Drizzle ORM |
| **LLM SDK** | litellm | Vercel AI SDK |
| **Sandbox** | Docker container (action_server) | None (runs on host) |
| **Realtime** | SSE + WebSocket (terminal) | SSE + WebSocket |

---

## Core Architecture Differences

| Aspect | OpenBox | opencode |
|--------|---------|----------|
| **Execution Isolation** | Docker container sandbox | Direct host execution |
| **Deployment** | Web app (browser) | CLI tool (terminal) |
| **Persistence** | Docker Named Volume + FS JSON | SQLite |
| **Multi-user** | Architecture supports (container isolation) | Single-user |

---

## Feature Comparison

### Agent System

| Feature | OpenBox | opencode | Notes |
|---------|---------|----------|-------|
| build agent (default) | Yes | Yes | Same |
| plan agent | Yes | Yes | Same |
| explore agent | Yes | Yes | Same |
| general agent (subagent) | Yes | Yes | Same |
| compaction agent | Yes | Yes | Same |
| title agent | Yes | Yes | Same |
| summary agent | No | Yes | opencode has dedicated summary agent |
| Custom agents | Yes (config) | Yes (config + LLM generate) | opencode can auto-generate agent config via LLM |
| Model-specific prompts | Yes (6 sets) | Yes (7 sets) | Essentially the same |
| Max steps control | Yes | Yes | |
| Doom loop detection | Yes | Yes | |

### Tool System

| Tool | OpenBox | opencode | Notes |
|------|---------|----------|-------|
| **bash** | Yes (in container) | Yes (on host) | OpenBox is safer (isolated) |
| **read** | Yes | Yes | |
| **write** | Yes | Yes | |
| **edit** | Yes | Yes | opencode adds: LSP diagnostics + auto-format |
| **multiedit** | No | Yes | opencode only |
| **apply_patch** | Yes | Yes | |
| **glob** | Yes | Yes | |
| **grep** | Yes | Yes | |
| **ls/list** | Yes (via list_files) | Yes (tree structure) | |
| **task** | Yes | Yes | |
| **batch** | Yes | Yes | |
| **skill** | Yes | Yes | |
| **todo** | Yes | Yes | |
| **question** | Yes | Yes | |
| **plan** | Yes | Yes | |
| **webfetch** | Yes | Yes | opencode adds image base64 |
| **websearch** | Yes | Yes | opencode uses Exa API |
| **codesearch** | No | Yes | opencode searches code/docs via Exa MCP |
| **lsp** | No | Yes | opencode only, 12+ languages |
| **MCP tools** (dynamic) | Yes | Yes | |
| **invalid** | Yes | Yes | |

### MCP Integration

| Feature | OpenBox | opencode | Notes |
|---------|---------|----------|-------|
| stdio transport | Yes (in container) | Yes (on host) | |
| SSE transport | Yes | Yes | |
| Streamable HTTP | Yes (custom RawStreamableHttpSession) | Yes | |
| OAuth authentication | No | Yes | opencode has full OAuth 2.0 flow |
| MCP resources | No | Yes | |
| MCP prompts | No | Yes (surfaced as slash commands) | |
| Tool refresh notification | No | Yes (ToolListChangedNotification) | |
| Config persistence | Yes (Docker Volume) | Yes (config file) | |
| UI management | Yes (Web GUI) | Yes (TUI dialog + CLI) | |

### Skill System

| Feature | OpenBox | opencode | Notes |
|---------|---------|----------|-------|
| SKILL.md frontmatter | Yes | Yes | |
| Global skill directory | Yes | Yes | |
| Project skill directory | Yes | Yes | |
| .claude/skills compat | Yes | Yes | |
| URL install | Yes (git clone / download) | Yes (skills.urls config) | |
| Paste content install | Yes | No | OpenBox only |
| UI install/uninstall | Yes (Web GUI dialog) | No (config file only) | |
| Container isolation | Yes | N/A (host) | |
| Skill as slash command | No | Yes | |

### Session Management

| Feature | OpenBox | opencode | Notes |
|---------|---------|----------|-------|
| Session CRUD | Yes | Yes | |
| Auto-title | Yes | Yes | |
| Parent/child sessions | Yes | Yes | |
| Revert/Unrevert | Yes | Yes | |
| File diff tracking | Yes | Yes | |
| Git-based snapshots | Yes | Yes | |
| Session fork | No | Yes | opencode only |
| Session sharing | No | Yes (opncd.ai) | opencode only |
| Session import/export | No | Yes | opencode only |
| Session archiving | No | Yes | opencode only |
| Session search | Yes | Yes | |
| Token/cost tracking | Yes | Yes | |

### Context Management

| Feature | OpenBox | opencode | Notes |
|---------|---------|----------|-------|
| Auto compaction | Yes | Yes | |
| Overflow detection | Yes | Yes | |
| Tool output pruning | Yes | Yes | |
| Configurable reserved tokens | Yes | Yes | |
| Manual summarize trigger | Yes | No | OpenBox has API endpoint |
| Plugin hook for compaction | No | Yes | opencode allows plugin customization |

### Permission System

| Feature | OpenBox | opencode | Notes |
|---------|---------|----------|-------|
| Rule matching (allow/deny/ask) | Yes | Yes | |
| Wildcard patterns | Yes | Yes | |
| "Always Allow" memory | Yes | Yes | |
| Agent-level permissions | Yes | Yes | |
| Frontend permission UI | Yes | Yes | |
| Persistent approvals | No (in-memory) | Yes (SQLite) | opencode persists across restarts |

### UI / User Interface

| Feature | OpenBox | opencode | Notes |
|---------|---------|----------|-------|
| **Interface type** | Web GUI (browser) | TUI (terminal) + Web | |
| Chat interface | Yes | Yes | |
| Terminal (PTY) | Yes (xterm.js WebSocket) | Yes (built-in PTY) | |
| File browser | Yes | No | OpenBox only |
| Web preview (iframe) | Yes (reverse proxy + path rewrite) | No | OpenBox only |
| Port auto-detection | Yes | No | OpenBox only |
| Diff view | Yes | No (TUI has no diff view) | |
| Sidebar navigation | Yes | Yes (session list) | |
| Command palette | Yes (Ctrl+K) | Yes | |
| Slash commands | Yes | Yes | |
| File @ mention | Yes | No | OpenBox only |
| Theme switching | Yes (light/dark) | Yes (many themes) | opencode has more themes |
| Right panel (Context/Todo/Details) | Yes | No | |
| Sandbox management page | Yes | N/A | |
| Settings page | Yes | Yes (TUI dialog) | |
| Toast notifications | No | Yes | |
| Prompt history (up/down) | No | Yes | |
| Prompt stash | No | Yes | |

### Sandbox / Container System

| Feature | OpenBox | opencode | Notes |
|---------|---------|----------|-------|
| Docker container isolation | Yes | No | **OpenBox core differentiator** |
| Container lifecycle management | Yes | N/A | |
| Resource limits (CPU/memory) | Yes (512MB/50% CPU) | N/A | |
| Named volume persistence | Yes | N/A | |
| Image build (SSE streaming) | Yes | N/A | |
| System info (CPU/memory/disk) | Yes | N/A | |
| Port proxy/preview | Yes | N/A | |
| Protected command detection | Yes | N/A | |

### LLM Provider Support

| Provider | OpenBox | opencode | Notes |
|----------|---------|----------|-------|
| Anthropic (Claude) | Yes | Yes | |
| OpenAI | Yes | Yes | |
| Google (Gemini) | Yes | Yes | |
| Azure OpenAI | Yes (via litellm) | Yes | |
| AWS Bedrock | Yes (via litellm) | Yes | |
| Vertex AI | Yes (via litellm) | Yes | |
| xAI (Grok) | Yes (via litellm) | Yes | |
| Mistral | Yes (via litellm) | Yes | |
| Groq | Yes (via litellm) | Yes | |
| OpenRouter | Yes (via litellm) | Yes | |
| GitHub Copilot | No | Yes (OAuth) | opencode only |
| GitLab AI | No | Yes | opencode only |
| DeepInfra | Yes (via litellm) | Yes | |
| Custom endpoints | Yes | Yes | |

### Other Systems

| Feature | OpenBox | opencode | Notes |
|---------|---------|----------|-------|
| **LSP integration** | No | Yes (12+ languages) | Major opencode-only feature |
| **Auto-format after edit** | No | Yes | opencode only |
| **Plugin system** | No | Yes (npm plugins) | opencode only |
| **Worktree support** | No | Yes (git worktree isolation) | opencode only |
| **File watching** | No | Yes (file change events) | |
| **OpenTelemetry** | No | Yes (experimental) | |
| **Auto-update** | No | Yes | |
| **Enterprise features** | No | Yes (system config, enterprise sharing) | |
| **AGENTS.md / CLAUDE.md** | No | Yes | opencode reads project instruction files |
| **Prompt caching** (Anthropic) | Yes | Yes | |

---

## OpenBox Unique Advantages

1. **Docker Container Isolation** - Code executes in sandbox, cannot affect host machine
2. **Web Preview** - iframe preview of web apps running in container, with auto port detection + path rewriting
3. **Web GUI** - Full browser IDE experience (file browser, diff view, terminal tabs, right panel)
4. **File @ Mention** - Reference container files in chat input
5. **Multi-user Architecture** - Container isolation enables future multi-user/multi-tenant support
6. **Skill Install UI** - Visual install/uninstall for skills and MCP servers

## opencode Unique Advantages

1. **LSP Integration** - 12+ language server support (go-to-definition, references, diagnostics)
2. **Auto-format** - Runs formatter after edits automatically
3. **Plugin System** - npm plugin packages with rich hook points
4. **Worktree** - git worktree isolation for parallel development
5. **MCP OAuth** - Full OAuth 2.0 flow for authenticated MCP servers
6. **Session Sharing/Export** - Share to opncd.ai or export sessions
7. **Session Fork** - Branch conversations
8. **codesearch** - Search code and documentation via Exa MCP
9. **multiedit** - Multi-location edits in a single tool call
10. **Enterprise features** - System-managed config, enterprise sharing URL
11. **AGENTS.md / CLAUDE.md** - Reads project-level instruction files
12. **Mature TUI** - Rich terminal interaction (themes, keybindings, history, stash)

---

## Implementation Roadmap

### Phase 1: High Priority - Core Experience Gaps

| # | Feature | Current State | Gap | Proposed Solution | Effort |
|---|---------|--------------|-----|-------------------|--------|
| 1 | **Project Instructions (AGENTS.md/CLAUDE.md)** | Not implemented | opencode and Claude Code both read project root `AGENTS.md`/`CLAUDE.md` as part of system prompt. Users cannot customize agent behavior per-project. | Inject contents of `AGENTS.md`, `CLAUDE.md`, `.openbox/instructions.md` from project root into agent loop system prompt | S |
| 2 | **LSP Diagnostics After Edit** | Not implemented | opencode runs LSP diagnostics after every edit, feeding compile errors back to LLM for auto-fix. OpenBox agent has no awareness of code errors it introduced. | Install basic LSP servers in container (TypeScript, Python). Run diagnostics after edit/write tools, inject errors into tool result. | L |
| 3 | **Auto-format After Edit** | Not implemented | opencode auto-runs formatter (prettier/black etc.) after edits, maintaining consistent code style. OpenBox agent output may not match project conventions. | Detect project formatter in container, run after edit/write tools | M |
| 4 | **Session Persistence (Database)** | File-system JSON | No transaction guarantees, not concurrency-safe, slow queries. opencode uses SQLite + Drizzle ORM. | Migrate to SQLite (aiosqlite + SQLAlchemy/Tortoise), or at minimum ensure atomic writes | L |
| 5 | **Permission Persistence** | In-memory only | "Always Allow" choices lost on backend restart, user must re-approve repeatedly. opencode persists to SQLite. | Persist permission approvals to storage layer, survive across sessions/restarts | S |

### Phase 2: Medium Priority - User Experience

| # | Feature | Current State | Gap | Proposed Solution | Effort |
|---|---------|--------------|-----|-------------------|--------|
| 6 | **multiedit Tool** | Not implemented | Current edit tool does one replacement per call. Multi-location edits waste tokens and steps. opencode has multiedit. | New multiedit tool accepting `edits: [{old, new}]` array for single-file multi-location replacement | S |
| 7 | **Session Fork** | Not implemented | Users cannot branch from a message to try different approaches. opencode supports fork. | New fork API: copy session up to specified message, create new session to continue | M |
| 8 | **Prompt History/Stash** | Not implemented | No input history (up/down arrow), long prompts lost if accidentally closed. | Frontend InputBar: add prompt history (localStorage) and stash functionality | S |
| 9 | **MCP OAuth Authentication** | Not implemented | Some MCP servers require OAuth (e.g., GitHub MCP). OpenBox cannot connect to these. opencode has full OAuth 2.0. | Implement OAuth callback in action_server, frontend opens auth window | L |
| 10 | **Custom Slash Commands (config)** | Read .md files only | Can only read command templates from `.openbox/commands/` directory. Cannot define in config. opencode supports config + MCP prompt + skill as commands. | Support command definition in config file; auto-register skills and MCP prompts as slash commands | M |
| 11 | **Skill as Slash Command** | Not implemented | Users must use skill tool indirectly. Cannot `/skill-name` directly. opencode auto-registers skills as commands. | Register installed skills as slash commands, show in `/` autocomplete | S |
| 12 | **codesearch Tool** | Not implemented | Agent cannot search external code/documentation/API references. opencode provides via Exa MCP. | New codesearch tool (via built-in MCP or direct API) | M |

### Phase 3: Low Priority - Nice to Have

| # | Feature | Current State | Gap | Proposed Solution | Effort |
|---|---------|--------------|-----|-------------------|--------|
| 13 | **Session Export/Share** | Not implemented | Cannot export sessions as Markdown/JSON or share with others | New export endpoint (Markdown/JSON), optional remote sharing | M |
| 14 | **Git Worktree Support** | Not implemented | All work in same directory, cannot develop different branches in parallel. opencode has full worktree management. | Support worktree creation/switching in container `/workspace` | M |
| 15 | **Plugin System** | Not implemented | No third-party extension mechanism. opencode has npm plugins + hook points. | Design hook points (chat.params, tool lifecycle, compaction), support container-side or backend plugins | L |
| 16 | **File Watching** | Not implemented | Container file changes don't proactively notify frontend. opencode has file watcher events. | Container inotify -> SSE events -> frontend auto-refresh file browser/diff | M |
| 17 | **Copilot/GitLab Provider** | Not implemented | Cannot use GitHub Copilot or GitLab AI free credits. opencode has OAuth integration. | Add Copilot OAuth flow (litellm may already support) | M |
| 18 | **Toast Notifications** | Not implemented | Background operations (install skill, connect MCP, compaction) have no lightweight feedback | Add toast component to frontend, trigger from SSE events | S |
| 19 | **Custom Agent via LLM** | Not implemented | Users can only manually configure agents. opencode can auto-generate agent config from description. | New `Agent.generate()` API endpoint, LLM generates agent definition from description | S |
| 20 | **Session Archiving** | Not implemented | Session list grows indefinitely, cannot archive old sessions | Add archive status, hide archived sessions from sidebar | S |

> **Effort estimates**: S = Small (< 1 day), M = Medium (1-3 days), L = Large (3+ days)

### Suggested Execution Order

```
Batch 1 (Core):       #1 Project Instructions -> #6 multiedit -> #5 Permission Persistence -> #8 Prompt History
Batch 2 (Code Quality): #2 LSP Diagnostics -> #3 Auto-format
Batch 3 (UX):          #11 Skill as Command -> #10 Custom Commands -> #18 Toast -> #4 Session DB
Batch 4 (Advanced):     #7 Session Fork -> #9 MCP OAuth -> #12 codesearch -> #13 Export/Share
Batch 5 (Ecosystem):    #15 Plugin System -> #16 File Watching -> #14 Worktree -> #17 Copilot -> #19 Agent Generate -> #20 Archiving
```

---

## Checklist

Use this checklist to track implementation progress:

- [ ] #1 Project Instructions (AGENTS.md / CLAUDE.md)
- [ ] #2 LSP Diagnostics After Edit
- [ ] #3 Auto-format After Edit
- [ ] #4 Session Persistence (SQLite)
- [ ] #5 Permission Persistence
- [ ] #6 multiedit Tool
- [ ] #7 Session Fork
- [ ] #8 Prompt History / Stash
- [ ] #9 MCP OAuth Authentication
- [ ] #10 Custom Slash Commands (config)
- [ ] #11 Skill as Slash Command
- [ ] #12 codesearch Tool
- [ ] #13 Session Export / Share
- [ ] #14 Git Worktree Support
- [ ] #15 Plugin System
- [ ] #16 File Watching
- [ ] #17 Copilot / GitLab Provider
- [ ] #18 Toast Notifications
- [ ] #19 Custom Agent via LLM
- [ ] #20 Session Archiving
