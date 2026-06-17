---
read_when:
  - 理解 cron 定时任务如何触发 LLM 调用
  - 调试 cron job 执行或 delivery 问题
  - 修改或扩展 cron 调度器的内部实现
summary: Cron 定时任务触发 LLM 的内部架构与完整调用链分析
title: Cron 触发 LLM 架构分析
---

# Cron 触发 LLM 架构分析

本文档从源码层面分析 openclaw 的 cron 定时任务系统如何触发 LLM 调用，覆盖调度器机制、两条执行路径、模型选择、Prompt 构建、结果交付的完整链路。

> 面向用户的使用文档请参阅 [定时任务](/automation/cron-jobs) 和 [定时任务与心跳对比](/automation/cron-vs-heartbeat)。

## 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                          创建入口                                 │
│  UI/API (cron.add)  ─  Agent (cron-tool)  ─  CLI (openclaw cron) │
└──────────┬───────────────────┬───────────────────┬───────────────┘
           │                   │                   │
           ▼                   ▼                   ▼
     normalizeCronJobCreate → validateCronAddParams → CronService.add
                                                        │
                                                        ▼
                                             createJob + persist(jobs.json)
                                                        │
                                                        ▼
                                                   armTimer(setTimeout)
                                                        │
                                               ┌────────┴────────┐
                                               ▼                 ▼
                                         onTimer 到点      runMissedJobs(启动补跑)
                                               │
                                        collectRunnableJobs
                                               │
                                        ┌──────┴──────┐
                                        ▼              ▼
                                  sessionTarget    sessionTarget
                                    = "main"        = "isolated"
                                   ┌─────┴────┐   ┌─────┴─────┐
                                   │ 路径 A    │   │ 路径 B     │
                                   │ 间接触发  │   │ 直接触发   │
                                   │ LLM      │   │ LLM       │
                                   └──────────┘   └───────────┘
```

cron 对 LLM 的触发有且仅有**两条路径**，通过 `assertSupportedJobSpec` 做强约束：

- `sessionTarget: "main"` **必须**配合 `payload.kind: "systemEvent"`
- `sessionTarget: "isolated"` **必须**配合 `payload.kind: "agentTurn"`

## 核心文件索引

| 文件 | 职责 |
|------|------|
| `src/cron/service.ts` | `CronService` 类，对外 API |
| `src/cron/service/ops.ts` | `start`/`add`/`update`/`run` 等操作 |
| `src/cron/service/timer.ts` | `armTimer`/`onTimer`/`executeJobCore`，调度与执行核心 |
| `src/cron/service/jobs.ts` | `createJob`/`computeJobNextRunAtMs`/`isJobDue`，Job 管理 |
| `src/cron/service/state.ts` | `CronServiceState`/`CronServiceDeps` 类型定义 |
| `src/cron/types.ts` | `CronJob`/`CronPayload`/`CronSchedule` 等类型 |
| `src/gateway/server-cron.ts` | `buildGatewayCronService`，依赖注入绑定 |
| `src/cron/isolated-agent/run.ts` | `runCronIsolatedAgentTurn`，isolated 路径主逻辑 |
| `src/cron/isolated-agent/delivery-dispatch.ts` | 结果交付分发 |
| `src/infra/heartbeat-runner.ts` | Heartbeat runner，main 路径的 LLM 触发点 |
| `src/infra/system-events.ts` | `enqueueSystemEvent`，内存事件队列 |
| `src/infra/heartbeat-wake.ts` | `requestHeartbeatNow`，heartbeat 唤醒调度 |
| `src/agents/pi-embedded-runner/run/attempt.ts` | `runEmbeddedAttempt`，实际 LLM HTTP 调用 |
| `src/agents/cli-runner.ts` | `runCliAgent`，CLI provider 执行 |
| `src/agents/tools/cron-tool.ts` | Agent 自创建 cron job 的工具 |

---

## 一、调度器机制

### 1.1 定时器设置 (`armTimer`)

`armTimer` 用 `setTimeout` 设置下次唤醒，延迟计算流程：

1. `nextWakeAtMs(state)` — 所有 enabled job 中最早的 `nextRunAtMs`
2. `delay = max(nextAt - now, 0)`
3. 若 `delay === 0`，用 `MIN_REFIRE_GAP_MS`（2 秒）兜底，防止 `setTimeout(0)` 死循环
4. 上限钳位 `MAX_TIMER_DELAY_MS`（60 秒），确保至少每分钟醒一次

| 常量 | 值 | 作用 |
|------|------|------|
| `MAX_TIMER_DELAY_MS` | 60,000 ms | 定时器最长间隔，减少调度漂移 |
| `MIN_REFIRE_GAP_MS` | 2,000 ms | 同一 job 两次触发最小间隔，防自旋 |

### 1.2 定时器触发 (`onTimer`)

```
onTimer()
  ├─ if (state.running) → armRunningRecheckTimer(60s) → return
  ├─ state.running = true
  ├─ armRunningRecheckTimer  // 看门狗
  ├─ locked:
  │   ├─ ensureLoaded(forceReload)
  │   ├─ collectRunnableJobs(nowMs)
  │   ├─ due.length === 0 → recomputeNextRunsForMaintenance → persist → return []
  │   └─ due.length > 0 → 每个 job.state.runningAtMs = now → persist → return jobs
  ├─ 并发池 (maxConcurrentRuns, 默认 1):
  │   └─ runDueJob → executeJobCoreWithTimeout → executeJobCore
  ├─ locked: applyOutcomeToStoredJob → recomputeNextRunsForMaintenance → persist
  └─ finally: sweepCronRunSessions → state.running = false → armTimer
```

并发控制使用共享 `cursor` 的 worker 池，并发数由 `cronConfig.maxConcurrentRuns` 决定（默认 1）。

### 1.3 Job 到期判断 (`isRunnableJob`)

一个 job 满足以下全部条件才可执行：

| 条件 | 说明 |
|------|------|
| `job.enabled === true` | 必须启用 |
| `runningAtMs` 为空 | 不能正在执行 |
| `nowMs >= nextRunAtMs` | 时间已到 |
| 不在 error backoff 窗口 | 错误退避（30s → 1min → 5min → 15min → 60min） |

启动时的 `runMissedJobs` 还会检查 `previousRunAtMs > lastRunAtMs` 来补跑重启期间错过的 cron slot。

### 1.4 Schedule 类型

```typescript
type CronSchedule =
  | { kind: "at"; at: string }                    // 一次性，ISO 时间
  | { kind: "every"; everyMs: number }             // 固定间隔
  | { kind: "cron"; expr: string; tz?: string }    // cron 表达式
```

---

## 二、路径 A — `main + systemEvent`（间接触发 LLM）

### 2.1 执行流程

```
executeJobCore (sessionTarget = "main")
  │
  ├─ 1. resolveJobPayloadTextForMain(job)
  │      提取 systemEvent.text，若为空 → status: "skipped"
  │
  ├─ 2. enqueueSystemEvent(text, { sessionKey, contextKey })
  │      存入进程内 Map<sessionKey, SessionQueue>
  │      数据结构: { text, ts, contextKey }，每 session 最多 20 条
  │
  └─ 3. 按 wakeMode 分支:
         │
         ├─ "now":
         │    runHeartbeatOnce({ reason, heartbeat: { target: "last" } })
         │    ├─ 若 "requests-in-flight" → 重试 (250ms 间隔，最多 2 分钟)
         │    ├─ 超时 → 改为 requestHeartbeatNow
         │    └─ 返回 ok / skipped / error
         │
         └─ "next-heartbeat":
              requestHeartbeatNow({ reason })
              → pendingWakes 队列 → schedule(coalesceMs)
              → 到期后触发 HeartbeatWakeHandler
```

### 2.2 Heartbeat → Agent → LLM 调用链

```
HeartbeatWakeHandler
  → runHeartbeatOnce
       ├─ resolveHeartbeatPreflight
       │    ├─ cron 触发会 bypassFileGates（跳过 HEARTBEAT.md 检查）
       │    └─ peekSystemEventEntries → 检测 cron: 前缀事件
       │
       ├─ resolveHeartbeatRunPrompt
       │    └─ 有 cron events → buildCronEventPrompt(cronEvents)
       │
       └─ getReplyFromConfig
            → runPreparedReply
                 ├─ drainFormattedSystemEvents  // 消费 system events
                 └─ runReplyAgent
                      → runAgentTurnWithFallback
                           → runEmbeddedPiAgent / runCliAgent
                                → session.prompt()
                                     → streamFn → HTTP/WebSocket → LLM API
```

### 2.3 wakeMode 对比

| 维度 | `"now"` | `"next-heartbeat"` |
|------|---------|--------------------|
| 是否同步 | 是，阻塞等待 heartbeat 完成 | 否，立即返回 |
| 延迟 | 即刻（最多重试 2 分钟） | 等下次 heartbeat 周期 |
| Main lane 忙 | 循环重试 250ms | 不关心 |
| 典型场景 | 需要立即反馈的定时提醒 | 不紧急的通知 |

---

## 三、路径 B — `isolated + agentTurn`（直接触发 LLM）

### 3.1 执行流程

```
executeJobCore (sessionTarget = "isolated", payload.kind = "agentTurn")
  │
  ├─ state.deps.runIsolatedAgentJob({ job, message, abortSignal })
  │    绑定自 server-cron.ts → runCronIsolatedAgentTurn
  │
  └─ runCronIsolatedAgentTurn:
       │
       ├─ 阶段 1: Agent 配置 & 模型解析
       │   ├─ agentId: params.agentId → job.agentId → defaultAgentId
       │   ├─ 合并 agent config
       │   └─ 模型优先级链（见 3.2）
       │
       ├─ 阶段 2: Session 管理
       │   └─ resolveCronSession({ forceNew: true })
       │        isolated 每次强制新建 session，不继承历史
       │
       ├─ 阶段 3: Prompt 构建
       │   ├─ 普通: "[cron:{id} {name}] {message}\n{timeLine}"
       │   ├─ External hook: buildSafeExternalPrompt 安全包装
       │   └─ delivery 时追加交付说明
       │
       ├─ 阶段 4: Auth Profile & Skills Snapshot
       │
       ├─ 阶段 5: 执行 Agent
       │   └─ runWithModelFallback({
       │        run: (provider, model) => {
       │          isCliProvider → runCliAgent
       │          else          → runEmbeddedPiAgent
       │        }
       │      })
       │
       └─ 阶段 6: 结果处理 & Delivery
            ├─ 更新 session (tokens, model)
            ├─ 提取 outputText / summary / deliveryPayload
            └─ dispatchCronDelivery
```

### 3.2 模型选择优先级链

从高到低：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | `payload.model` | Job 级别指定的模型覆盖 |
| 2 | `hooks.gmail.model` | Gmail hook 专用模型 |
| 3 | `session.modelOverride` | 会话级模型覆盖（/model 命令） |
| 4 | `subagents.model` | Agent 配置的 subagent 模型 |
| 5 | `agents.defaults.model` | 全局默认模型 |

若 `payload.model` 指定的模型不在 allowlist 中，会回退到 agent 默认模型并打 warning。

### 3.3 Prompt 构建

**普通 Prompt：**

```
[cron:{jobId} {jobName}] {message}
Current time: 2026-03-05 10:00 UTC
```

**External Hook 安全包装：**

当 session key 标识为 external hook（如 `hook:gmail:*`）且未设置 `allowUnsafeExternalContent` 时，使用 `buildSafeExternalPrompt` 包装：

1. `detectSuspiciousPatterns` 检测注入类模式并打安全日志
2. `replaceMarkers` 将伪造 boundary 替换为 `[[MARKER_SANITIZED]]`
3. 用唯一 ID 的 XML 风格 marker 包裹：`<<<EXTERNAL_UNTRUSTED_CONTENT id="...">>`
4. 在内容前加入安全警告，要求模型不把内容当指令执行

**Delivery 追加：**

若请求了 delivery，追加提示：

```
Return your summary as plain text; it will be delivered automatically.
```

### 3.4 两种 Provider

| 维度 | Embedded Provider（默认） | CLI Provider |
|------|--------------------------|--------------|
| 实现 | `runEmbeddedPiAgent` | `runCliAgent` |
| 执行方式 | 进程内，`streamFn` 发 HTTP/WebSocket | 子进程执行 `claude` / `codex` CLI |
| 工具支持 | 完整工具集 | 禁用 |
| LLM 调用 | `session.prompt()` → `streamFn` → `fetch` | CLI 命令行参数 |
| 适用 | anthropic / openai / google / ollama | claude-cli / codex-cli / 自定义 cliBackends |

**Embedded Provider 的实际 LLM 调用点：**

```
runEmbeddedPiAgent
  → runEmbeddedAttempt (attempt.ts)
       → 配置 streamFn:
            ollama → createOllamaStreamFn → fetch(`{baseUrl}/api/chat`)
            openai-responses → createOpenAIWebSocketStreamFn
            其他 → streamSimple (pi-ai 包内部 HTTP)
       → activeSession.prompt(effectivePrompt)
            → agent 循环中调用 streamFn(model, context, options)
            → 实际 HTTP/WebSocket 请求
```

### 3.5 Delivery 分发逻辑

```
dispatchCronDelivery
  ├─ 跳过条件:
  │   ├─ mode = "none" 或 !requested
  │   ├─ heartbeat-only 响应（不发 HEARTBEAT_OK）
  │   └─ agent 已通过 messaging tool 发到目标
  │
  ├─ 有结构化内容 (media/channelData) 或 threadId
  │   → deliverViaDirect → deliverOutboundPayloads
  │      → Telegram / Slack / Feishu / WhatsApp ...
  │
  └─ 纯文本
       → deliverViaAnnounce → runSubagentAnnounceFlow
            → 注入主会话或 channel
            → 失败且 !bestEffort → 回退 deliverViaDirect
```

Delivery 三种模式：

| 模式 | 行为 | 配置 |
|------|------|------|
| `announce` | 通过消息通道发送到聊天 | `delivery.channel` + `delivery.to` |
| `webhook` | HTTP POST 到 URL | `delivery.to`（URL）+ `webhookToken` |
| `none` | 不发送，结果仅保留在 session | 默认 |

---

## 四、Job 创建与配置

### 4.1 创建流程

```
UI/API/Agent 调用 cron.add
  → normalizeCronJobCreate(params)
       ├─ unwrapJob：支持 data/job 包装
       ├─ coerceSchedule：统一 at/every/cron
       ├─ coercePayload：推断 kind
       ├─ coerceDelivery：规范化 mode
       └─ applyDefaults：wakeMode:"now", enabled:true, ...
  → validateCronAddParams + validateScheduleTimestamp
  → CronService.add
       → locked → createJob → push → recomputeNextRuns → persist → armTimer
```

### 4.2 两种 Payload 类型

**`systemEvent`** — 轻量，注入文本到主会话：

```typescript
{ kind: "systemEvent", text: string }
```

**`agentTurn`** — 完整 agent 执行：

```typescript
{
  kind: "agentTurn",
  message: string,          // 发给 agent 的 prompt
  model?: string,           // 模型覆盖
  fallbacks?: string[],     // 备用模型
  thinking?: string,        // 思考模式
  timeoutSeconds?: number,  // 超时
  lightContext?: boolean,   // 轻量 bootstrap
  allowUnsafeExternalContent?: boolean,
  deliver?: boolean,        // 旧版 delivery 开关
  channel?: string,         // 旧版 delivery channel
  to?: string,              // 旧版 delivery 目标
  bestEffortDeliver?: boolean,
}
```

### 4.3 Agent 自创建 Cron Job

Agent 可通过 `cron` 工具创建定时任务（`src/agents/tools/cron-tool.ts`）：

1. `action: "add"` + `job` 对象
2. 兼容 flat-params（非 frontier 模型可能打平参数）
3. 自动注入 `agentId` / `sessionKey`（从当前会话推断）
4. 对 `agentTurn` 且无 delivery 目标时，从 `sessionKey` 推断 delivery（如 `telegram:direct:123`）
5. 对 `systemEvent`，可选附加 `contextMessages` 作为上下文
6. 最终调用 `callGateway("cron.add", job)` 走标准流程

---

## 五、依赖注入

`buildGatewayCronService`（`src/gateway/server-cron.ts`）为 CronService 注入关键依赖：

| 依赖 | 绑定目标 | 用途 |
|------|----------|------|
| `enqueueSystemEvent` | `infra/system-events.ts` | main 路径入队系统事件 |
| `requestHeartbeatNow` | `infra/heartbeat-wake.ts` | 请求下次 heartbeat 唤醒 |
| `runHeartbeatOnce` | `infra/heartbeat-runner.ts` | 立即执行一次 heartbeat（main + wakeMode=now） |
| `runIsolatedAgentJob` | `cron/isolated-agent/run.ts` → `runCronIsolatedAgentTurn` | 执行 isolated agent turn |
| `sendCronFailureAlert` | delivery 通道或 webhook | 失败告警通知 |
| `onEvent` | `broadcast("cron", evt)` | 生命周期事件广播到 UI |

---

## 六、错误处理与容错

### 6.1 错误退避

连续错误时使用指数退避，防止重试风暴：

| 连续错误次数 | 退避延迟 |
|-------------|---------|
| 1 | 30 秒 |
| 2 | 1 分钟 |
| 3 | 5 分钟 |
| 4 | 15 分钟 |
| 5+ | 60 分钟 |

### 6.2 One-shot Job 重试

`schedule.kind === "at"` 的一次性任务在 transient 错误时自动重试：

- 匹配模式：rate_limit / network / timeout / 5xx
- 最大重试：`cronConfig.retry.maxAttempts`（默认 3）
- 永久错误或重试耗尽 → 禁用 job

### 6.3 Schedule 计算错误

`computeJobNextRunAtMs` 抛异常时，`recordScheduleComputeError` 记录：

- 连续 3 次失败 → 自动禁用 job
- 发送 system event 通知用户

### 6.4 Failure Alert

连续失败达到阈值后发送告警（可配置）：

- `failureAlert.after`：连续错误几次后告警（默认 2）
- `failureAlert.cooldownMs`：告警冷却时间（默认 1 小时）
- 支持 `announce`（通过消息通道）或 `webhook`（HTTP POST）

### 6.5 Job Timeout

- isolated job：`payload.timeoutSeconds` → `resolveAgentTimeoutMs`
- 通过 `AbortController` + `Promise.race` 实现超时中断

---

## 七、配置项参考

```yaml
cron:
  enabled: true                        # 是否启用 cron 调度器
  store: "~/.openclaw/cron"            # 持久化存储路径
  maxConcurrentRuns: 1                 # 并发执行 job 数
  retry:
    maxAttempts: 3                     # one-shot transient 重试次数
    backoffMs: [30000, 60000, 300000]  # 重试退避时间
    retryOn:                           # 可重试的错误类型
      - rate_limit
      - network
      - timeout
      - server_error
  runLog:
    maxBytes: 2000000                  # 运行日志最大字节
    keepLines: 2000                    # 运行日志保留行数
  sessionRetention: "24h"              # cron 运行 session 保留时长
  failureAlert:
    enabled: true                      # 是否启用失败告警
    after: 2                           # 连续失败几次后告警
    cooldownMs: 3600000                # 告警冷却（毫秒）
    mode: "announce"                   # announce 或 webhook
  failureDestination:
    channel: "telegram"                # 失败通知通道
    to: "-1001234567890"               # 失败通知目标
    mode: "announce"                   # announce 或 webhook
  webhook: "https://..."               # 旧版全局 webhook（已废弃）
  webhookToken: "..."                  # webhook 认证 token
```
