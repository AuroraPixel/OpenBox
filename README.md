# OpenBox

**An AI Agent execution platform** — give an LLM a safe, isolated sandbox to read, write, run code, and drive a browser, with production-grade orchestration, context management, and multi-tenant isolation.

> A general-purpose agent runtime (inspired by OpenCode/Claude Code), rewritten in Python around **Pydantic AI + LiteLLM**, with every file/command operation confined to a per-session **Docker / Kubernetes sandbox**. Deployed on GCP GKE.

---

## At a glance

| | |
|---|---|
| **What it is** | A full-stack platform where an AI agent autonomously executes development tasks (edit code, run bash, git, browse) inside an isolated container, with a real-time web UI showing every tool call. |
| **Core stack** | FastAPI · Pydantic AI · LiteLLM (100+ models) · Docker/K8s sandbox · PostgreSQL · Redis · React 19 |
| **Agent loop** | Pydantic AI single-turn tool calls wrapped by a custom outer loop: multi-turn orchestration, permission checks, retries, context compaction |
| **Isolation** | Each session owns a dedicated sandbox container; user file/command tools run inside it, control-plane logic runs on the host |
| **Scale** | Docker locally, dynamic K8s container pool on GKE; multi-tenant (workspace / project / permission inheritance) |

---

## Why OpenBox is different

Most "let an LLM run code" demos break the moment they hit production. OpenBox treats the agent as a *system*, not a prompt:

| Concern | Typical agent demo | OpenBox |
|---|---|---|
| **Safety** | LLM runs commands on the host | Every `bash`/`read`/`write`/`edit`/`glob`/`grep` runs **inside a per-session sandbox**; host only does control-plane work |
| **Context overflow** | Conversation grows until it blows the window | **Automatic context compaction** (summarize history on overflow) + tool-output truncation + prompt cache |
| **Reliability** | One bad tool call kills the run | Custom outer loop with per-tool retry, permission gating, and graceful degradation |
| **Multi-user** | Single shared process | Workspace/project isolation, per-session container, Logto OIDC (enterprise SSO), credential boundary |
| **Auditability** | Opaque chat history | Real-time event stream (SSE + WebSocket), tool-execution visualization, session branch/rollback (git-like history) |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  OpenBox API (FastAPI, host)                  │
│  Agent orchestration · permission · skill ·   │
│  MCP · session · cron · event bus             │
├──────────────────┬────────────────────────────┤
│  Pydantic AI      │   Sandbox (per session)     │
│  tool-call loop   │   bash / read / write /     │
│  + LiteLLM        │   edit / glob / grep ...     │
└──────────────────┴────────────────────────────┘
                        │
                 Docker container  (local)
                 K8s container pool (GKE prod)
```

### Execution boundary (host vs sandbox)

| Tool / module | Runs in | Why |
|---|---|---|
| `bash`, `read`, `write`, `edit`, `apply_patch`, `glob`, `grep` | **Sandbox** | File/command ops must be isolated |
| MCP tool calls | Host | MCP servers are separate processes |
| Skill load (read `SKILL.md`) | Host | Config read, no risk |
| Skill execution (LLM acting) | **Sandbox** | Real actions go through `bash`/`write` |
| `web_fetch`, `web_search` | Host | Network requests |
| Plugin code + hooks | Host | Auth, arg mutation, host logic |
| Agent orchestration / permission / event bus | Host | Control plane |

---

## Key capabilities

- **Agent loop** (`backend/agent/`): `loop.py` outer orchestration, `compaction.py` auto context summarization, `caching.py` prompt cache, `retry.py` resilient retries, `hooks.py` lifecycle hooks.
- **Sandbox manager** (`backend/sandbox/`): `docker.py` + `kubernetes.py` dual providers, `manager.py` lifecycle (create on session start, destroy on end), dynamic GKE container pool.
- **22+ built-in tools**: bash, read, write, edit, glob, grep, mcp, skill, web_fetch, web_search, question, todo, plan, batch, …
- **Fine-grained permissions** (`backend/permission/`): per-tool approval flow with interactive user confirmation.
- **Three-tier context/memory**: in-memory current turn → DB-persisted compacted history → long-term instruction files.
- **Cron agents** (`backend/cron/`): scheduled autonomous agent runs.
- **Session branch / rollback**: git-like session history management.
- **Real-time UI**: PTY terminal (xterm.js + WebSocket), tool-execution timeline, diff viewer, SSE event stream.

---

## Tech stack

**Backend** (Python 3.12)
- FastAPI + Uvicorn · **Pydantic AI** (agent loop) · **LiteLLM** (100+ providers)
- PostgreSQL (SQLAlchemy async + Alembic) · Redis (session / ticket / context cache)
- Docker SDK + Kubernetes client (sandbox) · Azure Blob Storage (user files)
- JWT + Logto OIDC (enterprise SSO)

**Frontend** (React 19)
- Vite + TypeScript · Tailwind CSS 4 + Framer Motion
- Zustand + TanStack Query · TanStack Router · xterm.js (PTY)

**Infrastructure**
- GCP GKE (K8s) · Docker Compose (local) · Makefile workflow · monorepo (npm workspace)

---

## Project structure

```
OpenBox/
├── backend/
│   ├── agent/        # agent loop, compaction, caching, retry, hooks
│   ├── sandbox/      # docker.py + kubernetes.py providers, manager
│   ├── tool/         # built-in tools
│   ├── permission/   # per-tool approval
│   ├── mcp/          # MCP integration
│   ├── skill/        # skill loading/execution
│   ├── session/      # session lifecycle, branch/rollback
│   ├── cron/         # scheduled agents
│   ├── api/ · auth/ · db/ · bus/ · cache/ · blob/
│   └── main.py
├── frontend/         # React 19 + Vite UI
├── container/        # sandbox image (action_server)
├── k8s/              # GKE manifests
├── docs/             # architecture & design docs
└── docker-compose.yml
```

---

## Quick start (local)

```bash
# Backend (FastAPI, host)
cd backend
uv sync
cp openbox.jsonc.example openbox.json   # configure model / providers
cp .env.example .env                      # fill keys (never commit)
uv run python main.py

# Frontend
cd frontend
npm install
npm run dev          # or: npm run dev:mock  (UI without backend)
```

Docker sandbox image + full stack:

```bash
docker compose up        # backend + frontend + sandbox
```

Deployment manifests for GKE live in `k8s/`. See `docs/gke.md`.

---

## Documentation

Design docs in [`docs/`](docs/): `OPENAGENT_DESIGN.md` (agent architecture), `FRONTEND_DESIGN.md`, `API_INTERFACES.md`, `MULTI_USER_STORAGE_PLAN.md`, `CRON_SYSTEM_PLAN.md`, `PTY_UPGRADE_PLAN.md`, `PERFORMANCE_OPTIMIZATION.md`, `gke.md`.

---

## Note

This is a sanitized public copy: secrets and environment files have been removed; sandbox image internals and a vendored agent framework are excluded. Configure your own model providers and credentials via `.env` / `openbox.json`.
