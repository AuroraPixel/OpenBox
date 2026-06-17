# OpenBox Cron 定时任务系统 — 完整实施计划

## 概述

在 OpenBox 中实现 session 级别的 cron 定时任务系统，让 AI Agent 能够按计划自动执行任务。参考 OpenClaw 的调度器设计，但针对 OpenBox 多用户 + Docker sandbox 架构做了适配。

### 核心设计原则

1. **Session 级别隔离** — 每个 cron job 属于一个 session，一个 session 可以有多个 cron job
2. **独立执行 + 轻量注入** — cron 在临时 session 执行（summary + task prompt），仅将任务描述和最终结果注入主 session
3. **Container 智能预热** — 根据 job 调度频率决定容器保活或按需预热
4. **自建 Timer** — 翻译 OpenClaw 的调度器核心逻辑（Python asyncio 实现）
5. **Delivery 扩展预留** — 设计 delivery 抽象层，当前仅实现 WebSocket 推送，预留 Webhook/渠道扩展

---

## 一、数据模型

### 1.1 cron_jobs 表

```sql
CREATE TABLE cron_jobs (
    id              VARCHAR(64) PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL REFERENCES users(id),
    session_id      VARCHAR(64) NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,

    -- 基本信息
    name            VARCHAR(256) NOT NULL,
    description     TEXT DEFAULT '',
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,

    -- 调度配置
    schedule_kind   VARCHAR(16) NOT NULL,  -- 'at' | 'every' | 'cron'
    schedule_expr   VARCHAR(256) NOT NULL, -- ISO 时间 | 毫秒数 | cron 表达式
    schedule_tz     VARCHAR(64) DEFAULT 'UTC',

    -- 任务配置
    task_prompt     TEXT NOT NULL,          -- 发给 agent 的 prompt
    agent           VARCHAR(64) DEFAULT 'build',
    model           VARCHAR(128),           -- NULL = 跟随 session 的 model
    timeout_seconds INTEGER DEFAULT 1800,   -- 默认 30 分钟

    -- Delivery 配置（预留扩展）
    delivery_mode   VARCHAR(16) DEFAULT 'none',  -- 'none' | 'webhook' | 'channel'
    delivery_config JSONB DEFAULT '{}',           -- webhook_url, channel, to 等

    -- 调度状态（Timer 读写）
    next_run_at     TIMESTAMPTZ,
    last_run_at     TIMESTAMPTZ,
    running_at      TIMESTAMPTZ,            -- 非 NULL 表示正在执行
    last_status     VARCHAR(16),            -- 'ok' | 'error' | 'skipped'
    consecutive_errors INTEGER DEFAULT 0,

    -- 元数据
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_deleted      BOOLEAN DEFAULT FALSE,

    -- 性能索引
    -- CREATE INDEX idx_cron_jobs_timer ON cron_jobs(enabled, next_run_at) WHERE NOT is_deleted AND enabled = TRUE;
    -- CREATE INDEX idx_cron_jobs_user ON cron_jobs(user_id) WHERE NOT is_deleted;
    -- CREATE INDEX idx_cron_jobs_session ON cron_jobs(session_id) WHERE NOT is_deleted;
);
```

### 1.2 cron_runs 表

```sql
CREATE TABLE cron_runs (
    id              VARCHAR(64) PRIMARY KEY,
    job_id          VARCHAR(64) NOT NULL REFERENCES cron_jobs(id) ON DELETE CASCADE,
    user_id         VARCHAR(64) NOT NULL,
    session_id      VARCHAR(64) NOT NULL,       -- 主 session
    temp_session_id VARCHAR(64),                 -- 临时执行 session

    -- 执行状态
    status          VARCHAR(16) NOT NULL,        -- 'running' | 'ok' | 'error' | 'skipped'
    error_message   TEXT,

    -- 内容
    task_prompt     TEXT,                         -- 执行时的 prompt 快照
    summary_text    TEXT,                         -- Agent 的最终结果
    context_summary TEXT,                         -- 执行前的 session summary 快照

    -- 注入状态
    injected        BOOLEAN DEFAULT FALSE,        -- 是否已注入主 session
    injected_at     TIMESTAMPTZ,

    -- 统计
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    duration_ms     INTEGER DEFAULT 0,

    -- 时间
    started_at      TIMESTAMPTZ NOT NULL,
    ended_at        TIMESTAMPTZ,

    -- 性能索引
    -- CREATE INDEX idx_cron_runs_pending ON cron_runs(session_id, injected) WHERE status = 'ok' AND injected = FALSE;
    -- CREATE INDEX idx_cron_runs_job ON cron_runs(job_id, started_at DESC);
    -- CREATE INDEX idx_cron_runs_cleanup ON cron_runs(started_at) WHERE temp_session_id IS NOT NULL;
);
```

### 1.3 索引策略

Timer 每 60 秒查询一次到期 job，核心查询：

```sql
SELECT * FROM cron_jobs
WHERE enabled = TRUE AND NOT is_deleted
  AND next_run_at <= NOW()
  AND running_at IS NULL
ORDER BY next_run_at ASC;
```

组合索引 `idx_cron_jobs_timer(enabled, next_run_at)` + WHERE 过滤确保 O(log N) 查询。

---

## 二、调度器核心

### 2.1 文件结构

```
backend/cron/
├── __init__.py
├── types.py            # CronSchedule, CronPayload, CronJobState 类型定义
├── service.py          # CronService 类（对外 API：start/stop/add/update/remove/run）
├── timer.py            # arm_timer/on_timer/collect_runnable_jobs/apply_job_result
├── schedule.py         # compute_next_run_at（用 croniter 库）
├── executor.py         # 执行引擎：summary → 临时 session → run_loop → 提取结果
├── injector.py         # 结果注入：overflow 检查 → compact → 注入消息
├── warmup.py           # Container 预热调度器
├── recovery.py         # 启动恢复：清理 stuck jobs，补跑 missed jobs
├── reaper.py           # 临时 session 清理
└── delivery.py         # Delivery 抽象层（预留扩展）
```

### 2.2 Timer 循环（翻译自 OpenClaw timer.ts）

```
arm_timer():
  1. 查询最近的 next_run_at（所有 enabled job）
  2. delay = clamp(next_at - now, MIN_REFIRE_GAP=2s, MAX_TIMER_DELAY=60s)
  3. asyncio.get_event_loop().call_later(delay, on_timer)

on_timer():
  1. if running → 启动 watchdog（60s 后重检）→ return
  2. running = True
  3. 获取 Redis 分布式锁（多 Worker 安全）
  4. collect_runnable_jobs():
     - enabled=True, running_at IS NULL, next_run_at <= now
     - 排除 error backoff 窗口内的 job
  5. 标记 running_at = now（DB 持久化，释放锁前）
  6. 并发执行（max_concurrent_jobs，默认 2）
  7. apply_job_result():
     - 成功 → consecutive_errors=0, 计算 next_run_at
     - 失败 → consecutive_errors++, 指数退避
     - 一次性 job 成功 → enabled=False
  8. running = False → arm_timer()
```

### 2.3 指数退避（和 OpenClaw 一致）

| 连续错误次数 | 退避延迟 |
|-------------|---------|
| 1 | 30 秒 |
| 2 | 1 分钟 |
| 3 | 5 分钟 |
| 4 | 15 分钟 |
| 5+ | 60 分钟 |

### 2.4 瞬态错误重试（仅一次性 `at` job）

匹配模式：`rate_limit`、`network`、`timeout`、`5xx`
最大重试：3 次
永久错误或重试耗尽 → 禁用 job

### 2.5 分布式锁（多 Worker）

```python
# 使用 Redis SETNX
lock_key = "cron:timer:lock"
acquired = await redis.set(lock_key, worker_id, nx=True, ex=120)
if not acquired:
    return  # 另一个 worker 在处理
try:
    await _execute_due_jobs()
finally:
    await redis.delete(lock_key)
```

---

## 三、执行引擎

### 3.1 完整执行流程

```
Cron 触发（on_timer 收集到 due job）
  │
  ├─ 1. 生成 session summary
  │     ├─ 检查缓存：cron_jobs.summary_cache_message_id == session 最新消息 ID？
  │     │   ├─ 命中 → 复用缓存 summary
  │     │   └─ 未命中 → LLM summary（小模型，低成本）
  │     │              → 更新缓存
  │     ├─ 如果 session 最近有 compaction → 直接复用 compaction 摘要
  │     └─ summary 失败 → 降级：空 summary，仅 system prompt + task
  │
  ├─ 2. 创建临时 session
  │     ├─ create_session(user_id, agent, model, parent_id=main_session_id)
  │     ├─ 标记为 cron temp session
  │     └─ 获取 sandbox client（可能触发容器创建）
  │
  ├─ 3. 构建 prompt
  │     ├─ system prompt（标准 agent prompt）
  │     ├─ context: "[Session Summary]\n{summary}"
  │     └─ user message: "[Cron: {job_name}] {task_prompt}\nCurrent time: {now}"
  │
  ├─ 4. 执行 run_loop（临时 session）
  │     ├─ 完整 agent 能力（工具、技能）
  │     ├─ 自动 compaction（如果执行过程上下文快超）
  │     ├─ 超时控制：asyncio.wait_for + abort signal
  │     └─ ToolContext.origin_session_id = main_session_id
  │
  ├─ 5. 提取结果
  │     ├─ 从临时 session 提取最后一条 assistant text
  │     └─ 写入 cron_runs（status, summary_text, tokens, duration）
  │
  └─ 6. 结果注入（见第四节）
```

### 3.2 ToolContext 扩展

```python
class ToolContext:
    session_id: str              # 临时 session（执行环境）
    origin_session_id: str | None  # 主 session（cron 归属，cron tool 用）
    user_id: str
    sandbox: SandboxClient | None
```

cron tool 创建新任务时用 `origin_session_id`：

```python
async def execute_cron_tool(args, ctx):
    target_session = ctx.origin_session_id or ctx.session_id
    await cron_service.add(session_id=target_session, ...)
```

---

## 四、结果注入

### 4.1 注入时机

```
Cron 执行完毕 → 写入 cron_runs(injected=False)

注入触发点：
  ├─ 主 session IDLE → 直接注入
  └─ 主 session BUSY → 等待
       → run_loop finally 块：
            await flush_pending_cron_results(session_id, user_id)
            await set_session_status(IDLE)
```

### 4.2 注入流程（injector.py）

```
flush_pending_cron_results(session_id, user_id):
  1. 查询 cron_runs WHERE session_id AND status='ok' AND injected=False
     ORDER BY started_at ASC
  2. 对每条结果：
     a. 检查注入后 session 上下文是否会超：
        current_context + estimate(task + result) > context_limit * 0.9 ?
        ├─ 会超 → 先 compact 主 session → 再注入
        └─ 不超 → 直接注入
     b. create_user_message(
          session_id, synthetic=True,
          text="[Cron: {job_name}] {task_prompt}"
        )
     c. create_assistant_message(
          session_id, text=summary_text,
          agent="cron", model=job.model
        )
     d. UPDATE cron_runs SET injected=True, injected_at=now
  3. 推送前端（bus 事件）
```

### 4.3 BUSY 期间的竞态安全

```
run_loop 结束时的执行顺序（不可重排）：
  1. agent loop break（不再读写消息）
  2. flush_pending_cron_results()  ← session 还是 BUSY，prompt_async 进不来
  3. set_session_status(IDLE)       ← 此时才允许新请求

用户恰好在 flush 时发消息：
  → prompt_async 检查 status=BUSY → 等待/abort
  → flush 完成 → set IDLE
  → prompt_async 继续 → 新 run_loop 看到 cron 注入的结果 + 用户消息
```

### 4.4 失败处理

- 执行失败的 cron_runs **不注入** 主 session（不污染对话）
- cron_runs 表记录 status='error' + error_message
- 前端 session detail 面板展示失败记录
- 用户下次对话时，系统可在 instruction 中提示 "你有 N 个定时任务执行失败"

---

## 五、Container 预热

### 5.1 预热策略

```
WarmupScheduler（独立于 Timer，定期扫描）：
  1. 查询所有 enabled job，按 user_id 分组
  2. 对每个 user：
     a. 找最近的 next_run_at
     b. 如果 next_run_at - now < WARMUP_LEAD_TIME（默认 5 分钟）：
        → 检查该 user 是否有 running container
        → 没有 → sandbox_manager.get_client(user_id=...) 触发容器创建
     c. 如果 user 的最小 job 间隔 < WARMUP_LEAD_TIME：
        → 标记 container 为 "cron-keepalive"
        → 不参与 30 分钟 idle 销毁

扫描频率：每 60 秒一次（挂在 timer tick 上）
```

### 5.2 避免重复预热

```
per-user warmup state:
  warmup_requested_at: timestamp
  container_ready: bool

规则：
  - 如果 warmup_requested_at < 60s 前 → 跳过（刚预热过）
  - 如果 container_ready=True → 跳过（已经在运行）
  - 如果另一个 cron job 正在执行（running_at 有值）→ 跳过（容器肯定在）
```

### 5.3 Keepalive 判断

```python
def should_keepalive(user_id: str) -> bool:
    """如果用户的 cron job 频率高于预热时间，保持容器常驻"""
    jobs = get_enabled_jobs(user_id)
    if not jobs:
        return False
    min_interval = min(compute_job_interval(job) for job in jobs)
    return min_interval < WARMUP_LEAD_TIME_MS
```

容器标记 keepalive 后，不参与 WS 断开 30 分钟的自动销毁。

---

## 六、启动恢复

### 6.1 recovery.py

```python
async def recover_on_startup():
    """服务重启时的恢复流程"""

    # 1. 清理 stuck running markers
    stuck_jobs = await db.query(
        "UPDATE cron_jobs SET running_at = NULL "
        "WHERE running_at IS NOT NULL RETURNING id"
    )
    interrupted_job_ids = {row.id for row in stuck_jobs}

    # 2. 标记中断的 cron_runs
    await db.execute(
        "UPDATE cron_runs SET status = 'error', "
        "error_message = 'Server restarted during execution' "
        "WHERE status = 'running'"
    )

    # 3. 补跑 missed jobs（排除被中断的）
    missed = await collect_missed_jobs(skip_ids=interrupted_job_ids)
    for job in missed:
        # 每个 missed job 只补跑一次（不累积）
        await execute_job(job)

    # 4. 重新计算所有 job 的 next_run_at
    await recompute_all_next_runs()

    # 5. 启动 timer
    arm_timer()
```

### 6.2 Missed job 检测

```python
async def collect_missed_jobs(skip_ids: set[str]) -> list[CronJob]:
    """检测启动期间错过的 job"""
    now = datetime.utcnow()
    jobs = await db.query(
        "SELECT * FROM cron_jobs "
        "WHERE enabled = TRUE AND NOT is_deleted "
        "AND next_run_at < %s "
        "AND (last_run_at IS NULL OR last_run_at < next_run_at) "
        "AND id NOT IN %s",
        now, tuple(skip_ids)
    )
    return jobs
    # 每个 missed job 只补跑一次，然后 recompute next_run_at
```

---

## 七、临时 Session 清理

### 7.1 reaper.py

```python
REAPER_INTERVAL_SECONDS = 300   # 每 5 分钟检查一次
RETENTION_HOURS = 24            # 保留 24 小时

async def sweep_temp_sessions():
    """清理过期的 cron 临时 session"""
    cutoff = datetime.utcnow() - timedelta(hours=RETENTION_HOURS)

    # 查找已完成的 cron_runs 的临时 session
    expired = await db.query(
        "SELECT DISTINCT temp_session_id FROM cron_runs "
        "WHERE temp_session_id IS NOT NULL "
        "AND status != 'running' "
        "AND started_at < %s",
        cutoff
    )

    for row in expired:
        await delete_session(row.temp_session_id)  # 级联删除 messages + parts

    # 清理 cron_runs 表中的旧记录（可选，保留 30 天）
    await db.execute(
        "DELETE FROM cron_runs WHERE started_at < %s",
        datetime.utcnow() - timedelta(days=30)
    )
```

挂在 timer tick 的 finally 块上（和 OpenClaw 一致），自限流每 5 分钟最多执行一次。

---

## 八、API 端点

### 8.1 路由

```
GET    /api/cron/jobs                    全局 job 列表（Settings 页用）
GET    /api/cron/jobs?session_id=xxx     Session 级 job 列表（Detail 面板用）
POST   /api/cron/jobs                    创建 job
PATCH  /api/cron/jobs/{id}               更新 job
DELETE /api/cron/jobs/{id}               删除 job
POST   /api/cron/jobs/{id}/run           手动触发
GET    /api/cron/jobs/{id}/runs          执行历史
GET    /api/cron/status                  调度器状态
```

所有端点都带 `Depends(get_current_user)` 认证，按 user_id 过滤。

### 8.2 注册

```python
# main.py
from api.cron import router as cron_router
application.include_router(cron_router)
```

### 8.3 Cron 工具（Agent 对话创建）

```python
# tool/cron_tool.py
cron_tool = define_tool(
    "cron",
    description="""Create, list, or manage cron jobs for the current session.

Actions:
  - add: Create a new scheduled task
  - list: Show existing cron jobs for this session
  - update: Modify a cron job
  - remove: Delete a cron job

The job will execute automatically at the scheduled time.
Results will appear in this conversation.""",
    parameters=CronToolArgs,
    execute=execute_cron_tool,
)
```

工具只能操作 `ctx.origin_session_id or ctx.session_id` 的 job。

---

## 九、前端 UI

### 9.1 Session Detail 面板（侧边栏）

在 RightPanel 的 DETAILS tab 下新增 "Scheduled Tasks" 区域：

```
┌─ DETAILS ──────────────────────┐
│  ...existing content...         │
│                                 │
│  ▸ Scheduled Tasks (2)          │
│  ┌─────────────────────────────┐│
│  │ 📅 日报生成                  ││
│  │   Every day at 9:00          ││
│  │   Last: ok · 2h ago          ││
│  │   Next: tomorrow 9:00        ││
│  ├─────────────────────────────┤│
│  │ 📅 监控检查                  ││
│  │   Every 30 minutes           ││
│  │   Last: ok · 12m ago         ││
│  │   Next: in 18 minutes        ││
│  └─────────────────────────────┘│
│  [+ Add Task]                   │
└─────────────────────────────────┘
```

### 9.2 Settings → Cron tab

全局管理所有 cron job：

```
┌─ Settings / Cron ──────────────────────────────────────────────┐
│                                                                 │
│  Scheduled Tasks                              [+ New Task]      │
│  3 tasks · Scheduler: running                                   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 📅 日报生成                     Session: 千问分析   [Edit]   ││
│  │   0 9 * * * (Asia/Shanghai)    Status: ok          [Toggle] ││
│  │   Last: 2h ago · 1.2K tokens   Next: tomorrow 9:00 [Run]   ││
│  ├─────────────────────────────────────────────────────────────┤│
│  │ 📅 监控检查                     Session: DevOps     [Edit]   ││
│  │   */30 * * * *                 Status: ok          [Toggle] ││
│  │   Last: 12m ago · 800 tokens   Next: in 18m        [Run]   ││
│  ├─────────────────────────────────────────────────────────────┤│
│  │ 📅 周末提醒                     Session: Personal   [Edit]   ││
│  │   at: 2026-03-08 10:00         Status: pending     [Toggle] ││
│  │   Last: never                  Next: Mar 8 10:00   [Run]   ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│  [Execution History]                                            │
└─────────────────────────────────────────────────────────────────┘
```

### 9.3 Session 删除时的提示

```
ConfirmDialog:
  title: "Delete Session"
  message: "This session has 3 scheduled tasks that will also be deleted:
            · 日报生成 (every day at 9:00)
            · 监控检查 (every 30 minutes)
            · 周末提醒 (at Mar 8 10:00)
            Are you sure?"
  variant: "danger"
```

### 9.4 Bus 事件

```python
# bus/events.py
CRON_JOB_STARTED = "cron.job.started"
CRON_JOB_COMPLETED = "cron.job.completed"
CRON_JOB_FAILED = "cron.job.failed"
CRON_JOB_INJECTED = "cron.job.injected"    # 结果已注入 session
```

前端 useWS 订阅这些事件，实时更新 Detail 面板和 Settings 页。

---

## 十、Delivery 扩展预留

### 10.1 抽象层

```python
# cron/delivery.py

class DeliveryTarget(BaseModel):
    mode: Literal["none", "webhook", "channel"]  # 当前只实现 none
    config: dict = {}  # webhook_url, channel_id, etc.

class DeliveryResult(BaseModel):
    success: bool
    error: str | None = None

async def dispatch_delivery(
    target: DeliveryTarget,
    job: CronJob,
    result: CronRunResult,
) -> DeliveryResult:
    """分发 cron 结果到外部渠道"""
    if target.mode == "none":
        return DeliveryResult(success=True)
    elif target.mode == "webhook":
        return await _deliver_webhook(target.config, job, result)
    elif target.mode == "channel":
        # 预留：飞书、钉钉、Telegram 等
        return await _deliver_channel(target.config, job, result)
    return DeliveryResult(success=False, error=f"Unknown mode: {target.mode}")
```

### 10.2 Webhook 实现（Phase 4）

```python
async def _deliver_webhook(config: dict, job: CronJob, result: CronRunResult) -> DeliveryResult:
    url = config["webhook_url"]
    token = config.get("token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    payload = {
        "job_id": job.id,
        "job_name": job.name,
        "status": result.status,
        "summary": result.summary_text,
        "duration_ms": result.duration_ms,
        "timestamp": result.ended_at.isoformat(),
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)
        return DeliveryResult(success=resp.is_success)
```

---

## 十一、Lifespan 集成

### 11.1 main.py 启动

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing init ...

    # 初始化 Cron 调度器
    from cron.service import cron_service
    from cron.recovery import recover_on_startup

    await recover_on_startup()  # 清理 stuck + 补跑 missed
    await cron_service.start()  # 启动 timer

    yield

    # 关闭
    await cron_service.stop()
    # ... existing cleanup ...
```

### 11.2 Agent 工具注册

```python
# tool/registry.py — 注册 cron tool
from tool.cron_tool import cron_tool
register_tool(cron_tool)
```

---

## 十二、实施阶段

### Phase 1: 调度器核心（~800 行）

```
新增文件：
  backend/cron/__init__.py
  backend/cron/types.py
  backend/cron/service.py
  backend/cron/timer.py
  backend/cron/schedule.py
  backend/cron/recovery.py
  backend/db/models/cron.py  (ORM 模型)

修改文件：
  backend/main.py            (lifespan 集成)
  backend/bus/events.py      (新增 CRON_* 事件)

依赖：
  pip install croniter       (cron 表达式解析)
```

### Phase 2: 执行引擎 + 结果注入（~600 行）

```
新增文件：
  backend/cron/executor.py
  backend/cron/injector.py
  backend/cron/reaper.py

修改文件：
  backend/agent/loop.py      (finally 块加 flush hook)
  backend/models/message.py  (ToolContext 加 origin_session_id)
```

### Phase 3: API + 前端（~800 行）

```
新增文件：
  backend/api/cron.py
  backend/tool/cron_tool.py
  frontend/src/components/cron/CronJobList.tsx
  frontend/src/components/cron/CronJobForm.tsx
  frontend/src/components/cron/CronRunHistory.tsx

修改文件：
  frontend/src/pages/SettingsPage.tsx   (新增 Cron tab)
  frontend/src/components/layout/RightPanel.tsx (Detail 面板)
  frontend/src/services/api.ts          (cron API 方法)
  frontend/src/hooks/useWS.ts           (cron 事件订阅)
```

### Phase 4: Delivery + 预热（~400 行）

```
新增文件：
  backend/cron/delivery.py
  backend/cron/warmup.py

修改文件：
  backend/sandbox/manager.py  (keepalive 标记)
  backend/api/ws.py           (不销毁 keepalive 容器)
```

### 总计

| Phase | 新增代码 | 修改代码 | 复杂度 |
|-------|---------|---------|--------|
| Phase 1 | ~700 行 | ~100 行 | 高 |
| Phase 2 | ~500 行 | ~100 行 | 高 |
| Phase 3 | ~600 行 | ~200 行 | 中 |
| Phase 4 | ~300 行 | ~100 行 | 中 |
| **合计** | **~2100 行** | **~500 行** | |

---

## 十三、关键安全机制（对齐 OpenClaw）

| 机制 | 实现 | 来源 |
|------|------|------|
| 卡死检测 | running_at > 2 小时自动清除 | OpenClaw STUCK_RUN_MS |
| 最小间隔 | 同一 job 两次执行 >= 2 秒 | OpenClaw MIN_REFIRE_GAP_MS |
| Timer 钳位 | 最大 60 秒间隔 | OpenClaw MAX_TIMER_DELAY_MS |
| 指数退避 | 30s → 1m → 5m → 15m → 60m | OpenClaw DEFAULT_BACKOFF_SCHEDULE |
| 瞬态重试 | at job 最多 3 次 | OpenClaw DEFAULT_MAX_TRANSIENT_RETRIES |
| Watchdog | 执行期间每 60 秒重检 timer | OpenClaw armRunningRecheckTimer |
| 并发控制 | 可配置 max_concurrent_jobs | OpenClaw maxConcurrentRuns |
| 分布式锁 | Redis SETNX | OpenBox 特有（多 Worker） |
| Missed 补跑 | 启动时检测并补跑一次 | OpenClaw runMissedJobs |
| 进程内互斥 | asyncio.Lock per operation | OpenClaw locked() |

---

## 十四、补充：遗漏的边界场景

### 14.1 Summary 缓存与 Compaction 摘要复用

cron 执行前需要 session summary，但不是每次都要调 LLM：

```
cron_jobs 表新增字段：
  summary_cache       TEXT,           -- 缓存的 summary 内容
  summary_cache_msg_id VARCHAR(64),   -- 基于哪条消息生成的

执行前判断：
  1. session 最新消息 ID == summary_cache_msg_id？
     → 命中 → 直接用缓存（零开销）
  2. session 最近有 compaction？
     → 有 → 取 compaction 摘要作为 summary（零开销）
  3. 都不满足 → LLM summary（小模型） → 更新缓存
```

### 14.2 cron_jobs 表缺少的字段

```sql
-- Summary 缓存
summary_cache       TEXT,
summary_cache_msg_id VARCHAR(64),

-- 一次性 job 控制
delete_after_run    BOOLEAN DEFAULT FALSE,   -- 成功后自动删除（at 类型默认 True）

-- 重试配置（一次性 job）
max_retries         INTEGER DEFAULT 3,

-- 执行统计
total_runs          INTEGER DEFAULT 0,
total_successes     INTEGER DEFAULT 0,
total_failures      INTEGER DEFAULT 0,
last_error          TEXT,
last_duration_ms    INTEGER,
```

### 14.3 用户不在线时的 cron 失败通知

用户不在线时 bus 事件丢失。需要持久化通知：

```sql
-- 复用已有 kv_store 表或新增通知表
-- 用户上线后，前端查询未读 cron 通知

GET /api/cron/notifications?unread=true

返回：
[
  { "job_id": "xxx", "job_name": "日报", "status": "error",
    "error": "LLM timeout", "at": "2026-03-05T09:00:00Z", "read": false }
]
```

前端 WS 重连时（`__connected` handler）查询未读通知并显示 Toast。

### 14.4 Cron job 执行期间用户删除 session

```
场景：
  t0: Cron job 正在执行（临时 session + sandbox）
  t1: 用户删除主 session → CASCADE 删除 cron_jobs
  t2: Cron 执行完毕 → 尝试写入 cron_runs → job_id 外键失败

防护：
  1. 删除 session 前检查是否有 running cron job
     → 有 → 先 abort cron 执行 → 等待结束 → 再删除
     → 或：允许删除，但 cron executor 在写入时 catch 外键异常并静默放弃
  2. 推荐方案：catch + 静默放弃（更简单，cron 结果对已删除 session 无意义）
```

### 14.5 多个 cron 竞争同一容器资源

```
场景：用户有 3 个 cron job 同时到期，都需要 sandbox

问题：
  - sandbox_manager.get_client() 对同一 user 返回同一容器
  - 3 个临时 session 的 run_loop 同时在一个容器里执行
  - 容器资源（CPU/内存）可能不够

防护：
  1. per-user 并发限制：max_concurrent_cron_per_user = 2
     → 第 3 个 job 排队等前面的完成
  2. 容器资源配置：cron keepalive 容器可以配更大的资源限制
  3. 执行超时：防止一个 job 长期占用容器
```

### 14.6 cron_runs 表分区/归档策略

```
高频 cron job 会快速积累 runs 记录：
  - 每 30 分钟一次 = 每天 48 条
  - 10 个 job = 每天 480 条
  - 一年 = 175,200 条

策略：
  1. 活跃数据：最近 30 天（idx_cron_runs_job 索引）
  2. reaper 定期清理：DELETE WHERE started_at < 30 days ago
  3. 可选：归档到 cron_runs_archive 表（保留统计用）
  4. 前端分页查询：GET /api/cron/jobs/{id}/runs?page=1&limit=20
```

### 14.7 Cron job 的暂停/恢复 vs 禁用

```
enabled=False 是永久禁用。还需要"暂停"概念吗？

场景：用户出差一周，想暂停所有 cron job，回来后恢复

方案：
  - 不新增字段，复用 enabled
  - 前端提供 "Pause All" / "Resume All" 按钮
  - 暂停 = 批量 UPDATE enabled=False
  - 恢复 = 批量 UPDATE enabled=True + recompute next_run_at
```

### 14.8 时区处理

```
cron 表达式带时区：schedule_tz = "Asia/Shanghai"

关键：
  - DB 存储 next_run_at 为 UTC（TIMESTAMPTZ）
  - croniter 计算时传入 tz
  - 前端显示时转换为用户本地时区
  - DST 变化由 croniter + pytz/zoneinfo 自动处理
```

### 14.9 Cron tool 权限控制

```
Agent 通过 cron tool 创建任务时的安全限制：

  1. 只能操作当前 session（origin_session_id）的 job
  2. 不能创建频率过高的 job（最小间隔 1 分钟）
  3. 不能创建超过 N 个 job（每 session 上限，如 10 个）
  4. 一次性 at job 的时间必须在未来
  5. task_prompt 长度限制（防止注入超长 prompt）
```

### 14.10 Executor 与 run_loop 的关系图

```
正常用户对话：
  prompt_async → create_user_message → run_loop(main_session) → 前端实时流

Cron 执行：
  on_timer → executor:
    1. summary(main_session)           ← 只读主 session 消息
    2. create temp_session
    3. create_user_message(temp_session, prompt)
    4. run_loop(temp_session)          ← 独立执行，前端不可见
    5. extract result
    6. write cron_runs(injected=False)
    7. check main_session status:
       ├─ IDLE → inject + push frontend
       └─ BUSY → 等 run_loop finally flush

run_loop finally（无论正常还是 cron 触发的）：
    → flush_pending_cron_results(session_id)
    → set_session_status(IDLE)
```

### 14.11 监控指标（可观测性）

```
日志：
  - cron.job.scheduled   → job 被调度到
  - cron.job.started     → 开始执行
  - cron.job.completed   → 执行完成 + 耗时 + tokens
  - cron.job.failed      → 执行失败 + 错误
  - cron.job.injected    → 结果已注入
  - cron.timer.tick      → timer 唤醒
  - cron.warmup.started  → 容器预热开始
  - cron.reaper.swept    → 清理了 N 个临时 session

前端 Settings Cron 面板：
  - 调度器状态（running/stopped）
  - 总 job 数 / 启用数 / 运行中数
  - 最近 24h 执行次数 / 成功率
  - 下次最近的执行时间
```

### 14.12 注入消息格式（LLM 可识别）

Agent 在对话中需要能区分用户消息和 cron 注入的结果。注入格式设计：

```
user (synthetic):
  [Scheduled Task: 日报生成 | job_id: xxx | 2026-03-05 09:00 UTC]
  生成今日报告

assistant (agent="cron", model=job.model):
  今日报告内容...
```

- `[Scheduled Task: ...]` 前缀让 LLM 识别这是定时任务输出
- `agent="cron"` 标记让前端显示 CRON 标签（和 BUILD/COMPACTION 一样）
- 用户问 "上次定时任务结果怎么样" 时，LLM 能准确找到并引用

### 14.13 Session 长期不活跃时的 cron job

一个 session 创建了 cron job 后用户再也没来过，消息历史可能非常过时。

```
策略：
  - 不自动禁用（用户可能就是想要后台自动执行）
  - Settings 页标注 "Session inactive for 30+ days" 黄色警告
  - summary 缓存过期无影响（summary 内容虽旧但仍是有效上下文）
  - 如果 session 已被软删除 → cron job 会被级联软删除（见 14.14）
```

### 14.14 软删除级联（关键 Bug 预防）

OpenBox 的 session 删除是**软删除**（`is_deleted=True`），不是 SQL `DELETE`。
因此 `ON DELETE CASCADE` **永远不会触发**。

必须在 session 软删除时手动级联：

```python
async def delete_session(session_id, user_id):
    # 1. 检查是否有正在执行的 cron job
    running = await db.query(
        "SELECT id, name FROM cron_jobs "
        "WHERE session_id = %s AND running_at IS NOT NULL",
        session_id
    )
    # running jobs 的 executor 会在写入时 catch 异常并静默放弃

    # 2. 软删除关联的 cron_jobs
    disabled_count = await db.execute(
        "UPDATE cron_jobs SET enabled = FALSE, is_deleted = TRUE, updated_at = NOW() "
        "WHERE session_id = %s AND user_id = %s AND NOT is_deleted",
        session_id, user_id
    )

    # 3. 再软删除 session（已有逻辑）
    await db.execute(
        "UPDATE sessions SET is_deleted = TRUE, deleted_at = NOW() "
        "WHERE id = %s AND user_id = %s",
        session_id, user_id
    )

    log.info(f"Deleted session {session_id} with {disabled_count} cron job(s)")
```

如果不做这个处理，session 删除后 cron job 会继续执行，
但注入时找不到 session → 静默失败 → 容器持续被唤醒浪费资源。

同步修改 `cron_jobs` 表的外键约束（去掉无效的 CASCADE）：

```sql
session_id VARCHAR(64) NOT NULL REFERENCES sessions(id),  -- 去掉 ON DELETE CASCADE
```
