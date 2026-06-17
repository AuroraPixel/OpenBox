# OpenBox 性能优化计划

## Context

用户反馈聊天体验存在三阶段卡顿：发消息延迟显示、流式渲染不及时、LLM 结束后仍在转圈。
同时存在前端包体过大、后端高频轮询/广播等系统级性能问题。
经过两轮独立代码审查，确认根因并制定以下 12 项修复。

本补丁只做性能修复，不改业务语义。

---

## 优先级总览

| 优先级 | Fix | 描述 | 阶段 |
|--------|-----|------|------|
| **P0** | Fix 1 | 用户消息乐观渲染 | 发送阶段 |
| **P0** | Fix 2 | MessageBubble/TextPart/ToolPart 加 React.memo | 流式阶段 |
| **P0** | Fix 3 | 修复 updateToolStatus 无差别浅拷贝 | 流式阶段 |
| **P0** | Fix 4 | TextPart 流式期间延迟 markdown 解析 | 流式阶段 |
| **P1** | Fix 5 | useAutoScroll 优化 | 流式阶段 |
| **P1** | Fix 6 | 后端 IDLE 前移 | 结束阶段 |
| **P1** | Fix 7 | Vite manualChunks 拆包 | 首屏加载 |
| **P2** | Fix 8 | WebSocket 广播路由修复 | 后端安全+性能 |
| **P2** | Fix 9 | 容器列表轮询降频 | 后端负载 |
| **P2** | Fix 10 | diff 接口缓存 snapshot | 后端负载 |
| **P2** | Fix 11 | 消息列表虚拟化 | 长会话性能 |
| **P1** | Fix 12 | WebSocket 关键事件可靠投递 | 结束阶段稳定性 |

---

## Fix 1: 用户消息乐观渲染（消除发送延迟感）

**问题**: InputBar → HTTP POST → 后端 DB 写入 → WS 推送 → 前端才显示，延迟 100-300ms。

**方案**: 在 `handleSend` 里立即往 store 插入临时消息，使用 `client_message_id` 精确对齐后端 `message.created` 回推后替换（不使用按文本/role 猜测匹配）。

**修改文件**:
- `frontend/src/components/chat/ChatView.tsx` — `handleSend` 中调用 `addMessage` 插入临时用户消息
- `frontend/src/stores/session.ts` — `addMessage` 逻辑改为按 `client_message_id` 替换临时消息
- `backend/api/sessions.py` — `prompt_async` 接收并透传 `client_message_id`
- `backend/session/session.py` — `create_user_message` 发布 `message.created` 时回带 `client_message_id`

**实现细节**:
1. `ChatView.handleSend` 在调用 `api.sendMessageAsync` 之前：
   - 生成临时 ID: `tmp-${Date.now()}`
   - 调用 `addMessage(sessionId, { id: tmpId, role: "user", parts: [{ type: "text", text, id: "tmp-part" }], ... })`
2. `sendMessageAsync` body 增加 `client_message_id`
3. 后端在创建 `user` 消息时保存/透传 `client_message_id`
4. `session.ts` 新增逻辑：`addMessage` 收到正式消息后，按 `client_message_id` 精确替换对应 `tmp-` 消息

---

## Fix 2: MessageBubble / TextPart / ToolPart 加 React.memo（消除无关消息重渲染）

**问题**: 每个流式 delta 触发整个消息列表所有组件 re-render，无 memo 保护。

**方案**: 对核心渲染组件加 `React.memo`。

**修改文件**:
- `frontend/src/components/chat/MessageBubble.tsx` — 用 `React.memo` 包裹导出
- `frontend/src/components/parts/TextPart.tsx` — 用 `React.memo` 包裹导出
- `frontend/src/components/parts/ToolPart.tsx` — 用 `React.memo` 包裹导出

**实现细节**:
每个文件的导出改为：
```
export const XxxComponent = React.memo(function XxxComponent(...) { ... })
```

注意：`MessageBubble` 的 props 包含 `message` 对象，需要 store 层保证未变消息引用不变（见 Fix 3）。

---

## Fix 3: 修复 updateToolStatus 无差别浅拷贝（store 层 bug）

**问题**: `session.ts:142-153` 的 `updateToolStatus` 对所有消息都做 `{ ...m, parts: m.parts.map(...) }`，即使该消息不包含目标 partId，引用也被破坏，导致 React.memo 失效。

**修改文件**:
- `frontend/src/stores/session.ts` — `updateToolStatus` 方法

**实现细节**:
```typescript
// 当前代码（bug）:
list.map((m) => ({
  ...m,
  parts: m.parts.map((p) => { ... })
}))

// 修复后:
list.map((m) => {
  const hasTarget = m.parts.some((p) => p.id === partId && p.type === "tool")
  if (!hasTarget) return m  // 保持引用不变
  return {
    ...m,
    parts: m.parts.map((p) => {
      if (p.id !== partId || p.type !== "tool") return p
      return { ...p, status, ...data }
    }),
  }
})
```

---

## Fix 4: TextPart 流式期间延迟 markdown 解析（消除 CPU 热点）

**问题**: `TextPart.tsx` 每次 render 都完整执行 ReactMarkdown + rehype-highlight，流式输出时每秒触发几十次，每次重新解析全部已接收文本。

**方案**:
- 用 `useDeferredValue` 延迟 markdown 渲染（React 19）
- 流式阶段先渲染纯文本（`pre`/plain text），在消息结束后再切换到 `ReactMarkdown + rehype-highlight`

**修改文件**:
- `frontend/src/components/parts/TextPart.tsx`

**实现细节**:
```typescript
import { useDeferredValue, memo } from "react"

export const TextPart = memo(function TextPart({ text }: TextPartProps) {
  const deferredText = useDeferredValue(text)
  return (
    <div className="markdown-body text-sm leading-relaxed">
      <ReactMarkdown ...>{deferredText}</ReactMarkdown>
    </div>
  )
})
```

补充：
- 将 `remarkPlugins` 和 `rehypePlugins` 数组提取为模块级常量，避免每次 render 创建新数组引用
- 流式阶段禁用高亮解析，结束后一次性解析

---

## Fix 5: useAutoScroll 优化（减少 observer 重建）

**问题**: `useEffect` 依赖 `isAtBottom` state，每次滚动状态变化都断开重连 MutationObserver。

**修改文件**:
- `frontend/src/hooks/useAutoScroll.ts`

**实现细节**:
- 将 `isAtBottom` 改为 `useRef` 供 MutationObserver 回调读取，同时保留 `useState` 用于驱动 UI
- `checkAtBottom` 同时更新 ref 和 state
- `useEffect` 依赖列表移除 `isAtBottom`，只在 mount 时创建一次 observer
- 去掉 `characterData: true`，`childList + subtree` 已足够捕获 DOM 变化

---

## Fix 6: 后端 IDLE 前移（消除"结束后仍在转圈"）

**问题**: `loop.py:740-764` 在 cleanup pending tools + prune_tool_outputs 完成后才发 IDLE，这两步可能耗时 0.5-2s；同时存在 todo nudge 逻辑导致 finish 后继续运行的体感。

**修改文件**:
- `backend/agent/loop.py` — run_loop 函数的收尾部分（约 740-764 行）

**实现细节**:
```python
# 当前顺序:
# 1. cleanup pending tools (全量扫描 + 逐条 DB update)
# 2. prune_tool_outputs (全量扫描 + 批量 DB update)
# 3. set_session_status(IDLE)  <-- 用户等这一步

# 修改为:
# 1. set_session_status(IDLE)  <-- 先让前端停转圈
# 2. cleanup + prune 放入 asyncio.create_task (fire-and-forget)
```

补充：
- 增加可观测收尾事件（如 `session.finalizing`）或内部 metric，避免 UI 误判
- 为 todo nudge（`pending todo` 自动 Continue）增加配置开关，便于生产排障与灰度

---

## Fix 7: Vite manualChunks 拆包（首屏加载优化）

**问题**: `vite.config.ts` 无任何 code splitting 配置，所有依赖打进单一 chunk（~1MB / gzip 300KB），Vite 已报 chunk 过大警告。xterm、react-markdown、rehype-highlight、react-diff-viewer、framer-motion 等重库全部在首屏加载。

**修改文件**:
- `frontend/vite.config.ts` — 添加 `build.rollupOptions.output.manualChunks`
- `frontend/src/App.tsx` — 重模块改 `React.lazy` 懒加载

**实现细节**:
```typescript
// vite.config.ts — manualChunks 配置
manualChunks: {
  'vendor-xterm': ['@xterm/xterm', '@xterm/addon-fit', '@xterm/addon-web-links'],
  'vendor-markdown': ['react-markdown', 'remark-gfm', 'rehype-highlight'],
  'vendor-diff': ['react-diff-viewer-continued'],
  'vendor-motion': ['framer-motion'],
}

// App.tsx — 非首屏页面懒加载
const DiffView = React.lazy(() => import("@/components/diff/DiffView"))
const PreviewPanel = React.lazy(() => import("@/components/preview/PreviewPanel"))
const SettingsPage = React.lazy(() => import("@/pages/SettingsPage"))
const SandboxPage = React.lazy(() => import("@/pages/SandboxPage"))
// renderMain 中用 <Suspense fallback={<Loading />}> 包裹
```

---

## Fix 8: WebSocket 广播路由修复（安全 + 性能）

**问题**: `ws.py:111-120` 的 `_on_bus_event` 在 `userId` 缺失或未匹配时，直接 `broadcast()` 给所有连接用户。这既是信息泄露风险（用户收到别人的 session 事件），也是多用户场景下的性能问题。

**修改文件**:
- `backend/api/ws.py` — `_on_bus_event` 函数

**实现细节**:
```python
async def _on_bus_event(event: dict):
    data = event.get("data", {})
    user_id = data.get("userId")

    if user_id:
        await ws_manager.send_to_user(user_id, event)
    else:
        # 无 userId 的事件：只允许白名单类型广播
        event_type = event.get("type", "")
        BROADCAST_WHITELIST = {"build.progress", "build.complete", "build.error", "server.announcement"}
        if event_type in BROADCAST_WHITELIST:
            await ws_manager.broadcast(event)
        else:
            log.warning(f"Dropping event without userId: {event_type}")
```

---

## Fix 9: 容器列表轮询降频（后端负载优化）

**问题**: `App.tsx:104` 每 5 秒轮询 `GET /api/containers`，后端 `docker.py:321-343` 对每个内存中容器串行调用 `docker.containers.get()` 同步 API。在多容器/多用户场景下浪费资源。

**修改文件**:
- `frontend/src/App.tsx` — `refetchInterval` 从 5000 调整为 30000
- `frontend/src/hooks/useWS.ts` — 新增 `container.status` 事件监听，触发 react-query invalidate
- `backend/sandbox/docker.py` — 在 `create_container`/`delete_container`/`stop_container`/`start_container` 中补充 `bus.publish("container.status", { "userId": user_id })` （若尚未有）

---

## Fix 10: diff 接口缓存 snapshot（长会话优化）

**问题**: `sessions.py:408-439` 的 `GET /session/{id}/diff` 每次都全量查询消息并遍历所有 parts 寻找 first_snapshot / last_snapshot，会话越长越慢。

**修改文件**:
- `backend/api/sessions.py` — `get_diff` 函数

**实现细节**:
改为只查询 `step-start` 和 `step-finish` 类型的 parts（通过 `PartORM.type.in_(...)` 过滤），避免加载所有消息和所有 parts。

补充：
- 修复当前实现隐患：`get_diff` 调用 `get_messages(session_id)` 默认只拉 200 条，长会话可能漏 snapshot 边界
- 验证口径必须包含“200+ 消息会话下 diff 正确性”，不只看耗时

---

## Fix 11: 消息列表虚拟化（长会话性能）

**问题**: `MessageList.tsx` 用 `messages.map()` 渲染所有消息，长会话时 DOM 节点过多，滚动卡顿且内存占用高。

**修改文件**:
- `frontend/src/components/chat/MessageList.tsx` — 引入 `@tanstack/react-virtual`
- `frontend/package.json` — 添加 `@tanstack/react-virtual` 依赖

**实现细节**:
使用 `useVirtualizer` 替代直接 `map`，配置 `estimateSize`、`overscan`、`measureElement` 实现动态高度虚拟列表。需同步调整 `useAutoScroll`，`scrollToBottom` 改用 `virtualizer.scrollToIndex`。

---

## Fix 12: WebSocket 关键事件可靠投递（避免卡在 busy）

**问题**: WS 发送队列满时直接丢事件。若关键事件（`session.status=idle`、`session.error`、`message.created`）丢失，会出现“明明结束了但前端还在 busy”。

**修改文件**:
- `backend/api/ws.py` — `WSConnectionManager.send_to_user`

**实现细节**:
- 引入关键事件白名单：`session.status`、`session.error`、`message.created`
- 当队列满时：
  - 普通增量事件（如 delta）可丢弃
  - 关键事件必须保留（可采用覆盖旧状态、有限重试或优先队列）
- 记录 dropped/retained 指标，便于线上定位

---

## 修改文件清单

| 文件 | Fix | 改动量 |
|------|-----|--------|
| `frontend/src/components/chat/ChatView.tsx` | Fix 1 | ~15 行 |
| `frontend/src/stores/session.ts` | Fix 1, Fix 3 | ~20 行 |
| `frontend/src/components/chat/MessageBubble.tsx` | Fix 2 | ~3 行 |
| `frontend/src/components/parts/TextPart.tsx` | Fix 2, Fix 4 | ~10 行 |
| `frontend/src/components/parts/ToolPart.tsx` | Fix 2 | ~3 行 |
| `frontend/src/hooks/useAutoScroll.ts` | Fix 5 | ~10 行 |
| `backend/agent/loop.py` | Fix 6 | ~15 行 |
| `frontend/vite.config.ts` | Fix 7 | ~15 行 |
| `frontend/src/App.tsx` | Fix 7, Fix 9 | ~23 行 |
| `frontend/src/hooks/useWS.ts` | Fix 9 | ~5 行 |
| `backend/sandbox/docker.py` | Fix 9 | ~8 行 |
| `backend/api/sessions.py` | Fix 10 | ~20 行 |
| `frontend/src/components/chat/MessageList.tsx` | Fix 11 | ~40 行 |
| `backend/session/session.py` | Fix 1 | ~10 行 |
| `backend/api/ws.py` | Fix 8, Fix 12 | ~25 行 |
| `frontend/package.json` | Fix 11 | ~1 行 |

共 16 个文件，约 260 行变更。

---

## 验证方案

1. **Fix 1**: 发送消息后，用户消息应立即出现（不等 WS 回推）；并验证连续发送相似文本不会错配（基于 `client_message_id`）
2. **Fix 2/3/4**: React DevTools Profiler 中，流式输出时只有当前消息组件 re-render
3. **Fix 4**: 流式输出长代码块时，浏览器 CPU 占用明显下降；消息结束后再切 markdown/高亮
4. **Fix 5**: 快速滚动聊天区域不出现 observer 重建
5. **Fix 6**: LLM 最后 token 后 <200ms 切换为 idle；todo nudge 开关开启/关闭两种模式均验证
6. **Fix 7**: `npm run build` 后检查 chunk 分布，主 chunk 应 <500KB
7. **Fix 8**: 多用户连接时，用户只收到自己 session 的事件
8. **Fix 9**: Network tab 确认容器轮询间隔为 30s，容器状态变化时立即刷新
9. **Fix 10**: 长会话（>200 条消息）下 diff 接口响应时间 <200ms，且 first/last snapshot 选择正确
10. **Fix 11**: 200+ 条消息的会话中滚动流畅，DOM 节点数稳定
11. **Fix 12**: 人为压测 WS 队列（模拟高频 delta）时，不出现“会话停留 busy”的状态丢失
12. **回归**: 聊天完整流程 — 发送、流式、工具调用、abort、compaction、revert 均正常

---

## 数据库表设计复核（新增）

### 需要重点修复的表

| 表名 | 当前热点查询/写入 | 风险 | 修复动作 |
|------|-------------------|------|----------|
| `messages` | `session_id + created_at` 拉取消息；按 `user_id` 统计月成本；写入用户消息 | 大用户下按时间范围统计/排序可能走回表 | 新增 `client_message_id` 字段；新增索引 `ix_messages_user_created(user_id, created_at)` |
| `parts` | `session_id + type + created_at`（diff）；`message_id + created_at`（消息 parts） | 长会话下 `parts` 扫描和排序成本增长 | 新增索引 `ix_parts_session_type_created(session_id, type, created_at)`、`ix_parts_message_created(message_id, created_at)` |
| `sessions` | `user_id + status + is_deleted`（并发 busy 会话计数） | 高频 `count_busy` 查询可能退化 | 新增索引 `ix_sessions_user_status_active(user_id, status, is_deleted)` |

### 本轮新增迁移

- `backend/db/migrations/versions/b7c2f9f8d1a1_perf_indexes_and_client_message_id.py`
  - `messages` 表新增 `client_message_id`
  - 新增 4 个高频路径索引（`messages`/`parts`/`sessions`）

---

## 执行顺序（一步一步）

1. 先合入 P0（Fix 1-4），保证聊天体感先恢复：发消息即时显示、流式不卡
2. 再合入 P1（Fix 5-7 + Fix 6 补充项），优化结束态与首屏加载
3. 合入 P2（Fix 8-12），处理多用户路由、队列可靠性和长会话性能
4. 执行数据库迁移（新增索引与字段），并在预发压测验证慢查询改善
5. 按“验证方案”做回归，重点盯 `busy->idle` 时延、200+ 消息会话滚动与 diff 耗时
