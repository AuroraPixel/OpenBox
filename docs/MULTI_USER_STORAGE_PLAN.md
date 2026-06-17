# 多用户隔离 + 数据存储架构重构计划

## 目标

1. 多用户隔离 — 用户认证 + 数据按 user_id 隔离
2. PostgreSQL 存储所有结构化数据（替代当前 JSON 文件）
3. Redis 做缓存 + 跨 Worker 通信 + 会话阻塞
4. Azure Blob 做容器文件数据备份
5. 数据库层和存储层抽象化，方便后续切换不同 SQL / 对象存储
6. 多 Worker 就绪 — 进程内状态可跨 Worker 同步

> **基础设施假设**：PostgreSQL、Redis、Azure Blob 的高可用由云原生平台保证，本计划不做第三方组件故障降级设计。

---

## 当前现状（需改造的部分）

| 组件 | 当前方式 | 问题 |
|------|---------|------|
| 会话/消息/Parts | JSON 文件 `~/.local/share/openbox/storage/`（30 处调用） | 无事务、N+1 查询、无多用户 |
| 权限审批 | 纯内存 `_approved` 列表 + `_pending` dict（`permission.py:50-52`） | 重启丢失、跨 Worker 不共享 |
| 问题系统 | 纯内存 `_pending` dict（`question.py:60`） | 重启丢失、跨 Worker 不共享 |
| 容器跟踪 | 纯内存 `_containers` dict（`docker.py:30`） | 重启丢失、跨 Worker 不共享 |
| 用户系统 | 不存在 | 无认证、无隔离 |
| UI 偏好 | 浏览器 localStorage | 换设备丢失 |
| 容器文件备份 | 无 | 容器删除后文件丢失 |
| project_id | 硬编码 "default"（`session.py:84`） | 无多项目支持 |
| 实时通信 | SSE 单向广播（`events.py` + `sse.ts`），进程内 pub/sub（`bus.py`），28 处 publish 均无 userId | 单向、无用户过滤、跨 Worker 不可达、认证困难 |
| 所有 API 端点 | 零认证 | 任何人可访问任何数据 |
| 回退快照 | 纯内存 dict（`revert.py:14`） | 重启丢失 |
| 全局单例 | 9 个模块级单例/全局 dict | 多用户共享状态 |

---

## 架构总览

```
┌────────────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (Uvicorn 多 Worker)                   │
│                                                                        │
│  API Layer ── Auth Middleware (JWT) ── Rate Limiter (Redis)            │
│      │                                                                 │
│  Service Layer (session, permission, sandbox, audit...)                │
│      │                                                                 │
│  ┌───▼─────────────────────────────────────────────────────────┐      │
│  │            Repository Layer (Protocol 抽象接口)              │      │
│  │  ISessionRepo  IMessageRepo  IUserRepo  IAuditRepo  ...    │      │
│  │      │              │            │           │              │      │
│  │  ┌───▼───┐    ┌────▼──┐   ┌────▼──┐  ┌────▼──┐           │      │
│  │  │ PgSQL │    │ PgSQL │   │ PgSQL │  │ PgSQL │            │      │
│  │  └───────┘    └───────┘   └───────┘  └───────┘            │      │
│  └─────────────────────────────────────────────────────────────┘      │
│      │                                                                 │
│  ┌───▼─────────────────────────────────────────────────────────┐      │
│  │            Redis Layer                                       │      │
│  │                                                              │      │
│  │  Cache      Pub/Sub         Locks       Rate Limiter        │      │
│  │  (热数据)   (跨Worker通信)  (分布式锁)   (API限频)           │      │
│  │             (WS事件广播)    (端口分配)                       │      │
│  │             (abort信号)                                      │      │
│  │             (permission/question阻塞)                        │      │
│  └─────────────────────────────────────────────────────────────┘      │
│      │                                                                 │
│  ┌───▼─────────────────────────────────────────────────────────┐      │
│  │            Blob Storage Layer (IBlobStorage Protocol)        │      │
│  │  Azure Blob  ← 可切换为 S3 / GCS / MinIO / 本地            │      │
│  └─────────────────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: 抽象层 + 依赖 + 开发环境

### 1.1 新建 `backend/db/` — 数据库抽象层

```
backend/db/
├── __init__.py
├── base.py              # SQLAlchemy Base, async engine factory, async_sessionmaker
├── models/
│   ├── __init__.py
│   ├── user.py, project.py, session.py, message.py, part.py
│   ├── permission.py, container.py, preference.py
│   ├── prompt_history.py, todo.py, audit_log.py
├── repository/
│   ├── __init__.py
│   ├── interfaces.py    # Protocol classes
│   ├── user_repo.py, session_repo.py, message_repo.py
│   ├── permission_repo.py, container_repo.py
│   ├── preference_repo.py, audit_repo.py
└── migrations/
    ├── env.py
    └── versions/
```

**设计要点**：
- Repository 接口使用 `Protocol` 类，不绑定 SQLAlchemy
- 所有 repo 方法接受 `user_id` 参数实现隔离
- 不使用 PostgreSQL 专有语法（`ON CONFLICT` → `merge`；JSONB → TypeDecorator 跨库兼容）
- **Agent loop 使用短生命周期 DB session**：每次 DB 操作独立获取连接、操作后立即归还，不在整个 loop 执行期间持有连接

### 1.2 新建 `backend/cache/` — 缓存层

```
backend/cache/
├── __init__.py
├── interfaces.py        # ICache Protocol
├── redis_cache.py       # Redis 实现（生产）
└── memory_cache.py      # 内存实现（仅开发/测试用）
```

```python
class ICache(Protocol):
    async def get(self, key: str) -> Any | None: ...
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def delete_pattern(self, pattern: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def incr(self, key: str, ttl: int | None = None) -> int: ...
```

### 1.3 新建 `backend/blob/` — 对象存储抽象层

```
backend/blob/
├── __init__.py
├── interfaces.py        # IBlobStorage Protocol
├── azure_blob.py        # Azure Blob 实现
├── local_blob.py        # 本地文件系统实现（开发/测试）
└── sync.py              # 本地缓存 ↔ Blob 同步服务
```

```python
class IBlobStorage(Protocol):
    async def upload(self, key: str, data: bytes | AsyncIterator[bytes],
                     metadata: dict | None = None) -> str: ...
    async def download(self, key: str) -> AsyncIterator[bytes]: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def list_keys(self, prefix: str) -> list[str]: ...
    async def get_metadata(self, key: str) -> dict | None: ...
    async def get_presigned_url(self, key: str, expires: int = 3600) -> str: ...
```

### 1.4 修改 `backend/pyproject.toml` — 新增依赖

```
# 新增生产依赖
sqlalchemy[asyncio]>=2.0
asyncpg
alembic
redis[hiredis]>=5.0
azure-storage-blob>=12.0
passlib[bcrypt]
python-jose[cryptography]

# 移除
sse-starlette  ← 删除（SSE 全部改为 WebSocket，websockets 已在依赖中）

# 新增测试依赖
pytest>=8.0
pytest-asyncio>=0.23
```

### 1.5 修改 `backend/core/config.py` — 新增配置项

在当前 `OpenBoxConfig`（`config.py:62-90`）新增：

```python
# ── Database ──
database_url: str = "postgresql+asyncpg://openbox:openbox@localhost:5432/openbox"
db_pool_size: int = 10
db_pool_overflow: int = 20

# ── Redis ──
redis_url: str = "redis://localhost:6379/0"

# ── Blob Storage ──
blob_provider: str = "azure"            # "azure" | "local"
blob_azure_connection_string: str = ""
blob_azure_container: str = "ads-staging"
blob_local_path: str = "/opt/openbox/blobs"

# ── Auth ──
jwt_secret: str                          # 必填，启动时校验
jwt_access_expire_minutes: int = 15
jwt_refresh_expire_days: int = 7

# ── Quotas ──
max_containers_per_user: int = 5
max_sessions_per_user: int = 200
max_storage_mb_per_user: int = 5120
max_concurrent_agents: int = 3
monthly_cost_limit: float = 50.0
max_prompt_history: int = 500

# ── Rate Limiting ──
rate_limit_login: str = "5/minute"
rate_limit_api: str = "60/minute"
```

启动校验：`jwt_secret` 未设置 → `raise RuntimeError("JWT_SECRET is required")`

### 1.6 新建 `docker-compose.dev.yml`

```yaml
services:
  postgres:
    image: postgres:16-alpine
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: openbox
      POSTGRES_USER: openbox
      POSTGRES_PASSWORD: openbox_dev
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  azurite:
    image: mcr.microsoft.com/azure-storage/azurite
    ports: ["10000:10000"]
    volumes: [azurite-data:/data]
    command: azurite-blob --blobHost 0.0.0.0
volumes:
  pgdata:
  azurite-data:
```

### 1.7 测试基础设施（Phase 1 即建立）

> **关键决策**：测试不放到最后，从 Phase 1 开始每个 Phase 写对应测试。

```
backend/tests/
├── conftest.py            # fixtures: async DB session (SQLite in-memory), test Redis, test user
├── unit/                  # 每个 Phase 持续补充
└── integration/           # 每个 Phase 持续补充
```

**验收标准**：
- [ ] `docker compose -f docker-compose.dev.yml up` 启动 PG + Redis + Azurite
- [ ] SQLAlchemy async engine 连接 PG 成功
- [ ] Redis 连接成功
- [ ] Blob SDK 连接 Azurite 成功
- [ ] pytest 框架跑通

---

## Phase 2: 数据库表设计

### 设计原则

1. **软删除**：关键表使用 `is_deleted` + `deleted_at`（物理删除改为 `UPDATE`）
2. **软删除 + 唯一约束**：使用 partial unique index，例如 `UNIQUE(username) WHERE is_deleted = false`，避免软删除记录阻止新注册
3. **时间戳**：所有表 `TIMESTAMPTZ`
4. **ID**：ULID（VARCHAR(26)），时间有序
5. **冗余字段一致性**：`messages.user_id` 在 Repository 层写入时强制从 `sessions` 表获取，不接受外部传入

### 2.1 `users` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(26) PK | ULID |
| username | VARCHAR(64) NOT NULL | |
| email | VARCHAR(255) | |
| password_hash | VARCHAR(255) | bcrypt 哈希 |
| avatar_url | TEXT | |
| role | VARCHAR(16) DEFAULT 'user' | user / admin |
| is_active | BOOLEAN DEFAULT true | |
| oauth_provider | VARCHAR(32) | google/github（NULL=本地账号，预留） |
| oauth_id | VARCHAR(255) | 第三方用户 ID（预留） |
| failed_login_count | INT DEFAULT 0 | 连续失败次数 |
| locked_until | TIMESTAMPTZ | 账号锁定截止 |
| monthly_cost_limit | NUMERIC(10,2) | 用户级费用限额（覆盖全局） |
| is_deleted | BOOLEAN DEFAULT false | |
| deleted_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ NOT NULL | |
| updated_at | TIMESTAMPTZ NOT NULL | |

索引：
- `UNIQUE(username) WHERE is_deleted = false`
- `UNIQUE(email) WHERE email IS NOT NULL AND is_deleted = false`
- `UNIQUE(oauth_provider, oauth_id) WHERE oauth_provider IS NOT NULL`

### 2.2 `user_preferences` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(26) PK | |
| user_id | VARCHAR(26) FK → users.id UNIQUE | |
| theme | VARCHAR(16) DEFAULT 'system' | |
| default_model | VARCHAR(128) | |
| default_agent | VARCHAR(64) | |
| default_variant | VARCHAR(32) | |
| sidebar_open | BOOLEAN DEFAULT true | |
| right_panel_open | BOOLEAN DEFAULT false | |
| bottom_panel_height | INT DEFAULT 200 | |
| extra | JSONB DEFAULT '{}' | agent_overrides 等扩展 |

### 2.3 `projects` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(26) PK | |
| user_id | VARCHAR(26) FK → users.id | |
| name | VARCHAR(128) NOT NULL | |
| slug | VARCHAR(128) | |
| description | TEXT | |
| is_deleted | BOOLEAN DEFAULT false | |
| deleted_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ NOT NULL | |
| updated_at | TIMESTAMPTZ NOT NULL | |

索引：`(user_id)`, `UNIQUE(user_id, slug) WHERE is_deleted = false`

### 2.4 `sessions` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(26) PK | |
| user_id | VARCHAR(26) FK → users.id NOT NULL | |
| project_id | VARCHAR(26) FK → projects.id NOT NULL | |
| title | VARCHAR(255) | |
| slug | VARCHAR(128) | |
| agent | VARCHAR(64) | |
| model | VARCHAR(128) | |
| status | VARCHAR(16) DEFAULT 'idle' | idle/busy/retry/error/compacting |
| parent_id | VARCHAR(26) FK → sessions.id | 子会话 |
| token_usage | JSONB DEFAULT '{}' | |
| additions | INT DEFAULT 0 | |
| deletions | INT DEFAULT 0 | |
| files_changed | INT DEFAULT 0 | |
| sandbox_id | VARCHAR(64) | |
| is_deleted | BOOLEAN DEFAULT false | |
| deleted_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ NOT NULL | |
| updated_at | TIMESTAMPTZ NOT NULL | |

索引：`(user_id, project_id, is_deleted)`, `(user_id, created_at DESC)`, `(parent_id)`

### 2.5 `messages` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(26) PK | |
| session_id | VARCHAR(26) FK → sessions.id NOT NULL | |
| user_id | VARCHAR(26) FK → users.id NOT NULL | 冗余（repo 层强制从 session 获取） |
| role | VARCHAR(16) NOT NULL | user/assistant |
| agent | VARCHAR(64) | |
| model | VARCHAR(128) | |
| model_id | VARCHAR(128) | |
| variant | VARCHAR(32) | |
| provider_id | VARCHAR(128) | |
| format | VARCHAR(32) | |
| system | TEXT | |
| parent_id | VARCHAR(26) | |
| tokens | JSONB | |
| cost | NUMERIC(12,6) | 冗余，方便 SUM 聚合 |
| finish | VARCHAR(32) | |
| summary | BOOLEAN DEFAULT false | |
| error | JSONB | |
| created_at | TIMESTAMPTZ NOT NULL | |

索引：`(session_id, created_at)`, `(user_id)`

### 2.6 `parts` 表（单表多态）

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(26) PK | |
| message_id | VARCHAR(26) FK → messages.id NOT NULL | |
| session_id | VARCHAR(26) NOT NULL | 冗余 |
| user_id | VARCHAR(26) NOT NULL | 冗余 |
| type | VARCHAR(32) NOT NULL | text/reasoning/tool/step-start/step-finish/compaction/subtask/patch/file/agent/retry/plan |
| data | JSONB NOT NULL | |
| created_at | TIMESTAMPTZ NOT NULL | |

索引：
- `(message_id)`
- `(session_id, type)`
- `(user_id)`
- `GIN (data)`
- `((data->>'tool')) WHERE type = 'tool'`

### 2.7 `permission_rules` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(26) PK | |
| user_id | VARCHAR(26) FK → users.id NOT NULL | |
| project_id | VARCHAR(26) FK → projects.id | NULL = 全局 |
| permission | VARCHAR(128) NOT NULL | |
| pattern | VARCHAR(512) | |
| action | VARCHAR(16) NOT NULL | allow/deny |
| created_at | TIMESTAMPTZ NOT NULL | |

索引：`(user_id, project_id)`

### 2.8 `containers` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(26) PK | |
| user_id | VARCHAR(26) FK → users.id NOT NULL | |
| project_id | VARCHAR(26) FK → projects.id NOT NULL | |
| docker_id | VARCHAR(64) | |
| name | VARCHAR(128) NOT NULL | |
| status | VARCHAR(16) | creating/running/stopped/error |
| image | VARCHAR(255) | |
| port | INT | |
| api_key | VARCHAR(255) | |
| resource_limits | JSONB DEFAULT '{}' | |
| is_deleted | BOOLEAN DEFAULT false | |
| deleted_at | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ NOT NULL | |
| updated_at | TIMESTAMPTZ NOT NULL | |

索引：`(user_id, project_id)`, `UNIQUE(docker_id) WHERE docker_id IS NOT NULL`, `UNIQUE(port) WHERE port IS NOT NULL AND is_deleted = false`

> **端口唯一约束**：`UNIQUE(port)` 在数据库层防止多 Worker 分配同一端口。`docker.py:86-95` 的 socket.bind() 检测 + DB 唯一约束 = 双重保护。

### 2.9 `todos` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(26) PK | |
| session_id | VARCHAR(26) FK → sessions.id NOT NULL UNIQUE | |
| user_id | VARCHAR(26) NOT NULL | |
| items | JSONB NOT NULL | |
| updated_at | TIMESTAMPTZ NOT NULL | |

### 2.10 `prompt_history` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(26) PK | |
| user_id | VARCHAR(26) FK → users.id NOT NULL | |
| content | TEXT NOT NULL | |
| created_at | TIMESTAMPTZ NOT NULL | |

索引：`(user_id, created_at DESC)`

写入时自动清理超出 `max_prompt_history` 的旧记录。

### 2.11 `audit_logs` 表

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(26) PK | |
| user_id | VARCHAR(26) FK → users.id NOT NULL | |
| action | VARCHAR(64) NOT NULL | login/logout/session.create/session.delete/container.create/container.delete/permission.change/admin.* |
| resource_type | VARCHAR(32) | |
| resource_id | VARCHAR(26) | |
| details | JSONB | |
| ip_address | VARCHAR(45) | |
| user_agent | VARCHAR(512) | |
| created_at | TIMESTAMPTZ NOT NULL | |

索引：`(user_id, created_at DESC)`, `(action)`

只追加、不更新、不删除。定时清理 90 天以上记录。

### 2.12 Alembic 迁移

- `alembic upgrade head` **不在应用启动时自动执行**
- 原因：多 Worker 同时启动会并发执行迁移导致锁竞争
- 迁移通过 Makefile target `make migrate` 手动执行（或部署流水线中在启动 Worker 前执行一次）

**验收标准**：
- [ ] `make migrate` 能在空数据库上创建所有表
- [ ] 所有外键、唯一约束、部分索引正确
- [ ] `alembic downgrade -1` 能回退
- [ ] 对应的 Repository CRUD 单元测试通过（用 SQLite in-memory）

---

## Phase 3: 用户认证 + 安全加固

### 3.1 双 Token 架构

| Token | 有效期 | 存储位置 | 用途 |
|-------|--------|---------|------|
| Access Token | 15 分钟 | 前端内存 (Zustand) | `Authorization: Bearer {token}` |
| Refresh Token | 7 天 | HttpOnly Secure SameSite=Lax Cookie | 静默刷新 |

> **SameSite=Lax**（非 Strict）：开发环境前后端跨端口（localhost:5173 → localhost:8080），Strict 会导致 cookie 不发送。生产环境同域部署后可改为 Strict。

**流程**：
```
注册: POST /api/auth/register → 签发 access_token (body) + refresh_token (Set-Cookie)
登录: POST /api/auth/login → 同上
刷新: POST /api/auth/refresh → 浏览器自动带 cookie → 签发新 access_token
登出: POST /api/auth/logout → 双 Token jti 加入 Redis 黑名单 (TTL = 各自剩余有效期)
```

**前端首次加载（页面刷新后 Zustand 内存丢失）**：
```
1. 页面加载 → Zustand 无 access_token
2. 自动调用 POST /api/auth/refresh（浏览器自动带 HttpOnly cookie）
3. 成功 → 存新 access_token 到 Zustand → 正常渲染
4. 失败(cookie 过期/无效) → 跳转登录页
```

### 3.2 WebSocket 认证 — 一次性 Ticket

WebSocket 不支持自定义 header（握手阶段）。直接在 URL 放 JWT 有日志泄露风险。使用**一次性 Ticket**：

**Ticket 机制**：
```
1. POST /api/auth/ticket → 返回 {ticket: "<32字节随机token>"}, 存 Redis: ticket:{id} → {user_id}, TTL 30秒
2. new WebSocket("ws://host/ws/agent?ticket=xxx")
3. 后端验证 ticket → DEL ticket:{id}（原子操作，第二次使用必定失败）→ 提取 user_id → 建立连接
```

适用于：
- `ws://host/ws/agent` — **主 WebSocket**（替代原 SSE `GET /api/agent/event`，同时支持双向通信）
- `ws://host/ws/terminal/{id}` — 终端 WebSocket

> **SSE 全部移除**：原 `GET /api/agent/event` SSE 端点和 `GET /api/containers/sandbox-image/build` SSE 端点均被主 WebSocket 替代。构建进度事件通过主 WS 多路复用推送。

### 3.3 新增路由

```
backend/auth/
├── __init__.py
├── jwt.py           # 签发/验证/黑名单
├── middleware.py     # Depends(get_current_user)
├── ticket.py        # Ticket 签发/验证
├── routes.py        # 认证路由
└── password.py      # bcrypt 哈希 + 强度校验 (≥8字符, 含字母+数字)
```

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/auth/register` | POST | 注册 |
| `/api/auth/login` | POST | 登录 |
| `/api/auth/refresh` | POST | 刷新（cookie） |
| `/api/auth/logout` | POST | 登出 |
| `/api/auth/ticket` | POST | 签发 Ticket |
| `/api/auth/me` | GET | 当前用户 |
| `/api/auth/me/preferences` | GET/PUT | 偏好 |
| `/api/auth/me/prompt-history` | GET | Prompt 历史 |

**认证豁免**：仅 `/api/auth/register`、`/api/auth/login`、`/api/auth/refresh`、`/health`

### 3.4 暴力破解防护

| 层 | 实现 |
|----|------|
| IP 限频 | `/api/auth/login` → 5 次/分钟/IP（Redis INCR） |
| 账号锁定 | 连续 5 次错误 → `locked_until = now + 15min` |
| 注册限频 | 3 次/小时/IP |
| 密码强度 | ≥8 字符，含字母 + 数字 |

### 3.5 所有 API 路由认证改造

| 路由 | 当前 | 改造 | 严重级别 |
|------|------|------|---------|
| `api/sessions.py` | 无 | `Depends(get_current_user)` + user_id 过滤 | 高 |
| `api/containers.py` | 无 | 认证 + 所有权校验 + preview proxy 加固 | **严重** |
| `api/metadata.py` | 无 | 认证 + user_id 隔离 | 高 |
| `api/permissions.py` | 无 | 认证 + user_id 隔离 | 高 |
| `api/questions.py` | 无 | 认证 + user_id 隔离 | **严重** |
| `api/events.py` | 无 | **删除**（SSE → 主 WebSocket 替代） | **严重** |
| `api/ws.py` | 不存在 | **新建**：主 WebSocket 端点，Ticket 认证 + user_id 事件过滤 + 双向通信 | **严重** |
| `api/files.py` | 无 | 认证 + 容器所有权 | **严重** |
| `api/terminal.py` | 无 | Ticket 认证 + 容器所有权 | **严重** |

**隔离原则**：用户 A 访问用户 B 的资源 → 返回 **404**（不是 403，避免泄露资源存在性）

### 3.6 preview proxy 加固（`containers.py:101-223`）

- 添加认证 + `container.user_id == current_user.id` 校验
- 速率限制（防开放代理滥用）
- `api_key` 仅 backend→container 方向，不返回前端

### 3.7 前端认证改造

| 改造点 | 改造内容 |
|--------|---------|
| 新增 `LoginPage.tsx` | 登录/注册表单 |
| 新增 `stores/auth.ts` | Zustand store：access_token + refreshAccessToken() |
| `api.ts` request() | 加 `Authorization: Bearer {token}`；收到 401 → 调 refresh → 重试 |
| `api.ts` 401 竞态 | **使用 mutex**：多个并发请求同时 401 → 只有第一个调 refresh，其余等待结果后重试 |
| `api.ts` buildSandboxImage | **删除 EventSource 调用**（构建进度改为通过主 WS 推送） |
| `api.ts` getTerminalWsUrl | 先获取 ticket → 附加到 WS URL |
| **删除** `sse.ts` | SSEClient 整个删除，被 `ws.ts` 替代 |
| **新建** `ws.ts` | WebSocket 客户端：connect(ticket) + 收事件 + 发指令（详见 Phase 8.4） |
| `stores/ui.ts` | localStorage → `/api/auth/me/preferences` 服务端存取 |
| `App.tsx` | 路由守卫：无 token → refresh → 失败 → 登录页 |

**前端 401 刷新 mutex 伪代码**：
```typescript
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise  // 复用正在进行的 refresh
  refreshPromise = doRefresh().finally(() => { refreshPromise = null })
  return refreshPromise
}
```

**验收标准**：
- [ ] 未认证请求全部返回 401
- [ ] 用户 A 访问用户 B 资源返回 404
- [ ] Ticket 使用后再用返回 401
- [ ] 登录失败 5 次后账号锁定
- [ ] access_token 过期后前端无感刷新
- [ ] 页面刷新后通过 refresh cookie 恢复登录态
- [ ] 多个并发 401 只触发一次 refresh
- [ ] 主 WebSocket 连接正常建立和认证

---

## Phase 4: Repository 实现 + 数据层切换

### 4.1 替换策略 — 直接替换（非渐进）

> **关键决策**：不采用"渐进替换"（原方案），改为 **直接替换**。原因：storage.py 的 key-path 模型（`["session", "default", session_id]`）和 Repository 的关系模型完全不同，中间态兼容层会引入更多 bug。

执行顺序：
1. 实现所有 Repository（带测试）
2. 修改 `session/session.py` — 一次性将全部 21 处 storage 调用切到 Repository
3. 修改 `session/todo.py` — 2 处
4. 修改 `agent/compaction.py` — 1 处
5. 修改 `agent/loop.py` — 6 处
6. 移除 `storage.py` import

### 4.2 `session/session.py` — 21 处 storage 调用替换

| 行号 | 当前调用 | 替换为 |
|------|---------|--------|
| 70 | `storage.write(["session", pid, sid], ...)` | `session_repo.create(user_id, session)` |
| 84 | `storage.read(["session", "default", sid])` | `session_repo.get(sid, user_id)` |
| 92 | `storage.list_keys(["session", "default"])` | `session_repo.list_by_user(user_id, project_id)` |
| 95 | `storage.read(key)` | （合并到上面的 list 查询中，一次返回） |
| 114 | `storage.list_keys(["message", sid])` | `session_repo.soft_delete(sid, user_id)` — DB CASCADE |
| 118 | `storage.list_keys(["part", mid])` | （CASCADE 自动处理） |
| 120 | `storage.remove(pk)` | （CASCADE 自动处理） |
| 121 | `storage.remove(key)` | （CASCADE 自动处理） |
| 124 | `storage.remove(["session", pid, sid])` | （上面 soft_delete 已处理） |
| 144 | `storage.write(["session", pid, sid], ...)` | `session_repo.update(sid, user_id, **kwargs)` |
| 224 | `storage.write(["message", sid, mid], ...)` | `message_repo.create(user_id, msg_info)` |
| 235 | `storage.write(["part", mid, pid], ...)` | `part_repo.create(user_id, part)` |
| 273 | `storage.write(["message", sid, mid], ...)` | `message_repo.create(user_id, msg_info)` |
| 299 | `storage.write(["message", sid, mid], ...)` | `message_repo.update(mid, **fields)` |
| 330 | `storage.write(["part", mid, pid], ...)` | `part_repo.upsert(user_id, part)` |
| 346 | `storage.list_keys(["message", sid])` | `message_repo.list_by_session(sid)` — 一次 JOIN |
| 350 | `storage.read(key)` | （JOIN 已包含） |
| 357 | `storage.list_keys(["part", mid])` | （JOIN 已包含） |
| 360 | `storage.read(pk)` | （JOIN 已包含） |

> **N+1 解决**：当前 `get_messages()` 先 list session 的所有 message key（1次），再逐个 read message（N次），再对每个 message list part key（N次），再逐个 read part（M次）。替换后一次 `SELECT m.*, p.* FROM messages m LEFT JOIN parts p ON ... WHERE m.session_id = ? ORDER BY m.created_at, p.created_at` 搞定。

### 4.3 `session/todo.py` — 2 处

| 行号 | 当前 | 替换为 |
|------|------|--------|
| 15 | `storage.read(["todo", session_id])` | `todo_repo.get(session_id, user_id)` |
| 23 | `storage.write(["todo", session_id], ...)` | `todo_repo.upsert(session_id, user_id, items)` |

### 4.4 `agent/compaction.py` — 1 处

| 行号 | 当前 | 替换为 |
|------|------|--------|
| 363 | `storage.write(["part", mid, pid], part_data)` | `part_repo.update(pid, data=part_data)` |

### 4.5 `agent/loop.py` — 6 处

| 行号 | 当前 | 替换为 |
|------|------|--------|
| 106 | `storage.list_keys(["part", message_id])` | `part_repo.list_by_message(message_id)` |
| 109 | `storage.read(pk)` | （上面已返回完整数据） |
| 167 | `storage.read(pk)` | （同上） |
| 750 | `storage.write(["part", mid, pid], p)` | `part_repo.update(pid, data=p)` |
| 1029+1032 | `storage.list_keys/read(["part", last_user_id])` | `part_repo.list_by_message(last_user_msg_id)` |
| 1089+1092 | 同上（plan mode 分支） | 同上 |

### 4.6 改造 `sandbox/docker.py`

- `create_container()` 后同步写入 `containers` 表
- `delete_container()` 后软删除
- 启动时从 DB + Docker daemon 双向对账
- 容器绑定 `user_id + project_id`
- 端口分配：socket.bind() + DB UNIQUE(port) 双重保护

### 4.7 改造 `sandbox/manager.py`

- `acquire()` 新增 `user_id` 参数，从 DB 查找现有容器
- 废弃 `get_client_any()`（`manager.py:204-219`） → `get_client(user_id, project_id)`

### 4.8 改造 `permission/permission.py`

- `_approved` 列表 → 从 `permission_repo.list_rules(user_id)` 加载 + Redis 缓存
- `reply()` 中 "always" → `permission_repo.create_rule(user_id, ...)`

### 4.9 删除 `storage/storage.py`

所有 30 处调用替换完成后，删除此文件。

**验收标准**：
- [ ] `storage.py` 不再被任何代码 import
- [ ] session CRUD 通过 PostgreSQL
- [ ] `get_messages()` 一次查询返回完整数据（验证无 N+1）
- [ ] 权限规则重启后仍在
- [ ] 容器记录持久化，重启后从 DB 恢复
- [ ] 每个 repository 有对应的单元测试

---

## Phase 5: Agent Loop 用户上下文注入

### 5.1 ToolContext 添加字段（`tool/tool.py:22-38`）

```python
@dataclass
class ToolContext:
    session_id: str = ""
    user_id: str = ""        # 新增
    project_id: str = ""     # 新增
    sandbox: Any = None
    bus: Any = None
    abort: asyncio.Event = field(default_factory=asyncio.Event)
    message_id: str = ""
    part_id: str = ""
    workdir: str = "/workspace"
    _on_output: Any = None
```

### 5.2 run_loop() 注入 user_id（`loop.py:188`）

当前签名：`async def run_loop(session_id: str)`
改为：`async def run_loop(session_id: str, user_id: str)`

同时：
- **重命名** `last_user_id` → `last_user_msg_id`（当前名称在多用户上下文中极易与 user identity 混淆）
- 替换所有 6 处 storage 直接调用（见 Phase 4.5）
- `user_id` 传递到 ToolContext、ToolHooks

### 5.3 ToolHooks 添加 user_id（`hooks.py:17-24`）

当前：`__init__(self, session_id: str, ...)`
改为：`__init__(self, session_id: str, user_id: str, ...)`

- 权限检查按 `user_id` 查询
- 所有 4 处 `bus.publish()` 附带 `userId`

### 5.4 task.py 子任务映射（`task.py:33-38`）

当前直接访问私有字段：
```python
sandbox_manager._session_project[child.id] = parent_project
```

改造：新增公开方法 `SandboxManager.bind_child_session(parent_sid, child_sid, user_id)` 内部做所有权验证后映射。

### 5.5 revert.py 持久化（`revert.py:14`）

`_revert_snapshots: dict[str, str]` → Redis key: `revert:{session_id}`, TTL 1h

### 5.6 事件 Payload 标准化

所有 **28 处** `bus.publish()` 必须在 data 中包含 `userId`：

| 文件 | 调用数 | 行号 |
|------|--------|------|
| `session/session.py` | 8 | 72, 155, 164, 191, 248, 289, 314, 337 |
| `agent/loop.py` | 8 | 323, 496, 517, 620, 628, 674, 679, 762 |
| `agent/compaction.py` | 5 | 118, 200, 229, 263, 268 |
| `agent/hooks.py` | 4 | 117, 133, 161, 176 |
| `question/question.py` | 3 | 83, 104, 120 |
| `permission/permission.py` | 2 | 138, 199 |
| `session/todo.py` | 1 | 24 |
| `agent/retry.py` | 1 | 127 |

标准 payload：`{"type": str, "data": {"sessionId": str, "userId": str, ...}}`

### 5.7 WebSocket 协议定义

**服务端 → 客户端**（事件推送，与当前 bus 事件一致）：

```jsonc
// Session 事件
{"type": "session.status",     "data": {"sessionId": "...", "userId": "...", "status": "busy"}}
{"type": "session.title",      "data": {"sessionId": "...", "userId": "...", "title": "..."}}
{"type": "session.error",      "data": {"sessionId": "...", "userId": "...", "error": {"message": "..."}}}
{"type": "session.updated",    "data": {"sessionId": "...", "userId": "...", "token_usage": {...}}}
{"type": "session.diff",       "data": {"sessionId": "...", "userId": "..."}}
{"type": "session.compaction.start",    "data": {"sessionId": "...", "userId": "..."}}
{"type": "session.compaction.complete", "data": {"sessionId": "...", "userId": "..."}}

// Message 事件 (LLM 流式输出)
{"type": "message.created",    "data": {"sessionId": "...", "userId": "...", "message": {...}}}
{"type": "message.updated",    "data": {"sessionId": "...", "userId": "...", "message": {...}}}
{"type": "message.text_delta", "data": {"sessionId": "...", "userId": "...", "messageId": "...", "partId": "...", "text": "..."}}

// Part 事件
{"type": "part.created",  "data": {"sessionId": "...", "userId": "...", "messageId": "...", "part": {...}}}
{"type": "part.updated",  "data": {"sessionId": "...", "userId": "...", "messageId": "...", "part": {...}}}
{"type": "part.delta",    "data": {"sessionId": "...", "userId": "...", "messageId": "...", "partId": "...", "delta": "..."}}

// Tool 事件
{"type": "tool.running",   "data": {"sessionId": "...", "userId": "...", "partId": "...", "tool": "...", "input": {...}}}
{"type": "tool.completed", "data": {"sessionId": "...", "userId": "...", "partId": "...", "output": "...", "title": "..."}}
{"type": "tool.error",     "data": {"sessionId": "...", "userId": "...", "partId": "...", "error": "..."}}

// 交互事件（注意：统一使用 camelCase sessionId，Pydantic model_dump 时需配置 alias）
{"type": "permission.asked",   "data": {"id": "...", "sessionId": "...", "userId": "...", "tool": "...", ...}}
{"type": "permission.replied", "data": {"id": "...", "sessionId": "...", "userId": "...", "action": "..."}}
{"type": "question.asked",     "data": {"id": "...", "sessionId": "...", "userId": "...", "questions": [...]}}
{"type": "question.replied",   "data": {"id": "...", "sessionId": "...", "userId": "..."}}
{"type": "question.rejected",  "data": {"id": "...", "sessionId": "...", "userId": "..."}}
{"type": "todo.updated",       "data": {"sessionId": "...", "userId": "..."}}

// 构建事件 (替代原 SSE /api/containers/sandbox-image/build)
{"type": "build.progress", "data": {"userId": "...", "step": "building", "message": "..."}}
{"type": "build.complete", "data": {"userId": "...", "message": "Sandbox image built successfully"}}
{"type": "build.error",    "data": {"userId": "...", "message": "..."}}

// 系统事件
{"type": "server.connected", "data": {}}
{"type": "server.heartbeat", "data": {}}
```

**客户端 → 服务端**（指令）：

```jsonc
// Permission 回复（替代 POST /api/agent/permission/{id}）
{"type": "permission.reply", "id": "req_xxx", "action": "once|always|reject", "message": "..."}

// Question 回复（替代 POST /api/agent/question/{id}）
{"type": "question.reply", "id": "req_xxx", "answers": [["选项A"], ["选项B"]]}

// Question 拒绝（替代 POST /api/agent/question/{id}/reject）
{"type": "question.reject", "id": "req_xxx"}

// Abort（替代 POST /api/agent/session/{id}/abort）
{"type": "session.abort", "sessionId": "sess_xxx"}

// 触发构建（替代原 GET /api/containers/sandbox-image/build SSE）
{"type": "build.start"}
```

**验收标准**：
- [ ] `run_loop()` 签名包含 `user_id`
- [ ] ToolContext 包含 `user_id` 和 `project_id`
- [ ] `last_user_id` 已重命名为 `last_user_msg_id`
- [ ] 28 处 bus.publish 全部包含 userId
- [ ] `task.py` 不再直接访问 `_session_project` / `_project_map`

---

## Phase 6: 全局单例隔离

### 6.1 Skill/Command 两阶段加载

当前（`skill.py:21-22`、`command.py:22-23`）：全局 `_skills`/`_commands` dict + `_loaded` flag。

改造：
1. **全局**：`~/.config/openbox/skills/` → 启动时加载一次，只读
2. **用户级**：容器 `/data/skills/` → 通过 SandboxClient 获取，按 `(user_id, project_id)` 缓存

### 6.2 MCP Client 实例池

当前（`mcp/client.py:172-173`）：`mcp_client = McpClient()` 全局单例。

改造：`McpClientPool` 类，按 `(user_id, project_id)` 管理实例。`tool/mcp_tool.py` 从 pool 获取。

### 6.3 Tool Registry 自定义工具隔离

当前（`tool/registry.py:14`）：`_tools` 全局 dict。

改造：
- 内置工具（bash, read, write 等）保持全局只读
- 自定义工具（`.openbox/tools/`）从容器内加载

### 6.4 Project 单例替换

当前（`project/instance.py:5-6`）：`_project = None` 全局单例。

改造：从 `projects` 表按 `(user_id, project_id)` 查询。

### 6.5 Truncation 输出隔离

当前（`tool/truncation.py:27-34`）：`~/.local/share/openbox/tool-output/` 全局共享。

改造：`~/.local/share/openbox/tool-output/{user_id}/`

### 6.6 Instruction 清理

当前（`session/instruction.py:19`）：`_claims: dict[str, set[str]] = {}` 无清理。

改造：按 `session_id` 分组，session 删除时清理。

### 6.7 Per-user Agent 配置

内置 AGENTS 只读 + 用户覆盖存 `user_preferences.extra["agent_overrides"]`。

**验收标准**：
- [ ] 用户 A 安装的 skill 对用户 B 不可见
- [ ] 用户 A 的 MCP server 对用户 B 不可见
- [ ] 全局 `_project` 单例已废弃

---

## Phase 7: Redis 缓存 + 跨 Worker 通信

### 7.1 缓存策略

| 数据 | Key | TTL | 写策略 |
|------|-----|-----|--------|
| 用户信息 | `user:{id}` | 10min | 写穿透 |
| 用户偏好 | `pref:{id}` | 10min | 写穿透 |
| 会话列表 | `sessions:{uid}:{pid}` | 5s | 写穿透 |
| 会话详情 | `session:{id}` | 60s | 写穿透 |
| 容器状态 | `container:{uid}:{pid}` | 15s | 写穿透 |
| 权限规则 | `permissions:{uid}:{pid}` | 5min | 写穿透 |
| JWT 黑名单 | `jwt_bl:{jti}` | = 剩余有效期 | 即时 |
| Ticket | `ticket:{id}` | 30s | 即时 + 使用后 DEL |
| Revert 快照 | `revert:{sid}` | 1h | 即时 |
| 速率限制 | `rl:{ip_or_uid}:{endpoint}` | 窗口期 | INCR |
| 在线状态 | `online:{uid}` | 5min | 每次请求 SETEX |

### 7.2 跨 Worker 通信 — Redis Pub/Sub + WebSocket

当前 `bus/bus.py` 是进程内广播。多 Worker 部署时跨 Worker 不可达。

**改造 `bus/bus.py` 为混合架构**：

```python
# 发布时
def publish(event_type, data):
    event = {"type": event_type, "data": data, "event_id": generate_id(), "worker_id": WORKER_ID}
    # 1. 本进程内立即分发（同当前逻辑）
    _dispatch_local(event)
    # 2. 同时发到 Redis Pub/Sub → 其他 Worker 的 WS handler 收到后推送给对应用户
    redis.publish(f"bus:{data.get('userId', 'global')}", json.dumps(event))

# 每个 Worker 启动时订阅
async def _redis_listener():
    async for message in redis.subscribe("bus:*"):
        event = json.loads(message)
        if event["worker_id"] == WORKER_ID:
            continue  # 跳过自己发的
        _dispatch_local(event)
```

**事件推送链路**：
```
Agent Loop (Worker A) → bus.publish() → Redis Pub/Sub → Worker B → WS handler → 推送到该用户的 WebSocket 连接
```

### 7.3 Permission/Question 跨 Worker — WebSocket 双向通信

当前 `permission.py` 和 `question.py` 使用 `asyncio.Event` 阻塞等待用户回复。这是**进程内阻塞**，跨 Worker 不可达。

**场景**：Worker A 运行 agent loop → `permission.ask()` 阻塞等待 → 用户通过 WebSocket 发回复 → 回复被 Worker B 的 WS handler 接收 → Worker A 等不到。

**改造方案（WebSocket + Redis Pub/Sub 协同）**：

```python
# permission.py ask() 改造
async def ask(session_id, user_id, ...):
    request_id = generate_id()
    # 1. 将请求信息存入 Redis
    await redis.set(f"perm_req:{request_id}", json.dumps(request_data), ex=300)
    # 2. 发布 PERMISSION_ASKED 事件 → bus → Redis Pub/Sub → WS handler → 前端 WebSocket
    bus.publish(PERMISSION_ASKED, request.model_dump())
    # 3. 订阅 Redis channel 等待回复
    async for msg in redis.subscribe(f"perm_reply:{request_id}"):
        reply_data = json.loads(msg)
        # 处理回复（"always" 规则持久化等）...
        break

# permission.py reply() 改造 — 由 WS handler 调用（用户通过 WebSocket 发送回复）
async def reply(request_id, action, message=None):
    request_data = await redis.get(f"perm_req:{request_id}")
    if not request_data:
        return  # 已过期或已处理
    await redis.delete(f"perm_req:{request_id}")
    # 通过 Redis Pub/Sub 通知等待中的 Worker（可能在任意 Worker 上）
    await redis.publish(f"perm_reply:{request_id}", json.dumps({"action": action, "message": message}))
    # "always" 规则持久化...
```

`question.py` 同理。

> **REST 端点同样适用**：`POST /api/agent/permission/{id}` 和 `POST /api/agent/question/{id}` REST 端点保留为 API 兼容入口。它们内部同样调用 `permission.reply()` / `question.reply()`，走的是同一套 Redis Pub/Sub 机制。前端主路径走 WebSocket，但 REST 端点也能正确触发跨 Worker 回复。

**完整流程图**：
```
前端 ──WS──→ Worker B (WS handler) ──Redis publish──→ Worker A (agent loop 等待)
             │                                          │
             │ 用户发: {"type":"permission.reply",      │ redis.subscribe("perm_reply:xxx")
             │   "id":"xxx","action":"always"}          │ 收到回复 → ask() 返回 → loop 继续
             │                                          │
             └─ 调用 permission.reply(id, action)       │
```

### 7.4 分布式锁

| 资源 | Lock Key | 说明 |
|------|----------|------|
| 容器创建/删除 | `lock:container:{uid}:{pid}` | 防止并发创建 |
| Blob 同步 | `lock:sync:{uid}:{pid}` | 防止并发同步 |

**验收标准**：
- [ ] 双 Worker 部署时 WS 事件跨 Worker 可达
- [ ] Permission ask (Worker A) / reply via WS (Worker B) 正常工作
- [ ] Question ask/reply 跨 Worker 正常工作
- [ ] Abort 信号跨 Worker 生效

---

## Phase 8: 前端改造 + main.py 改造

### 8.1 `backend/main.py` 改造

**启动时**（lifespan）：
1. 校验 `JWT_SECRET`
2. 初始化 PostgreSQL 连接池
3. 初始化 Redis 连接池
4. 初始化 Azure Blob 客户端
5. 初始化 `WSConnectionManager`
6. 启动 Redis Pub/Sub 订阅 listener（后台 task）— 接收跨 Worker 事件 → 推送到本 Worker 的 WS 连接
7. 容器状态对账（DB ↔ Docker daemon）
8. 注册 auth 路由 + WS 路由
9. 现有 `_init_agent()` 逻辑

**关闭时**：
1. **关闭所有 WebSocket 连接**（发送 close frame with code 1001 "going away"）
2. **通知所有活跃 agent loop 中止**（设置 abort signal）
3. **等待最多 30 秒让活跃 loop 完成当前 step**
4. 检查 sessions 表中 status=BUSY 的记录 → 标记为 ERROR（处理意外中断）
5. 现有容器清理
6. 关闭 Redis Pub/Sub listener
7. 关闭 Redis 连接池
8. 关闭 DB 连接池
9. 关闭 Blob 客户端

### 8.2 `docker-compose.yml` 改造

```yaml
services:
  backend:
    environment:
      - DATABASE_URL=postgresql+asyncpg://root:73SdesGJ9Z61CA8H0ajh4MyTRkzK5U2w@107.175.44.162:31938/openbox
      - REDIS_URL=redis://redis:6379/0
      - BLOB_AZURE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=adsblob;AccountKey=RRx7QTZ9/MzsfVpu13qvL2ScKHngVynI1AM22bcGJ6ow0SzCQvaMl9sMQDR+8Hlvu2bSwE+dbmFL+AStrg60Kg==;EndpointSuffix=core.windows.net
      - BLOB_AZURE_CONTAINER=ads-staging
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      - redis
  redis:
    image: redis:7-alpine
    restart: unless-stopped
  frontend:
    # ... 现有配置
```

> PostgreSQL 使用外部服务器。需在 107.175.44.162:31938 上手动创建 `openbox` 数据库。

### 8.3 `Makefile` 新增

```makefile
deps:          ## Start dev dependencies (PG + Redis + Azurite)
migrate:       ## Run Alembic migrations
migrate-json:  ## Migrate JSON data to PostgreSQL
test:          ## Run all tests
test-isolation: ## Run multi-user isolation tests
```

### 8.4 新建 `backend/api/ws.py` — 主 WebSocket 端点

**替代原 `api/events.py`（SSE）**，同时承担双向通信。

```python
@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket, ticket: str):
    # 1. Ticket 认证
    user_id, user_role = await verify_and_consume_ticket(ticket)
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()

    # 2. 注册到 WS 连接管理器（按 user_id）
    send_queue = ws_manager.register(user_id, websocket)

    # 3. 发送初始连接确认
    await send_queue.put({"type": "server.connected", "data": {}})

    try:
        # 4. 三个并发任务：接收客户端消息 + 发送服务端事件 + 心跳
        await asyncio.gather(
            _receive_loop(user_id, user_role, websocket, send_queue),
            _send_loop(websocket, send_queue),
            _heartbeat_loop(send_queue),
        )
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.unregister(user_id, websocket)

async def _receive_loop(user_id, user_role, ws, send_queue):
    """接收并处理客户端消息。"""
    async for raw in ws.iter_text():
        msg = json.loads(raw)
        await _handle_client_message(user_id, user_role, msg)

async def _send_loop(ws, send_queue):
    """从 send_queue 取事件发给客户端（保证串行发送，避免并发 send 损坏帧）。"""
    while True:
        event = await send_queue.get()
        await ws.send_json(event)

async def _heartbeat_loop(send_queue):
    """每 25 秒发一次心跳（低于常见 proxy 30 秒超时）。"""
    while True:
        await asyncio.sleep(25)
        await send_queue.put({"type": "server.heartbeat", "data": {}})
```

> **关键设计**：每个 WebSocket 连接有独立的 `asyncio.Queue` 作为 send queue。所有推送（bus 事件、心跳）都先入队列，由 `_send_loop` 串行取出发送。这避免了多个协程并发调用 `ws.send_json()` 导致 WebSocket 帧损坏的问题。

**客户端→服务端消息处理**（`_handle_client_message`）：

```python
async def _handle_client_message(user_id: str, user_role: str, msg: dict):
    msg_type = msg.get("type")
    if msg_type == "permission.reply":
        await permission.reply(msg["id"], msg["action"], msg.get("message"))
    elif msg_type == "question.reply":
        await question.reply(msg["id"], msg["answers"])
    elif msg_type == "question.reject":
        await question.reject(msg["id"])
    elif msg_type == "session.abort":
        await abort_session(msg["sessionId"], user_id)  # 内部验证 session 归属
    elif msg_type == "build.start":
        if user_role != "admin":
            return  # 仅 admin 可触发构建
        asyncio.create_task(_stream_build_to_ws(user_id))
```

**WS 连接管理器**（`ws_manager`）：

```python
class WSConnectionManager:
    """管理所有用户的 WebSocket 连接。每个连接有独立的 send queue。"""
    _connections: dict[str, dict[WebSocket, asyncio.Queue]]  # user_id -> {ws: queue}

    def register(self, user_id: str, ws: WebSocket) -> asyncio.Queue:
        """注册连接，返回该连接的 send queue。"""
        queue = asyncio.Queue()
        self._connections.setdefault(user_id, {})[ws] = queue
        return queue

    def unregister(self, user_id: str, ws: WebSocket): ...

    async def send_to_user(self, user_id: str, event: dict):
        """将事件放入该用户所有连接的 send queue（多标签页全部收到）。"""
        for ws, queue in self._connections.get(user_id, {}).items():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # 连接积压过多，丢弃

    async def broadcast(self, event: dict):
        """发给所有用户（admin 广播）。"""
        for user_queues in self._connections.values():
            for ws, queue in user_queues.items():
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass
```

bus 事件 → WS 推送链路：
```
bus.publish() → _dispatch_local() → WS handler 检查 event["data"]["userId"]
                                   → ws_manager.send_to_user(userId, event)
```

**该端点替代的原有功能**：

| 原功能 | 原实现 | 新实现（通过主 WS） |
|--------|--------|---------------------|
| 实时事件推送 | SSE `GET /api/agent/event`（`events.py`） | 服务端通过 WS 推送 |
| 构建进度推送 | SSE `GET /api/containers/sandbox-image/build`（`containers.py:27-33`） | 构建事件类型 `build.progress` / `build.complete` / `build.error` 通过主 WS 推送 |
| Permission 回复 | REST `POST /api/agent/permission/{id}`（`permissions.py`） | 客户端通过 WS 发 `{"type":"permission.reply",...}` |
| Question 回复 | REST `POST /api/agent/question/{id}`（`questions.py`） | 客户端通过 WS 发 `{"type":"question.reply",...}` |
| Question 拒绝 | REST `POST /api/agent/question/{id}/reject` | 客户端通过 WS 发 `{"type":"question.reject",...}` |
| Abort Session | REST `POST /api/agent/session/{id}/abort`（`sessions.py`） | 客户端通过 WS 发 `{"type":"session.abort",...}` |

> **注意**：上述 REST 端点**保留不删除**（API 兼容性），但前端主路径改为 WebSocket。REST 端点可用于 curl / API 调用等非浏览器场景。

### 8.5 删除 `backend/api/events.py`（SSE 端点）

整个文件删除（43 行）。其功能完全由 `api/ws.py` 替代。

### 8.6 改造 `backend/api/containers.py` — 移除构建 SSE

当前 `containers.py:27-33` 的 `build_sandbox_image()` 返回 `EventSourceResponse`。

改造：
- 将 `docker_manager.build_sandbox_image()` 的事件改为通过 bus → 主 WS 推送
- 改为 REST `POST /api/containers/sandbox-image/build`（触发构建，立即返回 `{"ok": true}`）
- 构建进度通过 WS 事件类型 `build.progress` / `build.complete` / `build.error` 推送

### 8.7 前端完整改造清单

| 文件 | 改造 |
|------|------|
| **新建** `LoginPage.tsx` | 登录/注册表单 |
| **新建** `stores/auth.ts` | access_token + refreshAccessToken() (含 mutex) |
| **新建** `services/ws.ts` | 主 WebSocket 客户端（替代 `sse.ts`，详见下方） |
| **删除** `services/sse.ts` | 整个文件删除（82 行），被 `ws.ts` 替代 |
| **重写** `hooks/useSSE.ts` → `hooks/useWS.ts` | 22 个事件订阅迁移到 WS + 新增客户端发送能力 |
| **重写** `types/sse.ts` → `types/ws.ts` | 类型重命名 SSE* → WS*，新增客户端消息类型 |
| `api.ts` request() | + `Authorization` header；+ 401 自动 refresh + 重试 |
| `api.ts` buildSandboxImage | **删除 EventSource 版本**，改为 REST POST（进度通过 WS 推送） |
| `api.ts` getTerminalWsUrl | + ticket |
| `api.ts` | **删除** `replyPermission`、`replyQuestion`、`rejectQuestion`、`abortSession` REST 调用（改为 WS 发送） |
| `CreateContainerDialog.tsx` | 移除 EventSource（`useRef<EventSource>`），构建进度从 WS 事件获取 |
| `SandboxRequiredDialog.tsx` | 同上 |
| `stores/ui.ts` | → 服务端 `/api/auth/me/preferences` |
| `App.tsx` | 路由守卫 + `useWS()` 替代 `useSSE()` |

**新建 `services/ws.ts`**：

```typescript
export class AgentWSClient {
  private ws: WebSocket | null = null
  private handlers: Map<string, Set<EventHandler>> = new Map()
  private reconnectTimer: number | null = null

  async connect() {
    const ticket = await api.getTicket()  // POST /api/auth/ticket
    const wsBase = (BASE_URL || window.location.origin).replace(/^http/, "ws")
    this.ws = new WebSocket(`${wsBase}/ws/agent?ticket=${ticket}`)

    this.ws.onmessage = (event) => {
      const parsed = JSON.parse(event.data)
      this.dispatch(parsed.type, parsed.data)
    }

    this.ws.onclose = () => {
      this.dispatch("__disconnected", {})
      // 3 秒后重连（重新获取 ticket）
      this.reconnectTimer = window.setTimeout(() => this.connect(), 3000)
    }

    this.ws.onopen = () => {
      this.dispatch("__connected", {})
    }
  }

  // 客户端→服务端：发送指令
  send(msg: WSClientMessage) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  // 便捷方法
  replyPermission(id: string, action: string, message?: string) {
    this.send({ type: "permission.reply", id, action, message })
  }
  replyQuestion(id: string, answers: string[][]) {
    this.send({ type: "question.reply", id, answers })
  }
  rejectQuestion(id: string) {
    this.send({ type: "question.reject", id })
  }
  abortSession(sessionId: string) {
    this.send({ type: "session.abort", sessionId })
  }
  startBuild() {
    this.send({ type: "build.start" })
  }

  // 事件订阅（与原 SSEClient 接口一致）
  on(event: string, handler: EventHandler) { ... }
  off(event: string, handler: EventHandler) { ... }
  disconnect() { ... }
}

export const wsClient = new AgentWSClient()
```

**`hooks/useWS.ts`**：与原 `useSSE.ts` 结构完全一致（22 个事件订阅），只是把 `sseClient` 替换为 `wsClient`。事件名不变（`session.status`、`message.text_delta` 等）。

**断线恢复**：WS 断线 → 3 秒后重连 → 重新获取 ticket → 重连成功后全量刷新状态（调 REST API 拉当前 session/messages）。

**验收标准**：
- [ ] 前端登录/注册/登出完整流程
- [ ] 页面刷新后自动恢复登录态
- [ ] WS 断线重连 + 状态刷新
- [ ] 偏好跨设备同步

---

## Phase 9: Azure Blob 同步

### 9.1 同步策略 — 文件级增量

不使用全量 tar 包。使用 manifest 驱动的文件级增量同步。

```python
class SyncManifest(BaseModel):
    files: dict[str, FileEntry]  # relative_path -> entry
    active_sessions: list[str]
    last_sync_at: str

class FileEntry(BaseModel):
    size: int
    mtime: float
    sha256: str | None = None
```

**流程**：
1. 读远程 `manifest.json`
2. 扫本地目录，对比 mtime + size
3. 变更文件逐个上传
4. 删除文件从 Blob 移除
5. 更新 `manifest.json`

### 9.2 Blob 结构

```
ads-staging/
└── userdata/{user_id}/{project_id}/
    ├── workspace/...        # 增量同步
    ├── data.tar.zst         # /data 压缩备份（较小）
    ├── home.tar.zst         # /home/sandbox 压缩备份
    └── manifest.json
```

### 9.3 同步生命周期

| 事件 | 动作 |
|------|------|
| 容器创建 | 检查 Blob 有无备份 → 有则恢复 |
| 运行中 | 每 10 分钟增量同步（跳过 BUSY 状态 session 目录） |
| 容器停止 | 全量同步 |
| 容器删除 | 全量同步 → 清理本地缓存 |
| Session 删除 | 从 manifest 移除 + 清理 Blob 中该 session 文件 |

### 9.4 排除文件

`node_modules/`, `__pycache__/`, `.venv/`, `dist/`, `build/`, `*.pyc`, `*.o`, `*.so`, `.git/objects/pack/`

### 9.5 Bind Mount 替代 Named Volume

当前（`docker.py:128-134`）用 Named Volume。改为 Bind Mount：

```python
base = f"/opt/openbox/cache/{user_id}/{project_id}"
volumes = {
    f"{base}/workspace": {"bind": "/workspace", "mode": "rw"},
    f"{base}/data": {"bind": "/data", "mode": "rw"},
    f"{base}/home": {"bind": "/home/sandbox", "mode": "rw"},
}
```

**Bind Mount 权限处理**：容器内用户（uid 1000）和宿主机目录权限不一致的问题：
- 在 Dockerfile 中创建容器用户时指定 `uid=1000`
- 宿主机 bind mount 目录创建时 `chown 1000:1000`
- 或在 `docker run` 时使用 `--user 1000:1000`

### 9.6 备份保留策略

| 场景 | 保留 |
|------|------|
| 活跃项目 | 始终保留最新 |
| 已删除项目 | 30 天后清理 |
| 已删除用户 | 90 天后清理 |

**验收标准**：
- [ ] 容器创建时自动恢复 Blob 备份
- [ ] 10 分钟增量同步正常
- [ ] Session 删除后对应文件从 Blob 清理
- [ ] Bind mount 权限无问题

---

## Phase 10: 用户配额 + 成本控制

### 10.1 配额检查

| 操作 | 检查 | 超限返回 |
|------|------|---------|
| 创建容器 | `count(containers WHERE user_id=? AND is_deleted=false) < max_containers` | 429 |
| 创建 session | `count(sessions WHERE user_id=? AND is_deleted=false) < max_sessions` | 429 |
| 启动 agent | `count(sessions WHERE user_id=? AND status='busy') < max_concurrent` | 429 |
| Blob 同步 | `sum(blob_size) < max_storage_mb` | 跳过同步 + 通知 |

### 10.2 LLM 成本控制

Agent loop 每步开始前检查：
```python
total = await message_repo.sum_cost_this_month(user_id)
limit = user.monthly_cost_limit or config.monthly_cost_limit
if total >= limit:
    # 返回友好提示，不突然中断
```

**验收标准**：
- [ ] 超容器限额返回 429 + 清晰错误信息
- [ ] 月度费用超限 agent 拒绝执行

---

## Phase 11: 数据迁移 + 最终清理

### 11.1 JSON → PostgreSQL 迁移脚本

`backend/scripts/migrate_json_to_pg.py`

**策略**：
1. 创建默认用户（用户名/密码从环境变量读取）和默认项目
2. 遍历 `~/.local/share/openbox/storage/` 目录
3. 批量 INSERT sessions → messages → parts → todos（每 500 条一批）
4. 幂等可重跑（检查 session.id 是否已存在）
5. 旧数据目录重命名为 `*.bak`

**迁移对象**：

| 旧路径 | 新表 |
|--------|------|
| `storage/session/{project_id}/{id}` | sessions |
| `storage/message/{session_id}/{id}` | messages |
| `storage/part/{message_id}/{id}` | parts |
| `storage/todo/{session_id}` | todos |

### 11.2 回滚脚本

`backend/scripts/migrate_pg_to_json.py` — 从 PostgreSQL 导回 JSON 文件格式。覆盖 sessions + messages + parts。

### 11.3 Blob 初始备份

对现有容器做一次全量同步到 Azure Blob。

### 11.4 最终清理

- 确认 `storage/storage.py` 已删除
- 确认无代码引用旧 storage 模块
- 更新 `.env.example`
- 更新 `pyproject.toml` 中 packages 列表（移除 storage，新增 db, cache, blob, auth）

**验收标准**：
- [ ] 迁移脚本跑通，数据完整
- [ ] 回滚脚本可用
- [ ] 全量测试通过

---

## 关键测试场景（贯穿所有 Phase）

| 场景 | 验证内容 | Phase |
|------|---------|-------|
| 用户隔离 | A 创建 session → B GET → 404 | 3 |
| 容器隔离 | A 的容器 → B DELETE/WS/preview → 404 | 3 |
| WS 隔离 | A/B 各连 WS → A 发消息 → 只 A 收到 | 5+7 |
| 权限持久化 | approve → 重启 → 权限在 | 4 |
| Token 刷新 | access 过期 → 自动 refresh → 无感恢复 | 3 |
| Token 黑名单 | 登出 → 旧 token → 401 | 3 |
| Ticket 一次性 | 使用一次 → 再用 → 失败 | 3 |
| 暴力破解 | 5 次错误 → 锁定 | 3 |
| Permission 跨 Worker | Worker A ask → 用户 WS 回复到 Worker B → Redis → A 继续 | 7 |
| Question 跨 Worker | 同上 | 7 |
| 并发容器创建 | 两请求同时 → 只创建一个 | 7 |
| 配额限制 | 超限 → 429 | 10 |
| 成本限制 | 月费超限 → agent 拒绝 | 10 |
| 软删除 | 删 session → DB 仍在 (is_deleted=true) | 4 |
| 数据迁移 | 旧 JSON → PG 完整 | 11 |
| 优雅关停 | 关停时等待活跃 loop → 超时标记 ERROR | 8 |

---

## 执行顺序与工作量

```
Phase 1  [M ~5天] 抽象层 + 依赖 + 开发环境 + 测试基础
    │
Phase 2  [M ~3天] 数据库表 + Alembic 迁移
    │
Phase 3  [L ~8天] 认证 + 安全加固 + 前端登录
    │
Phase 4  [L ~8天] Repository + 直接替换 storage + 删除 storage.py
    │
Phase 5  [L ~6天] Agent loop user_id 注入 + 28处事件标准化
    │
    ├──→ Phase 6  [M ~5天] 全局单例隔离 ─────────────────┐
    ├──→ Phase 7  [M ~5天] Redis 缓存 + 跨 Worker 通信 ──┤  (可并行)
    └──→ Phase 8  [L ~8天] main.py + 前端全面改造 ────────┘
              │
              ├──→ Phase 9  [L ~6天] Blob 同步 ────────┐
              ├──→ Phase 10 [S ~3天] 配额 + 成本控制 ──┤  (可并行)
              └──→ Phase 11 [M ~5天] 迁移 + 清理 ──────┘

总计: 约 62 人天
```

---

## 不需要改造的模块（已验证安全）

| 模块 | 原因 |
|------|------|
| `snapshot/snapshot.py` | 无全局状态，纯函数式，通过 session_id 天然隔离 |
| `session/compaction.py` | 无全局状态，纯过滤函数 |
| `agent/llm.py` | 无全局状态，纯 LLM 调用封装 |
| `core/identifier.py` | ULID 生成，无状态 |
| `core/wildcard.py` | 模式匹配，无状态 |
| `core/markdown.py` | Markdown 解析，无状态 |

---

## 文件变更清单

### 新建（11 个目录/文件组）

| 文件/目录 | 说明 |
|-----------|------|
| `backend/db/` | base.py + 11 个 ORM model + 7 个 repository + migrations/ |
| `backend/cache/` | interfaces.py + redis_cache.py + memory_cache.py |
| `backend/blob/` | interfaces.py + azure_blob.py + local_blob.py + sync.py |
| `backend/auth/` | jwt.py + middleware.py + ticket.py + routes.py + password.py |
| `backend/api/ws.py` | 主 WebSocket 端点 + WSConnectionManager（替代 SSE） |
| `backend/scripts/migrate_json_to_pg.py` | 迁移脚本 |
| `backend/scripts/migrate_pg_to_json.py` | 回滚脚本 |
| `docker-compose.dev.yml` | 开发环境 |
| `backend/tests/` | 测试套件 |
| `frontend/src/pages/LoginPage.tsx` | 登录页 |
| `frontend/src/stores/auth.ts` | Auth store |
| `frontend/src/services/ws.ts` | 主 WebSocket 客户端（替代 sse.ts） |
| `frontend/src/hooks/useWS.ts` | WS 事件订阅 hook（替代 useSSE.ts） |
| `frontend/src/types/ws.ts` | WS 事件类型定义（替代 types/sse.ts） |
| `backend/.env.example` | 环境变量示例 |

### 修改（45 个文件）

**基础设施 (5)**：config.py, main.py, pyproject.toml, docker-compose.yml, Makefile

**Agent 核心 (6)**：loop.py, hooks.py, compaction.py, retry.py, tool/tool.py, question/question.py

**数据层 (7)**：session/session.py, session/todo.py, session/revert.py, permission/permission.py, sandbox/docker.py, sandbox/manager.py, storage/storage.py (删除)

**全局单例 (11)**：skill/skill.py, command/command.py, mcp/client.py, project/instance.py, project/project.py, tool/mcp_tool.py, tool/registry.py, tool/truncation.py, tool/task.py, session/instruction.py, agent/agent.py

**API 路由 (8)**：sessions.py, containers.py, metadata.py, permissions.py, files.py, terminal.py, questions.py, events.py (删除)

**事件系统 (2)**：bus/bus.py, bus/events.py

**前端 — 删除 (3)**：services/sse.ts, hooks/useSSE.ts, types/sse.ts

**前端 — 修改 (6)**：api.ts, stores/ui.ts, App.tsx, CreateContainerDialog.tsx, SandboxRequiredDialog.tsx, hooks/useWebSocket.ts (终端 WS + ticket)

**总计：59 个文件**（新建 14 + 修改 41 + 删除 4）

---

## 环境变量

### 生产

```bash
DATABASE_URL=postgresql+asyncpg://root:73SdesGJ9Z61CA8H0ajh4MyTRkzK5U2w@107.175.44.162:31938/openbox
REDIS_URL=redis://redis:6379/0
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=adsblob;AccountKey=RRx7QTZ9/MzsfVpu13qvL2ScKHngVynI1AM22bcGJ6ow0SzCQvaMl9sMQDR+8Hlvu2bSwE+dbmFL+AStrg60Kg==;EndpointSuffix=core.windows.net
BLOB_AZURE_CONTAINER=ads-staging
JWT_SECRET=<openssl rand -hex 32>
```

### 开发

```bash
DATABASE_URL=postgresql+asyncpg://openbox:openbox_dev@localhost:5432/openbox
REDIS_URL=redis://localhost:6379/0
BLOB_PROVIDER=local
BLOB_LOCAL_PATH=/opt/openbox/blobs
JWT_SECRET=dev-secret-do-not-use-in-production
```
