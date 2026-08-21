# OpenBox Frontend v2 · 工程规范

> **适用范围**：`frontend-v2/` 下全部代码
> **生效日期**：2026-08-20（2026-08-20 依据 bossip 设计稿修订，见附录 D）
> **文档定位**：本文档规定「怎么写」。产品视觉与交互的唯一标准是 **bossip 设计稿**（`design-reference/Agent 聊天.dc.html`、`design-reference/bossip-landing-login.dc.html`、`前端说明与对接文档.md`）。设计稿与本文档冲突时，**以设计稿为准**，并同步修订本文档（本次修订记录在附录 D）。

---

## 0. 规范等级与执行方式

全文条款分三级，每条前有标记：

| 等级 | 含义 | 执行方式 |
|---|---|---|
| **【必须】** | 硬约束 | CI 强制校验，违反则流水线失败，无法合入 |
| **【应当】** | 强建议 | Code Review 必须质询，PR 描述中说明理由方可放行 |
| **【可选】** | 推荐做法 | 不做检查，团队自行判断 |

**例外流程**：任何「必须」级条款的例外，需同时满足三点 —— ① PR 描述写明理由与影响面；② 代码处留 `// SPEC-EXCEPTION: <条款号> <理由>` 注释；③ 在本文档「附录 B · 例外登记」追加一行。未登记的例外视为违规。

---

## 1. 为什么重做：v1 的教训 → v2 的约束

v2 不是推倒重来，而是**保住 v1 已经做对的部分，把工程外围的欠账一次性补上**。下表是 v1 的实测问题与 v2 对应的强制约束，后续每一条规范都可以回溯到这里：

| v1 实测问题 | 数据 | v2 对策 | 条款 |
|---|---|---|---|
| ESLint 配置缺失，`npm run lint` 从未跑通 | 装了 5 个 lint 包，0 个配置文件 | lint 配置纳入仓库并作为 CI 必过项 | §14 |
| 零测试 | 装了 playwright，0 个测试文件 | 三层测试 + 覆盖率门槛 | §13 |
| 依赖装了不用 | 6 个包零引用，产出 2 个 39 字节空 chunk | 依赖准入流程 + 未使用依赖检测 | §2.3 §14 |
| 首屏加载终端模拟器和 Markdown 引擎 | 未登录页也要下 314 KB gzip | 性能预算 + 强制懒加载清单 | §16 |
| Tailwind 4 未用 `@theme` | 1712 处 `hsl(var(--x))` 任意值，散在 76 个文件 | 语义 token 化，禁用颜色任意值 | §9 |
| 服务端状态双源真相 | `useQuery` → `useEffect` → Zustand | 服务端状态单一来源，禁止回灌 | §7 |
| 读写不对称 | 30 个 `useQuery` vs 2 个 `useMutation`，50 处组件内裸调 API | 写操作统一走 mutation 层 | §7 §11 |
| 手写 hash 路由 | 路由逻辑在 `App.tsx` 里写了两遍 | React Router 数据路由 + 路径常量 | §8 |
| 两套 WebSocket 实现并存 | `useWS.ts` / `useWebSocket.ts` 命名无法区分 | 单一 WS 客户端 + 统一事件契约 | §12 |
| 全英文硬编码，无 i18n | 0 个 i18n 库，文案散在 76 个组件 | i18n 为一等公民，硬编码文案 CI 拦截 | §10 |
| 单文件过大、职责混杂 | `App.tsx` 348 行同时管路由/鉴权/数据/布局 | 800 行硬上限 + 组件分层职责 | §5 §6 |

---

## 2. 技术选型

### 2.1 核心栈（已定，不再讨论）

| 领域 | 选型 | 主版本 | 选定理由 |
|---|---|---|---|
| UI 框架 | React | 19.x | 与 v1 一致，迁移成本最低；并发特性对流式渲染有直接收益 |
| 语言 | TypeScript | 5.7+ | `strict` 全开；v1 已验证类型零错误，基线保持 |
| 构建 | Vite | 6.x+ | 与 v1 一致，插件生态与 HMR 表现达标 |
| 样式 | Tailwind CSS | 4.x | 本次**必须**用 v4 的 `@theme` 机制，见 §9 |
| 路由 | React Router | 7.x（library / data 模式） | 数据路由带 loader、错误边界、类型化路径；**不启用 framework 模式**，避免引入 SSR 与文件路由约定 |
| 服务端状态 | TanStack Query | 5.x | 缓存、失效、重试、并发去重，替代 v1 的手写同步 |
| 客户端状态 | Zustand | 5.x | 轻量、无 Provider 嵌套；v1 已验证适配流式增量更新 |
| 国际化 | i18next + react-i18next | i18next 25.x / react-i18next 15.x+ | 命名空间、复数规则、懒加载、TS key 类型推导均原生支持 |
| 图标 | lucide-react | 0.4xx | v1 已在 64 个文件使用，视觉语言延续 |
| 终端 | @xterm/xterm + fit/web-links | 5.x | 无替代品；**必须**懒加载 |
| Markdown | react-markdown + remark-gfm + rehype-highlight | — | **必须**懒加载 |
| 长列表 | @tanstack/react-virtual | 3.x | 消息流与文件树必需 |
| 单元/组件测试 | Vitest + Testing Library | Vitest 3.x | 与 Vite 共用配置；`extension/` 已有 vitest 实践 |
| 端到端测试 | Playwright | 1.5x | v1 已装未用，本次落地 |
| 代码规范 | ESLint 9（flat config）+ typescript-eslint 8 | — | 配置文件**必须**入库 |
| 格式化 | Prettier + prettier-plugin-tailwindcss | — | class 自动排序，消除风格争论 |

> 具体版本号在 `package.json` 中锁定到 minor（`~` 而非 `^`），升级走独立 PR。

### 2.2 明确不引入

| 包 | 不引入的理由 |
|---|---|
| Redux / MobX / Jotai / Recoil | TanStack Query + Zustand 已覆盖两类状态，第三套状态方案只会制造归属歧义 |
| Framer Motion | v1 装了零使用。动画优先用 CSS transition / `@starting-style`；确有复杂编排需求时单独提 RFC |
| Axios | 原生 `fetch` 足够；封装层在 `shared/api` 自建，见 §11 |
| Moment.js / date-fns（默认） | 日期格式化统一走 `Intl`，与 i18n 天然一致（§10.6）。确有复杂日期运算再评估 |
| CSS-in-JS（styled-components / emotion） | 与 Tailwind 双轨会撕裂主题系统 |
| 任何完整 UI 组件库（antd / MUI / Chakra） | 与 §9 的 token 体系和现有视觉语言冲突；原子组件从 v1 移植（§17） |

### 2.3 【必须】新依赖准入流程

新增任何 `dependencies`（`devDependencies` 同样适用于构建链关键包）必须在 PR 描述中回答四问：

1. **不引入能否实现？** 成本多大？
2. **体积代价？** 给出 gzip 后增量（`npx vite-bundle-visualizer` 或构建前后对比）。
3. **进不进首屏？** 若进首屏，必须同时给出仍满足 §16 性能预算的证据。
4. **维护状态？** 最近一次发布时间、周下载量、是否有活跃维护者。

任一问题答不上来 → 不合入。

---

## 3. 工程目录结构

### 3.1 【必须】总体结构

```
frontend-v2/
├── docs/
│   └── ENGINEERING_SPEC.md        # 本文档
├── public/                        # 原样拷贝的静态资源（不参与构建哈希）
├── e2e/                           # Playwright 端到端用例
├── src/
│   ├── app/                       # 应用装配层（全应用仅此一处做「组装」）
│   │   ├── providers/             # Query / i18n / Theme / Toast 等 Provider
│   │   ├── router/                # 路由表、路径常量、路由守卫
│   │   ├── layouts/               # 应用级骨架布局（外壳，不含业务）
│   │   └── bootstrap/             # 入口挂载、全局错误边界、启动时序
│   │
│   ├── routes/                    # 路由页面（薄壳层）
│   │   ├── session/
│   │   ├── sandbox/
│   │   ├── settings/
│   │   └── auth/
│   │
│   ├── features/                  # 业务领域（本项目主体）
│   │   ├── session/
│   │   ├── chat/
│   │   ├── agent-parts/
│   │   ├── permission/
│   │   ├── question/
│   │   ├── project/
│   │   ├── sandbox/
│   │   ├── terminal/
│   │   ├── files/
│   │   ├── diff/
│   │   ├── skill/
│   │   ├── mcp/
│   │   ├── cron/
│   │   ├── preview/
│   │   └── auth/
│   │
│   ├── shared/                    # 跨领域通用能力（无任何业务语义）
│   │   ├── ui/                    # 原子组件（Button / Modal / Toast …）
│   │   ├── hooks/                 # 通用 hooks
│   │   ├── lib/                   # 纯函数工具
│   │   ├── api/                   # HTTP 客户端、拦截器、错误规范
│   │   ├── ws/                    # WebSocket 客户端与事件契约
│   │   ├── i18n/                  # i18n 初始化与工具
│   │   ├── config/                # 环境变量读取与运行时配置
│   │   └── types/                 # 跨领域共享类型
│   │
│   ├── locales/                   # 翻译资源
│   │   ├── en-US/
│   │   └── zh-CN/
│   │
│   └── styles/                    # 全局样式与 Tailwind 主题定义
│
├── eslint.config.js               # 【必须】入库
├── vite.config.ts
├── tsconfig.json
└── package.json
```

### 3.2 【必须】feature 内部标准结构

每个 `features/<name>/` 内部一律按下列结构组织，**目录名固定**，用不到的目录不创建：

```
features/session/
├── api/          # 该领域的接口定义 + useQuery / useMutation 封装
├── components/   # 该领域的展示组件
├── hooks/        # 该领域的逻辑 hooks
├── stores/       # 该领域的客户端状态
├── types/        # 该领域的类型定义
├── utils/        # 该领域的纯函数
├── constants/    # 该领域的常量与枚举
└── index.ts      # 【必须】唯一对外出口
```

### 3.3 【必须】feature 的边界

- 每个 feature **必须**有 `index.ts` 作为唯一对外出口，只导出外部真正需要的东西。
- 外部**禁止**深链引用 feature 内部路径（例如引用 `features/session/components/SessionList` 是违规的，只能从 `features/session` 导入）。
- feature 的划分依据是**业务领域**，不是技术类型。判断标准：如果这块功能整体删掉，删除范围是否收敛在一个目录内？收敛则划分正确。

---

## 4. 分层与依赖方向（解耦的硬约束）

### 4.1 【必须】依赖方向单向

```
app  ──▶  routes  ──▶  features  ──▶  shared
 │                                       ▲
 └───────────────────────────────────────┘
```

四条铁律：

1. **【必须】`shared/` 不得引用 `features/`、`routes/`、`app/` 中的任何内容。** shared 层一旦知道业务，就不再通用，会成为新的耦合中心。
2. **【必须】`features/` 之间禁止横向引用。** feature A 不得 import feature B 的任何内容（含 barrel）。
3. **【必须】`features/` 不得引用 `routes/` 与 `app/`。** 业务层不感知自己被挂在哪个路由下。
4. **【必须】禁止循环依赖**，含模块级与目录级。

### 4.2 跨领域协作的三种合法手段

当两个 feature 确实需要协作时，按成本从低到高选择：

| 手段 | 适用场景 | 做法 |
|---|---|---|
| **在组合层拼装** | A 的数据要喂给 B 的组件 | 在 `routes/` 或 `app/layouts/` 中同时引入 A 和 B，由组合层传递数据。这是**首选手段**，覆盖绝大多数场景 |
| **下沉到 shared** | 双方共用的是无业务语义的能力 | 把公共部分抽到 `shared/`，双方各自依赖 shared |
| **事件解耦** | 领域间只需通知，不需要数据契约 | 通过 `shared/ws` 的事件总线或领域事件，发送方不认识接收方 |

**【必须】** 若以上三种都不适用，说明领域划分本身有问题 —— 应重新划分领域边界，而不是开一个横向 import 的口子。

### 4.3 【必须】机器强制

依赖方向靠自觉守不住，**必须**配置 ESLint 边界规则（`eslint-plugin-boundaries` 或 `import/no-restricted-paths`）+ `import/no-cycle`，把上述四条铁律编码成规则，纳入 CI。人工 Review 只作为补充。

---

## 5. 组件规范

### 5.1 【必须】五类组件的职责边界

| 类型 | 位置 | 职责 | 允许做 | 禁止做 |
|---|---|---|---|---|
| **页面组件** | `routes/` | 路由入口，组装 | 读路由参数、组合容器组件、声明页面级 loader | 写业务逻辑、直接调 API、写样式细节 |
| **容器组件** | `features/*/components/` | 连接数据与展示 | 调用本领域 hooks / query、处理事件、编排展示组件 | 写复杂 JSX 结构、写视觉样式 |
| **展示组件** | `features/*/components/` | 渲染 UI | 接收 props 渲染、内部交互态 | 调 API、读全局 store、发起副作用 |
| **原子组件** | `shared/ui/` | 无业务的基础控件 | 纯 UI、受控/非受控、可访问性 | 出现任何业务词汇（session / sandbox / agent 等） |
| **布局组件** | `app/layouts/` | 页面骨架 | 定义区域槽位、响应式栅格 | 关心槽位里装的是什么业务 |

### 5.2 【必须】组件拆分的触发条件

命中任意一条即**必须**拆分：

- 单文件超过 §6 的警戒线
- 一个组件内出现 **2 个以上互不相关的 `useState` 主题**（例如同时管「筛选条件」和「弹窗开关」）
- JSX 嵌套超过 **5 层**
- 组件内出现 **3 个以上 `useEffect`**
- 同一段 JSX 结构在两处以上重复
- 一个组件同时承担「取数」+「过滤/排序」+「渲染」三件事

### 5.3 组件接口约定

- **【必须】** props 必须有显式的 TypeScript 接口定义，不使用内联匿名类型。
- **【必须】** props 数量超过 **7 个** 时必须重新设计（拆组件、或用组合而非配置）。
- **【应当】** 优先用 `children` / slot 组合，而非布尔开关堆叠。出现 `showX` / `hideY` / `isZMode` 三个以上并列布尔 props 时，说明该组件应拆成多个。
- **【必须】** 展示组件不得从全局 store 直接取数，数据一律经 props 传入 —— 这是保证组件可测、可复用的前提。
- **【禁止】** 在组件内直接读 `import.meta.env`，环境变量统一经 `shared/config` 收口。

### 5.4 【必须】副作用约束

- 数据获取一律走 `features/*/api/` 的 query hooks，**禁止**在组件里用 `useEffect` + `fetch` 手写取数。
- `useEffect` 仅用于「与外部系统同步」（订阅、DOM 测量、定时器、WS 监听），**禁止**用于「由 props/state 推导出另一个 state」—— 这类场景一律用渲染期计算或 `useMemo`。
- 每个 `useEffect` **必须**有清理函数（若订阅了任何东西）。

---

## 6. 文件体量规范

### 6.1 【必须】行数分级

适用于 `src/` 与 `e2e/` 下的**源码文件**（`.ts` / `.tsx` / `.css`）。以 `wc -l` 统计的**物理行数**（含空行与注释）为准 —— 唯一标准是可机器校验、无歧义。

| 阈值 | 等级 | 处理 |
|---|---|---|
| ≤ 200 行 | 健康 | — |
| 201–400 行 | 警戒 | Review 时需说明为何不拆 |
| 401–800 行 | 高危 | PR 描述**必须**给出拆分计划或不拆的充分理由 |
| **> 800 行** | **违规** | **CI 失败，禁止合入** |

**豁免清单**（不计入统计，需在 lint 配置中显式列出）：自动生成的类型声明文件、翻译资源 JSON、锁文件、快照文件。文档（`.md`）、配置文件不在本条约束范围内。

### 6.2 【必须】行数之外的配套指标

行数是滞后指标，下列为先行指标，同样纳入 lint：

| 指标 | 上限 |
|---|---|
| 单个函数/组件行数 | 150 行 |
| 圈复杂度 | 15 |
| 函数参数个数 | 4 个（超出用 options 对象） |
| 单文件导出的组件数 | 1 个（工具函数与类型不受限） |
| JSX 嵌套深度 | 5 层 |

### 6.3 拆分手法（推荐顺序）

1. **抽逻辑到 hook** —— 状态与副作用搬进 `features/*/hooks/`，组件只剩渲染。收益最大，优先做。
2. **抽子组件** —— 按视觉区块切分（头部/列表/空态/错误态）。
3. **抽纯函数** —— 数据变形、格式化、排序过滤搬进 `utils/`，顺便变得可单测。
4. **抽常量与配置** —— 长枚举、映射表、图标映射搬进 `constants/`。
5. **按领域再拆 feature** —— 前四步之后仍然超标，说明这个 feature 装了两个领域。

---

## 7. 状态管理规范

### 7.1 【必须】四类状态的归属

| 状态类型 | 定义 | 归属 | 举例 |
|---|---|---|---|
| **服务端状态** | 后端拥有的数据 | **TanStack Query** | 会话列表、容器列表、Skill 列表、Diff 内容、Cron 任务 |
| **流式状态** | WS 推送的增量，本地累积 | **Zustand（专用 store）** | 消息 delta、工具执行状态、token 用量 |
| **客户端 UI 状态** | 纯界面状态，与后端无关 | **Zustand** | 侧栏折叠、底部面板高度、主题、当前标签页 |
| **URL 状态** | 应当可分享、可刷新保留的状态 | **React Router（URL）** | 当前会话 ID、当前子视图、筛选条件、分页 |

### 7.2 【必须】服务端状态单一来源

- **禁止**把 `useQuery` 的结果通过 `useEffect` 写进 Zustand。这是 v1 最主要的架构债，两份数据的失效时机永远对不齐。
- 需要跨组件共享服务端数据时，**在各处直接使用同一个 query key** —— TanStack Query 自带去重与缓存共享，这就是它的用途。
- query key **必须**集中定义在 `features/*/api/` 的 key 工厂中，**禁止**在组件里手写字符串数组。
- 所有 query key **必须**包含用户身份维度，确保切换账号时缓存不串。

### 7.3 【必须】写操作统一走 mutation

- 所有写操作（POST / PUT / PATCH / DELETE）**必须**封装为 `useMutation`，**禁止**在组件里直接 `await api.xxx()`。
- 每个 mutation **必须**显式声明成功后的失效范围（invalidate 哪些 key）。
- 需要即时反馈的操作**应当**实现乐观更新，并实现回滚。

### 7.4 【必须】流式状态的边界

WS 推送的消息增量是唯一允许绕开 Query 的服务端来源，规则：

- 流式数据写入**专用 Zustand store**，与 Query 缓存物理隔离，不互相回写。
- 会话「一次性快照」（历史消息）走 Query；「增量」走 WS store；组件层做合并，合并逻辑放在 hook 里，**不写在组件内**。
- 重连后的补偿拉取**必须**通过 Query 的 invalidate 触发，不手写 fetch。

### 7.5 Zustand store 约束

- **【必须】** 每个 store 归属一个 feature，放在 `features/*/stores/`。**禁止**建立跨领域的「全局大 store」。
- **【必须】** 只有真正全应用共享的 store（认证、主题、Toast）才放 `app/` 或 `shared/`，数量**不超过 3 个**。
- **【必须】** 组件订阅 store **必须**使用选择器精确订阅单个字段，**禁止**整体订阅导致无关重渲染。
- **【必须】** 认证 token **禁止**持久化到 localStorage / sessionStorage（延续 v1 的正确做法：access token 只驻内存，refresh token 走 HttpOnly Cookie）。

---

## 8. 路由规范（React Router）

### 8.1 【必须】基本约定

- 使用 React Router 7 的 **data router**（`createBrowserRouter`），**不使用** hash 路由，**不启用** framework 模式。
- 路由表**必须**集中声明在 `app/router/`，单一文件超出 §6 阈值时按顶层区段拆分，但仍集中在该目录。
- **禁止**在业务组件里做路由分发（v1 把 10 种路由的 switch 写在 `App.tsx` 里，且导航与解析各写一遍）。

### 8.2 【必须】路径常量化

- 所有路由路径**必须**定义为常量（含参数构造函数），**禁止**在任何地方硬编码路径字符串。
- 跳转**必须**使用 `Link` / `navigate` + 路径常量，**禁止**直接操作 `window.location`。

### 8.3 【必须】路由级能力

| 能力 | 要求 |
|---|---|
| 代码分割 | 每个顶层路由**必须**懒加载 |
| 错误边界 | 每个顶层路由**必须**挂 `errorElement`，错误信息经 i18n |
| 加载态 | 每个懒加载路由**必须**有 fallback，且 fallback 文案经 i18n |
| 鉴权 | 未登录重定向在路由守卫层统一处理，**禁止**在页面组件内各写一遍 |
| 404 | **必须**有全局兜底路由 |

### 8.4 【必须】URL 即状态

凡是「刷新后应当保留」或「值得分享给同事」的状态，一律进 URL —— 当前会话、当前子视图（chat / terminal / files / diff / preview / browser）、列表筛选与排序、分页。**禁止**把这类状态只存在组件 state 里。

---

## 9. 样式与主题规范

### 9.1 【必须】Tailwind 4 token 化

- 主题**必须**在 `styles/` 中通过 Tailwind 4 的 `@theme` 定义，产出语义化工具类。
- **禁止**在 className 中使用颜色任意值语法（`hsl(var(--x))`、`bg-[#xxxxxx]` 等）。这是 v1 最大的样式债 —— 1712 处、76 个文件。ESLint 需配 `no-restricted-syntax` 拦截。
- 颜色、间距、圆角、字号、阴影、层级（z-index）**必须**全部来自 token，**禁止**魔法数字。

### 9.2 【必须】语义 token 而非具象 token

token 命名按**用途**而非**外观**。`--color-surface-raised` 是对的，`--color-dark-gray-2` 是错的 —— 后者在浅色主题下会自相矛盾。

至少需要覆盖的语义组：

| 组 | 说明 |
|---|---|
| 表面层级 | 背景、卡片、抬升面、覆盖层 |
| 文字层级 | 主要、次要、弱化、禁用、反色 |
| 边框 | 默认、强调、聚焦环 |
| 品牌与交互 | 主色、主色前景、悬停、按下 |
| 语义状态 | 成功、警告、错误、信息 —— 与品牌色**必须**分开定义 |
| 领域状态 | 工具执行态（待定/运行中/完成/失败）、权限态（允许/拒绝/待确认） |

### 9.3 【必须】多主题 × 双模式（依设计稿修订）

设计稿定义 **8 套主题**（default / azure / cobalt / graphite / lagoon / ink / ochre / sepia）× **浅色 / 深色 / 跟随系统** 三种颜色模式 × **4 档字号**：

- 实现方式：`<html>` 上的 `data-theme` / `data-mode` / `data-fs` 属性 + `src/styles/tokens.css` 中的运行时变量（`--t-*`）重定义；Tailwind 工具类经 `@theme inline` 映射到这些变量。
- 深色是**整套 token 反色**（共享一个暖深色地面，accent 按主题保留），不是滤镜；**禁止**在组件里写 `isDark ? A : B` 条件样式。
- 字号档位通过 `html` 根字号百分比缩放（92%/100%/109%/120%），因此**组件尺寸优先用 rem 系（Tailwind spacing/text token）**，让整个界面随档位缩放——这是设计稿 zoom 机制的 rem 落地。
- `mode: 'system'` 读 `prefers-color-scheme` 并监听变化；用户显式选择持久化到本地 + 服务端 preferences。
- 新增视觉必须在「默认主题浅色 + 默认主题深色」两个组合下验收；其余主题由 token 体系保证。

### 9.4 【必须】为 RTL 预留

即便首批语言不含 RTL 语种，方向相关样式**必须**使用逻辑属性（`ms-` / `me-` / `ps-` / `pe-` / `start` / `end`），**禁止**使用 `ml-` / `mr-` / `left` / `right`。事后全量改造的成本远高于一开始就写对。

### 9.5 其他

- **【必须】** 尊重 `prefers-reduced-motion`，动画在该模式下降级。
- **【必须】** 交互元素有可见的键盘聚焦态。
- **【应当】** className 顺序由 `prettier-plugin-tailwindcss` 自动排序，不做人工争论。

---

## 10. 国际化规范

> **这是本项目的一等公民约束。** 任何新页面、新组件、新提示语，不支持多语言即视为未完成，不得合入。

### 10.1 【必须】语言矩阵

| 语言 | 代码 | 角色 |
|---|---|---|
| 英语 | `en-US` | **基准语言**（`fallbackLng`），key 与英文文案同步维护 |
| 简体中文 | `zh-CN` | 一等公民，与英语同步交付 |

**基准语言选 en-US 的理由**：后端错误码、技术术语、第三方文案本身是英文；未来新增语种时以英文为翻译源，链路最短。两种语言在验收上**同等要求**，不存在「先做英文、中文以后补」。

> ⚠️ 若团队希望以 zh-CN 作为基准语言，这是唯一需要在开工前拍板的选型点，其余规范不受影响。

### 10.2 【必须】资源组织：命名空间 = feature

- 翻译文件按**命名空间**切分，命名空间与 `features/<name>` **一一对应**，同名。
- 另设两个特殊命名空间：`common`（跨领域通用文案：确定/取消/保存/加载中…）与 `errors`（后端错误码映射，见 §10.7）。
- 目录形态：`locales/<语言>/<命名空间>.json`。
- **【必须】** 按路由懒加载命名空间，**禁止**首屏一次性加载全部语言资源。

### 10.3 【必须】key 命名规范

统一格式：

```
<命名空间>:<区块>.<元素>[.<状态或变体>]
```

约定：

- 层级**不超过 4 段**；段内使用 camelCase。
- **禁止**用原文当 key。用英文原文做 key 意味着改一次文案就要改所有引用点，且中英文 key 无法对齐。
- **禁止**动态拼接 key（`t('prefix.' + type)`）。提取工具扫不到动态 key，会造成漏翻且无法检测未使用项。确需按变量取值时，**必须**建立显式的「取值 → key」映射表并放在 `constants/`。
- 同一 key 在所有语言文件中**必须**存在；缺失由 CI 拦截（§10.8）。

参考形态：`session:list.empty.title`、`chat:input.placeholder`、`sandbox:status.running`、`common:action.cancel`。

### 10.4 【必须】文案不进组件

- 任何**面向用户可见**的字符串**必须**来自 `t()`，**禁止**硬编码。包括但不限于：按钮文字、标题、占位符、空态、错误提示、Toast、确认框、`aria-label`、`title` 属性、图表轴标签、日期格式、页面 `<title>`。
- 不面向用户的字符串（日志、测试 ID、内部枚举值、CSS 类名）**不进** i18n。
- 由 ESLint（`eslint-plugin-i18next` 的 `no-literal-string` 或等价规则）在 CI 拦截，白名单显式登记。

### 10.5 【必须】句子完整性

- **禁止**用字符串拼接组装句子。不同语言的语序、量词、介词位置都不同，拼接必然出错。
- 变量一律用**插值占位符**；带数量的文案一律用 **i18next 的复数机制**（不是 `count > 1 ? 's' : ''`）。
- 文案中含链接、加粗等富文本时，使用 i18next 的组件插值（`Trans`），**禁止**把句子切成三段分别翻译。
- 每条 key **应当**附 `_comment` 或独立的上下文说明，告诉译者这句话出现在哪里 —— 同一个英文词在不同语境下译法不同。

### 10.6 【必须】日期、数字与相对时间

- 一律使用 `Intl`（`Intl.DateTimeFormat` / `Intl.NumberFormat` / `Intl.RelativeTimeFormat`），并传入当前语言。
- **禁止**手写日期格式化（v1 的 `toLocaleString()` 无参调用会随浏览器区域漂移）。
- **禁止**硬编码单位与分隔符（千分位、小数点、货币符号、字节单位）。
- 封装为 `shared/lib` 的统一格式化函数，全项目只有这一处实现。

### 10.7 【必须】后端错误消息的处理

v1 直接把后端返回的 `detail` 字段显示给用户，这条路在多语言下走不通。v2 规定：

- 后端**返回稳定的错误码**（如 `SANDBOX_NOT_READY`），前端在 `errors` 命名空间做码 → 文案映射。
- 未知错误码**必须**有兜底文案（「操作失败，请重试」类），并把原始码记入日志/上报，**禁止**把裸码或英文堆栈直接展示给用户。
- 该约定需与后端同步确认；在后端就位前，前端**必须**先建立映射层并对未知码走兜底，不得直接透传。

### 10.8 【必须】i18n 的 CI 门禁

下列检查全部纳入 CI，任一失败则阻断合入：

| 检查项 | 说明 |
|---|---|
| key 完整性 | 所有语言的 key 集合完全一致，无缺失、无多余 |
| 硬编码文案 | 组件中不存在未走 `t()` 的用户可见字符串 |
| 未使用 key | 翻译文件中不存在代码里不再引用的 key（防止资源无限膨胀） |
| key 类型安全 | 开启 i18next 的 TS 类型增强，拼错的 key 编译期报错 |
| 插值参数一致 | 同一 key 在各语言中的插值变量名一致 |

### 10.9 【必须】新页面的 i18n 验收项

新页面/新组件合入前逐条自查：

- [ ] 无任何硬编码用户可见字符串（含 `aria-label` / `title` / 占位符）
- [ ] 新增 key 在 `en-US` 与 `zh-CN` 中均已补齐
- [ ] 命名空间与所属 feature 同名，且按路由懒加载
- [ ] 带数量的文案使用复数机制
- [ ] 日期/数字/字节走统一格式化函数
- [ ] 错误提示走错误码映射，含未知码兜底
- [ ] 在**两种语言下都实际截图验收过**布局 —— 德语式长词、中文短句都不会撑破或塌陷
- [ ] 方向相关样式使用逻辑属性

---

## 11. 数据契约与 API 层

### 11.1 【必须】分层

| 层 | 位置 | 职责 |
|---|---|---|
| 传输层 | `shared/api/` | fetch 封装、认证头注入、401 刷新与重试、统一错误规范化、超时与取消 |
| 契约层 | `features/*/api/` | 该领域的端点定义、请求/响应类型、query key 工厂 |
| 使用层 | `features/*/api/` | `useXxxQuery` / `useXxxMutation` hooks，供组件消费 |

**禁止**出现 v1 那样的单文件全局 `api.ts`（421 行、覆盖 21 个路由前缀）—— 按领域拆到各自 feature 下。

### 11.2 【必须】约定

- 组件**只**消费 hooks，**禁止**直接触碰传输层。
- 认证与刷新逻辑集中在传输层，**必须**保留 v1 已验证的**刷新互斥锁**（并发 401 只发一次刷新请求）。
- 所有响应类型**必须**显式声明，**禁止** `any`；`unknown` + 收窄是可接受的。
- **应当**在传输层边界做运行时校验（后端契约变更时快速失败，而非在渲染层炸开）。若引入校验库，走 §2.3 准入流程。
- 错误**必须**规范化成统一形状（错误码 + 原始信息 + HTTP 状态），供 §10.7 的映射层消费。

---

## 12. 实时通信规范

### 12.1 【必须】单一客户端

- 全项目**只有一个** WebSocket 客户端实现，位于 `shared/ws/`。v1 的 `useWS.ts` / `useWebSocket.ts` 双实现并存**禁止**重现。
- PTY 终端若确需独立连接，**必须**复用同一客户端的连接管理、重连与鉴权逻辑，仅在通道/协议层区分，并在命名上明确体现差异。

### 12.2 【必须】保留 v1 已验证的机制

以下 v1 做对的设计**必须**在 v2 延续：

- 握手使用一次性 ticket 换取连接，**禁止**把 access token 放进 WS URL（避免落入网关与代理日志）。
- 指数退避重连。
- **重连补偿**：恢复连接后主动对齐断线期间可能遗漏的状态（待处理权限请求、待回答问题、当前会话消息）。补偿动作走 Query invalidate（§7.4）。

### 12.3 【必须】事件契约

- 所有事件名与载荷类型**必须**集中定义在 `shared/ws/` 的契约文件中，作为前后端的单一事实来源。
- 事件名**必须**遵循 `<领域>.<动作>` 格式，与后端约定一致。
- **禁止**在组件内直接订阅 WS 事件。订阅统一在 feature 的 hook 层完成，事件 → 状态的写入路径全项目唯一。
- 收到未知事件**必须**静默忽略并记录，不得抛错中断连接。

---

## 13. 测试规范

### 13.1 【必须】三层结构

| 层 | 工具 | 覆盖对象 | 要求 |
|---|---|---|---|
| 单元测试 | Vitest | 纯函数、格式化、数据变形、store reducer | 逻辑分支全覆盖 |
| 组件测试 | Vitest + Testing Library | 展示组件、hooks | 覆盖空态/加载态/错误态/正常态四态 |
| 端到端 | Playwright | 关键用户链路 | 见 §13.3 |

### 13.2 【必须】覆盖率门槛

- `shared/lib`、`shared/api`、各 feature 的 `utils/` 与 `stores/`：**行覆盖率 ≥ 80%**。
- 其余代码不设硬门槛，但**禁止**覆盖率相比上一次基线下降。

### 13.3 【必须】E2E 必测链路

至少覆盖：

1. 登录（含 OIDC 回调）→ 进入工作区
2. 创建会话 → 发送消息 → 收到流式响应 → 工具执行卡片正确渲染
3. 权限请求弹出 → 批准 → 会话继续
4. 沙箱创建 → 终端连接 → 执行命令回显
5. **语言切换 → 界面全量切换，无残留原文**

### 13.4 测试写法约定

- **【必须】** 元素定位优先用可访问性角色与文本，其次用 `data-testid`；**禁止**依赖 CSS 类名或 DOM 结构定位。
- **【必须】** `data-testid` 的值**不进** i18n，且不随文案变化。
- **【应当】** 断言面向用户可见行为，而非内部实现细节。

---

## 14. 质量门禁与 CI

### 14.1 【必须】CI 必过项

| 检查 | 失败后果 |
|---|---|
| 类型检查（`tsc --noEmit`） | 阻断 |
| ESLint（**配置文件必须存在于仓库**） | 阻断 |
| Prettier 格式检查 | 阻断 |
| 单元 + 组件测试 | 阻断 |
| 覆盖率门槛（§13.2） | 阻断 |
| 文件行数上限（§6.1） | 阻断 |
| 分层依赖与循环依赖（§4.3） | 阻断 |
| i18n 五项检查（§10.8） | 阻断 |
| 构建成功 | 阻断 |
| 性能预算（§16.1） | 阻断 |
| 未使用依赖 / 未使用导出 | 告警（连续两次则阻断） |
| E2E 关键链路 | 阻断（主干与发布分支） |

### 14.2 【必须】ESLint 规则基线

配置文件**必须**入库并随 CI 执行（v1 的教训：装了 5 个 lint 包却没有配置文件，lint 从未跑通）。至少启用：

| 规则来源 | 用途 |
|---|---|
| `typescript-eslint`（推荐 + 类型感知） | 类型层面的错误用法 |
| `eslint-plugin-react-hooks` | hooks 依赖与调用规则 |
| `eslint-plugin-boundaries` / `import/no-restricted-paths` | §4 分层依赖 |
| `import/no-cycle` | 循环依赖 |
| `max-lines` / `max-lines-per-function` / `complexity` / `max-params` | §6 体量指标 |
| `eslint-plugin-i18next`（`no-literal-string`） | §10.4 硬编码文案 |
| `no-restricted-syntax`（自定义） | §9.1 禁用颜色任意值 |
| `@typescript-eslint/no-explicit-any` | 禁 `any` |
| `eslint-plugin-unused-imports` | 清理死代码 |
| `eslint-plugin-jsx-a11y` | 可访问性基线 |

### 14.3 【必须】提交前本地门禁

配置 pre-commit（lint-staged）执行：格式化 + 增量 lint + 相关类型检查。目的是把问题拦在推送前，而不是等 CI 红灯。

---

## 15. 命名与风格约定

| 对象 | 约定 |
|---|---|
| 目录 | kebab-case（`agent-parts`） |
| 组件文件 | PascalCase，文件名与默认导出组件同名 |
| hook 文件 | camelCase，`use` 前缀 |
| 工具/常量文件 | camelCase |
| 类型文件 | camelCase，或 `types.ts` |
| 类型与接口 | PascalCase；**禁止** `I` / `T` 前缀 |
| 常量 | UPPER_SNAKE_CASE |
| 布尔变量 | `is` / `has` / `can` / `should` 前缀 |
| 事件处理函数 | `handleXxx`（定义处）/ `onXxx`（props 名） |
| query key 工厂 | `xxxKeys` |
| WS 事件名 | `<领域>.<动作>` 全小写 |
| i18n key | 见 §10.3 |

补充：

- **【必须】** 禁止 `data`、`item`、`temp`、`info`、`obj` 这类无信息量命名。
- **【必须】** 注释解释「为什么」，不解释「是什么」。代码能自解释的地方不写注释。
- **【应当】** 保留 v1 的一个好习惯：对非显而易见的决策，在代码处写明背景（v1 在端口配置、Logto 交换、Query 包装等处都有这类注释，值得延续）。

---

## 16. 性能预算

### 16.1 【必须】首屏预算

| 指标 | 上限 |
|---|---|
| 首屏 JS（gzip） | **150 KB** |
| 首屏 CSS（gzip） | **25 KB** |
| 单个路由级 chunk（gzip） | 100 KB |
| 首屏语言资源 | 仅当前语言的 `common` + 当前路由命名空间 |

对照 v1 的 314 KB gzip 首屏（其中 71 KB 是未登录页面根本用不到的终端模拟器），预算收紧到一半以内。超预算则 CI 失败。

### 16.2 【必须】强制懒加载清单

以下模块**禁止**进入首屏 chunk，**必须**在实际使用时才加载：

- xterm.js 及其插件
- Markdown 渲染链（react-markdown / remark / rehype / 语法高亮）
- Diff 渲染
- 所有非首屏路由
- 非当前语言的翻译资源

### 16.3 【必须】其他

- `manualChunks` 中列出的每个包**必须**真实被引用（v1 产出了两个 39 字节的空 chunk）。
- 超过 **50 项**的列表**必须**虚拟化（消息流、文件树、会话列表、Cron 历史）。
- 高频更新组件（流式消息）**必须**做渲染隔离，避免整树重绘。
- 大体积静态资源（截图、安装包）**应当**走对象存储或 CDN，不随前端镜像分发（v1 的 `public/` 有 2.4 MB 此类资源）。

---

## 17. v1 资产复用清单

v2 不是白手起家。v1 有一批经过生产验证的实现，**应当**移植；也有一批必须放弃。四级分类：

### 17.1 直接复用（改 i18n + 换 token 即可）

`frontend/src/components/ui/` 全部 9 个原子组件，共 454 行 —— 体量小、无业务耦合、接口设计合理：

| 组件 | 行数 | 移植动作 |
|---|---|---|
| `Badge` | 30 | 颜色改 token |
| `Spinner` | 13 | 颜色改 token |
| `Progress` | 30 | 颜色改 token |
| `Tooltip` | 33 | 颜色改 token + 补 i18n |
| `Tabs` | 36 | 颜色改 token + 补 i18n |
| `Modal` | 57 | 颜色改 token + 补焦点陷阱与 ESC |
| `Dropdown` | 73 | 颜色改 token + 补键盘导航 |
| `Toast` | 86 | 颜色改 token + 文案全量 i18n |
| `ConfirmDialog` | 96 | 颜色改 token + 文案全量 i18n |

> 移植时**必须**补齐可访问性（v1 全站仅 32 处 `aria-*`）。

### 17.2 逻辑移植（照搬算法，重写外壳）

这些是 v1 真正的技术资产，**必须**移植其逻辑，但外壳按 v2 结构重写：

| 来源 | 移植什么 |
|---|---|
| `lib/logto.ts` | PKCE 生成与校验、`state` 校验、回调后清理 URL 与 sessionStorage 防重放 —— 这套实现是正确的 |
| `stores/auth.ts` | token 刷新互斥锁；access token 只驻内存的策略 |
| `services/ws.ts` | ticket 握手、指数退避重连 |
| `hooks/useWS.ts` | 重连补偿逻辑（重拉待处理权限/问题/消息） |
| `stores/session.ts` | 流式消息 reducer（`appendTextDelta` / `addPart` / `updateToolStatus`）、乐观本地会话 ID → 服务端 ID 重映射 |
| `components/chat/MessageList.tsx` | 同轮次 assistant 消息合并算法 |
| `components/parts/` 19 个工具卡片 | 各工具（bash / read / edit / glob / grep / task）的展示逻辑与信息层级 |

### 17.3 重写

| 对象 | 原因 |
|---|---|
| `App.tsx`（348 行） | 路由、鉴权、数据获取、布局四件事混在一起；路由改用 React Router |
| `services/api.ts`（421 行） | 单文件覆盖 21 个路由前缀，按 §11 拆到各 feature |
| `index.css`（233 行） | 改用 Tailwind 4 `@theme`，token 语义化 |
| 全部业务组件的样式层 | 1712 处颜色任意值需改为语义工具类 |
| 全部用户可见文案 | 全量接入 i18n |

### 17.4 废弃

| 对象 | 原因 |
|---|---|
| `hooks/useWebSocket.ts` | 与 `useWS.ts` 职责重叠，合并为单一实现 |
| `dev:mock` 模式 | v1 中该脚本已失效（无 mock 分支），改用 MSW 或直接删除 |
| 6 个零引用依赖 | `@tanstack/react-router`、`framer-motion`、`react-hook-form`、`zod`、`class-variance-authority`、`react-diff-viewer-continued` —— v2 按需重新评估，不默认继承 |
| hash 路由方案 | 由 React Router 取代 |
| `public/` 中的 2.4 MB 引导截图与插件包 | 移出前端镜像 |

---

## 18. 新页面 Definition of Done

新页面合入前，下列全部勾选：

**结构**
- [ ] 页面壳在 `routes/`，业务在 `features/`，无跨 feature 横向 import
- [ ] 所有文件 ≤ 800 行，且无文件进入「高危」区间而无说明
- [ ] 新 feature 有 `index.ts` 出口，外部无深链引用

**数据**
- [ ] 服务端数据走 Query，query key 出自 key 工厂且含用户维度
- [ ] 写操作走 mutation，失效范围已声明
- [ ] 无 `useQuery` → `useEffect` → store 的回灌

**路由**
- [ ] 路径走常量，已懒加载，有 errorElement 与 loading fallback
- [ ] 该保留的状态已进 URL（刷新可还原）

**样式**
- [ ] 无颜色任意值，全部走 token
- [ ] 深色与浅色**都已截图验收**
- [ ] 方向相关样式使用逻辑属性
- [ ] 键盘聚焦态可见

**国际化**
- [ ] §10.9 的 8 项全部通过

**质量**
- [ ] 空态 / 加载态 / 错误态 / 正常态四态都已实现并测试
- [ ] 关键交互有组件测试；若属 §13.3 链路则有 E2E
- [ ] 本地 lint、类型检查、测试全绿
- [ ] 首屏预算未被击穿

---

## 19. 落地路线图

| 阶段 | 内容 | 出口标准 |
|---|---|---|
| **P0 · 地基** | 脚手架、目录骨架、ESLint/Prettier/TS 配置、CI 流水线、Tailwind token 体系、i18n 装配、传输层与 WS 客户端 | **CI 全绿**，且各项门禁能真实拦住违规提交（需构造反例验证，不能只看配置存在） |
| **P1 · 骨架** | 路由表、应用布局、认证链路（Logto + 刷新）、`shared/ui` 九个原子组件移植 | 能登录、能在空壳里切换路由、能切换语言与主题 |
| **P2 · 主链路** | session + chat + agent-parts + permission + question | §13.3 前三条 E2E 通过 |
| **P3 · 沙箱域** | sandbox + terminal + files + diff + preview | §13.3 第四条 E2E 通过 |
| **P4 · 配置域** | project + skill + mcp + cron + settings | 功能对齐 v1 |
| **P5 · 收口** | 性能预算达标、可访问性走查、双语全量校对、v1 下线方案 | 全部门禁达标，可替换 v1 |

**【必须】** P0 不允许压缩或跳过。v1 的全部工程债都源于「先做功能，规范以后补」—— 而「以后」没有到来。P0 的门禁必须用反例实测验证有效，再进入 P1。

---

## 附录 A · 反模式清单

以下写法在 Code Review 中直接打回，无需讨论：

1. 在组件里 `useEffect` + `fetch` 手写取数
2. 把 `useQuery` 的结果同步进 Zustand
3. 组件内直接 `await api.xxx()` 做写操作
4. 手写路径字符串跳转，或直接改 `window.location`
5. className 里写 `hsl(var(--x))` 或十六进制颜色
6. 用户可见文案硬编码在组件里
7. 字符串拼接组装句子
8. 用英文原文当 i18n key
9. 动态拼接 i18n key
10. feature 之间横向 import
11. 深链引用其他 feature 的内部文件
12. `shared/` 里出现业务逻辑（例外：平台资源客户端 auth / containers / ws 事件契约 / 后端 wire 类型允许放 `shared/`，因为它们是传输层契约而非业务逻辑——2026-08-20 修订，见附录 D）
13. 单文件超过 800 行
14. 一个组件同时做取数、变形、渲染
15. `any` 类型（`unknown` + 收窄可以）
16. 展示组件直接读全局 store
17. 三个以上并列布尔 props
18. 把后端 `detail` 字段直接展示给用户
19. `toLocaleString()` 无参调用
20. 用 `ml-` / `mr-` / `left` / `right` 写方向样式
21. `manualChunks` 里列入未被引用的包
22. 提交未配 lint 规则就绕过 CI

---

## 附录 B · 例外登记

| 日期 | 条款 | 位置 | 理由 | 登记人 |
|---|---|---|---|---|
| — | — | — | — | — |

---

## 附录 C · 待确认事项

以下事项需在 P0 开工前拍板，本文档已给出默认值，可直接沿用：

| 事项 | 默认值 | 影响面 |
|---|---|---|
| i18n 基准语言 | `en-US` | 影响 key 维护方式与后续加语种的翻译源（§10.1） |
| 后端错误码契约 | 需与后端确认返回稳定错误码 | 未就位前前端先建映射层 + 兜底，不阻塞（§10.7） |
| 运行时校验库 | 暂不引入 | 若引入走 §2.3 准入（§11.2） |
| PTY 是否独立连接 | 复用统一 WS 客户端的连接管理 | 影响 `shared/ws` 的抽象层次（§12.1） |

---

## 附录 D · 设计稿对齐记录（2026-08-20）

依据「设计稿为准」原则，v2 实施时做出的映射与取舍。**原则：界面呈现严格随设计稿；数据一律来自真实后端；后端没有的能力宁可省略控件，不做假按钮。**

### D.1 版本与选型修订

| 原条款 | 修订 |
|---|---|
| §2.1 React Router 7.x | 实际安装 **react-router 8.x**（data 模式 API 同 7） |
| §2.1 TypeScript 5.7+ | 实际 **6.x**（`baseUrl` 已废弃，paths 用相对映射） |
| §2.1 i18next 25.x | 实际 **26.x**；懒加载后端用 `import.meta.glob` 自实现，未引额外包 |
| §10.1 基准语言 en-US | 保持；但**产品词表源头是设计稿的中英双语词表**，两边同步维护 |

### D.2 品牌与路由

- 品牌名 **bossip**，沿用设计稿 logo（b 方块 + 流光 wordmark）。
- 路由：`/`（官网）、`/login`、`/register`、`/callback`（SSO 回跳）、`/app`（空态/新对话）、`/app/s/:sessionId`（对话）、`/app/settings/:tab`。设计稿词汇「项目/对话」映射后端 `project` / `session`。

### D.3 设计 → 后端能力映射

| 设计稿元素 | 真实数据源 | 取舍 |
|---|---|---|
| 思考折叠条 | `reasoning` part | 完整实现 |
| 过程日志（8 类调用） | `tool` part（bash/read/glob/grep/edit/write/skill/mcp/web_*） | 完整实现；kind/glyph/tone 映射表在 chat 特性 |
| 计划清单卡 | `GET /session/{id}/todo` + `todo.updated` | **只读**：后端无用户增删步骤端点，「加一步 / 删步骤」不做 |
| 改动卡片 → 审阅 | `patch` part + `GET /session/{id}/diff` | 完整实现；审阅面板「全部通过/退回」**省略**（后端无 changeset approve API） |
| 积分 / 订阅 | `session.token_usage`（tokens / cost 聚合） | 设置页改为「用量与消耗」；充值/套餐/发票 UI 省略 |
| 附件 / 语音输入 | 无上传端点 | composer 中省略这两个按钮 |
| 邮箱链接登录 + 微信/Google | 后端为 账号密码 + Logto OIDC | 登录卡改为 账号密码 + 单个 SSO 按钮（logto enabled 时显示） |
| 项目菜单：复制 / 归档 / 置顶 | 无对应端点 | 菜单保留 重命名 / 新建对话 / 删除 |
| 对话行悬停：置顶 / 归档 | 无对应端点 | 改为 删除 |
| 顶栏分享 | 无分享链接服务 | 实现为「复制当前会话链接」+ toast |
| 文件面板内容预览 | **新增后端端点** `GET /api/containers/{id}/files/content?path=` | 转发容器 `/read_file` 并去行号（backend/api/files.py，本次唯一后端改动） |
| 终端 | WS `/ws/terminal/{containerId}?ticket=` PTY 字节透传 | 完整实现（xterm，懒加载） |
| 浏览器面板 | WS `/ws/dev-browser/auto?ticket=` 截图流 | 移植 v1 协议 + 设计稿皮肤 |
| 权限/提问交互（设计稿未覆盖） | `permission.asked` / `question.asked` | **必须补**：行内卡片，沿用设计语言（后端流程依赖它） |
| 字号缩放（root zoom） | — | 按对接文档建议改为 html 根字号 + rem |

### D.4 实施期发现并修复的后端问题（2026-08-20 联调）

| 问题 | 修复 | 位置 |
|---|---|---|
| `step-start` / `step-finish` part 从未落库：`save_part()` 未传 `is_new=True`，UPDATE 不存在的行被静默丢弃 → **会话 diff 功能自后端重构起整体断链**（v1 亦受影响），过程耗时也拿不到 | 两处调用补 `is_new=True` | `backend/agent/loop.py` |
| 无文件内容读取端点（工作面板文件预览无数据可用） | 新增 `GET /api/containers/{id}/files/content?path=`（转发容器 `/read_file` 并去行号） | `backend/api/files.py` |
| 前端 diff 查询未带 `?full=true` → 审阅面板无逐行 hunks | 查询带上 `full=true` | `features/workbench/api/diff.ts` |

### D.4.1 第二轮修复（2026-08-20 晚，用户验收反馈）

| 反馈 | 根因与修复 |
|---|---|
| 气泡没有左右分侧 | ChatFlow 行 wrapper 是普通 div，`self-end` 无效（父级非 flex）→ wrapper 加 `flex flex-col` |
| 流式输出不顺畅、难看 | react-markdown 每个 delta 全量重解析 → 换 **streamdown**（DEEIX-Chat 同款）：分块解析+块级 memo+不完整语法容错+内置流式光标与淡入动画+shiki 双主题代码块（经 shadcn 别名 token 穿 bossip 皮肤，`[data-mode="dark"]` 翻转 `--shiki-dark`）；补 `.text-shimmer`（运行态标题流光）、`.fold`（折叠 220ms 过渡）、工具条目 spinner 徽标+滑入、思考折叠流式尾行预览、TypingRow shimmer；滚动器换 ResizeObserver 贴底+顶/底渐隐遮罩+overscroll-contain+overflow-anchor:none+发送强制滚底 |
| 输入框样式功能不对 | 重写 Composer 对齐设计：附件 tiles 行 + 输入行（busy 时行内「停止生成」）+ 操作行 [附件 ＋ ▸ ⊙模型胶囊 ▸ 40px 发送圆钮]；附件=真实上传（粘贴亦可），气泡下方渲染附件胶囊 |
| 附件无后端（用户授权补） | 新增 `POST /api/containers/{id}/files/upload`（multipart → base64 分块经容器 /execute 落至 /workspace/uploads，≤8MB），消息尾部附 `[attachments]` 路径块由 UserBubble 解析为胶囊 |

依赖新增：`streamdown`（懒加载 Markdown chunk 内，首屏 122.8KB gzip 仍在预算内）。

### D.4.2 第三轮：聊天区 1:1 还原 DEEIX-Chat（2026-08-20 深夜）

用户要求聊天页与过程输出 UI/UX 与 DEEIX-Chat 完全一致，原实现作废重做。**右侧工作面板不在本次范围内，未改动。**

**拆解到的参考规格**（源：`~/workspace/DEEIX-Chat/frontend`）：

| 元素 | DEEIX 规格 | 本项目落地 |
|---|---|---|
| 助手消息 | **无头像、无气泡**，占满列宽；`text-[15px] leading-8 [overflow-wrap:anywhere]` | `AssistantTurn` 重写；尺寸用 rem token（`text-lg`）以保留字号档位缩放 |
| 用户消息 | 右对齐，`max-w-[70%] rounded-xl bg-muted/60 p-3`，移动端 88% | `UserBubble` 重写 |
| 消息列 | `mx-auto w-full max-w-[760px] space-y-6` | `ChatFlow` 对齐（760px / gap-6） |
| trace 行 | 无边框手风琴：13px 中粗标题 + 11px 弱化副标题 + 右侧 chevron（展开 rotate-180），`mb-2 w-full pr-4 sm:pr-6` | `TraceShell` 三 trace 共用 |
| 三条 trace | 处理中/**处理完成** + 准备 N tokens 上下文 · 正在思考/**思考完成** + 固定副标题 · 工具调用中/**工具调用** + N 次工具调用 | `ProcessTrace` / `ThinkingTrace` / `ToolChainTrace`，文案取自 DEEIX zh-CN 词表 |
| trace 顺序 | **聚合在正文之上**（process → think → tools），不与正文交错 | `buildTurnView` 聚合装配，取代原 `buildBlocks` 交错序列 |
| 折叠行为 | 运行中自动展开 + 标题 shimmer；正文开始输出后自动收起；手动切换优先 | `TraceShell` 渲染期派生，无 effect 同步 |
| 工具行 | `grid-cols-[0.875rem_8rem_1fr] gap-x-5 text-[12px]` 时间轴：连接线 + 圆点（`ring-4 ring-background`）+ 定宽名称列 + 详情列 | `ToolChainRows` |
| 长输出 | 超 8 行（`1.25rem` 行高）截断，底部渐隐 + 展开/收起 | `DetailText`（ResizeObserver 量高） |
| 流式占位 | 骨架条 `max-w-[680px] space-y-2.5`，非光标 | `StreamSkeleton` |

**删除**：`ReasoningFold` / `ProcessFold` / `ToolEntry` / `AnswerText` / `lib/turns.ts`（被 `lib/turn-view.ts` 取代）。

**数据映射**（保持真实后端，无编造）：`step-finish.input_tokens` → 准备 N tokens 上下文；`reasoning` parts → 思考 trace；`tool`+`subtask` parts → 工具链；`text` parts 拼接 → 正文。

E2E 新增 `chat-ui.spec.ts` 锁死该形态（气泡分侧、无头像、trace 标题+副标题+展开态）。

### D.4.3 第四轮：元信息条 / 工具输出 / 输入框（2026-08-21）

用工作流做了 7 维度全量对比（108 条差距），按优先级实施。

**用户点名的三项**

| 项 | 落地 |
|---|---|
| 消息元信息条 | 悬浮显隐（`group/msg` + `md:group-hover`）；徽标行 = 模型 · 输入/输出/缓存 tokens · 耗时；操作行 = 复制/点赞/点踩/复刻/时间戳。**重试与编辑按钮明确不做**（后端无重生成/编辑端点，本项目也无消息树） |
| 工具结构化输出 | 按 `resolveToolLayout` 分派 7 种布局：search（关键词 + 域名胶囊 + 标题摘要）、fetch、shell（命令/输出 + 退出码红调）、file（路径 + old→new 双块）、find、agent、generic（参数/结果 JSON）；长输出 8 行截断 + 渐隐 + 展开 |
| 输入框「丑黑边」 | **根因**：全局 `:focus-visible { outline: 2px solid var(--t-a700) }` 中 a700 在默认主题≈墨黑，且优先级压过 textarea 的 `outline-none`。**修法**：`textarea/input:focus-visible { outline: none }`，焦点表现交给容器 `focus-within:border-n400`（DEEIX InputGroup 形态） |

**输入框其余重写**：形变主按钮（停止收进发送槽，不再是两个控件）· 拖拽上传（dragenter 嵌套计数）· 附件卡片（类型图标 + 大小）· `+` 下拉（上传/截图 `getDisplayMedia`）· 仅附件可发送 · 发送快捷键 Enter/⌘Ctrl+Enter（存 preferences.extra）· 粘贴截图自动命名 · **@ 提及**（文件/技能）与 **/ 命令** 菜单（键盘导航优先于发送快捷键）

**本轮后端新增（均实测）**

| 能力 | 改动 |
|---|---|
| 消息反应 | `messages.reaction` 列 + 迁移 `d4f6a8c0e2b4` + `POST .../message/{mid}/reaction` |
| 工具 metadata 透传 | `ToolPartData.metadata`（bash `exit_code`、`truncated`、`duration`） |
| web_search 结构化结果 | Tavily/DuckDuckGo 均返回 `metadata{query, results:[{title,url,snippet}]}` —— 否则前端只能正则解析编号文本 |
| 消息 error 回显 | `get_messages` 补 `error=m.error` |
| 文件搜索 | `GET /api/containers/{cid}/files/search?q=` —— @ 提及的数据源 |

**明确不做**：重试/编辑/分支导航（需引入消息树模型）· 会话分享 · 语音输入 · Markdown 预览切换 · 排队消息（与「插话即打断重启」语义冲突）· 数学公式/mermaid/HTML 透传。

### D.4.4 第五轮：流式抖动 / 代码块 / 改动 diff（2026-08-21）

| 问题 | 根因与修复 |
|---|---|
| **折叠 trace 在流式时反复开合，屏幕跳动** | `TraceShell` 的 `open` 是从 `streaming` **派生**的，而活跃标志在一轮内反复翻转（工具1结束→工具2开始的间隙、推理与工具交替）→ 每翻转一次就开合一次。改为 **闩锁**（DEEIX 语义）：只有「活动开始」开、「本轮可作答」关一次，其余一律保持；并把 per-part 标志收敛为 phase 级（`preAnswer` / `thinkingLive` / `toolsLive`），顺带消除标题在「正在思考↔思考完成」间闪烁 |
| **代码块样式不对** | 开启 streamdown `lineNumbers`（仅 default 变体），并为其 `data-streamdown="code-block-*"` 槽位补样式：语言标签+复制在框外、框体 14px 圆角、浅灰底、行号列 `text-n500` 不可选 |
| **改动展示需要 diff 且可点开审阅** | 见下 |

**改动卡片（DiffPreview）**

- **后端原本从不产生 `patch` part** —— 改动信息只存在于会话累计 diff 里，无法归属到具体轮次。现于 `agent/loop.py` 快照变化处用 `snapshot.diff()` 落 `PatchPart`，并带上 `from_snapshot`/`to_snapshot`。
- 新增 `GET /api/agent/session/{sid}/diff/step?from_snapshot=&to_snapshot=`（复用 `snapshot.diff_full`）：会话 diff 是**累计**的，若用它渲染单步卡片，会出现「头部 +1−1、正文却是 3 行新增」的自相矛盾。按快照区间取才对得上。
- 前端 `buildDiffPreview` 把 hunks 压成预览：只留改动行，连续 context（含跨 hunk 跳跃）合并成一条「N 行未修改」条；超出 8 行的改动记入 `hiddenChanges`。点击卡片 → `emitAppEvent("workbench.open", {kind:"review"})` 打开侧栏审阅。
- **工具链里的文件输出同款**：`DiffRows` 抽为共用组件，`edit`/`multiedit` 用 `editPreview`（按首尾公共行收敛）渲染真行级 diff，取代原来的「删块+增块」两坨。

> 注意：快照的 work-tree 是**项目目录**（`project_directory(slug)`），项目目录之外的文件改动不会进快照，也就没有 patch part。写 E2E 时踩过这个坑。

单测：`diff-preview.test.ts` 覆盖 context 折叠、跨 hunk 合并、截断计数、纯新增/纯删除、无 hunks 等 9 例。

### D.4.5 第六轮：「点了审阅，侧边栏没有？」（2026-08-21）

用户点击改动卡片后，侧栏**确实打开了**（Playwright 四种场景 4/4 均通过），但打开的是一个**空壳**：头部写着「本轮改动 +0 −0」，下面没有任何文件。之前手动验收看起来正常，只是因为那次会话 diff 恰好已在缓存里。

| 问题 | 根因与修复 |
|---|---|
| **面板打开后短暂全空，读起来像「没反应」** | `ReviewTab` 的守卫是 `if (!isLoading && entries.length === 0)` —— 加载中会**跳过空状态**，直接用 `data ?? []` 渲染真实头部，于是 `+0 −0` 叠在空列表上。面板只在用户点进来时才发起请求（实测点击后 485ms 才发出，800ms 才填上），这段空窗全暴露给用户。改为 `if (isLoading)` 先渲染骨架屏（`aria-busy` + 脉冲卡片 + Spinner），**不显示尚不成立的计数** |
| **同上，从根上消除空窗** | 新增 `usePrefetchSessionDiff`，改动卡片 `onMouseEnter`/`onFocus` 即预取会话 diff。指向卡片到按下之间的时间足够跑完请求，实测面板**打开即满**（+2307 −2 / 6 个文件，0 空窗） |
| **点击的文件在列表下方看不见** | 侧栏若已打开且文件多，`setReviewFile` 只是换了展开项，视口没动 → 又是一次「点了没反应」。展开卡片 `scrollIntoView({block:"nearest"})` 滚入视野 |
| **卡片头部不可聚焦、鼠标无指针反馈** | `<div onClick cursor-default>` → `<button type="button" aria-expanded>` |
| **工具链里的文件 diff 长得一模一样却点不动** | 与改动卡片同款外观就该同款行为，否则是第二个「死点击」面。`FileOutput` 的每个 edit 块在已知 path 时包成 button，同样 `emitAppEvent("workbench.open", {kind:"review", file})` |
| **`<button>` 里塞 `<div>`（非法嵌套）** | 改动卡片是 `<button>`，而 `DiffRows` 渲染 `div`。`DiffRows` 全部改用 `span` + `block`/`flex`，两种宿主下视觉不变 |

> E2E 教训：原 `diff-card.spec.ts` 只断言「`本轮改动` 可见」，而**空壳面板也有这行字**，所以这个 bug 从测试里漏了过去。已加强为：点击文件必须**出现在列表里**，且必须是 `aria-expanded="true"` 的那张卡。

### D.4.6 第七轮：改动卡片瘦身 + 开面板白屏（2026-08-21）

**① 改动卡片不再内联 diff。** 新建一个 340 行的文件，卡片就在对话流里铺开一大块绿色，把用户真正要看的回答挤到屏幕外。改为**一行淡色列表**：`⊞ path/name  +340  审阅 →`（26px 高，`text-n600`，悬停转 `text-ink`/强调色）。hunk 属于审阅侧栏，不属于对话流。

连带的简化 —— 计数本来就在 `PatchPart.files[].additions/deletions` 上，卡片不再需要请求任何 diff：

- `PatchChip` 去掉 `useStepDiff` → **每个 patch part 少一次网络请求**；
- 随之失去调用方的 `buildDiffPreview` / `useStepDiff` / `ChangeRow.no` / `toChange` 一并删除（`DiffRows` 的行号槽从来没被 `editPreview` 填过，是一列 40px 的空白，同时去掉）。工具链里的 `editPreview` + `DiffRows` 保留：那是用户**主动展开**的详情面，diff 正该在那儿。
- 后端 `/diff/step` 端点保留（能力正确，只是前端当前不用）。

**② BUG：打开右侧栏整个工作区白屏 ~420ms 并重新加载。**

根因是 Suspense 边界的位置。`WorkbenchPanel` 是 `<main>` 的**兄弟节点**，不在布局那个只包住 `<Outlet/>` 的 `<Suspense>` 里；而 i18n 命名空间是**按需懒加载**的（`react: { useSuspense: true }` + vite glob backend），`ReviewTab` 的 `useTranslation("workbench")` 首次渲染必然挂起 —— 于是挂起一路冒泡到**路由级**边界（包 `lazy(WorkspaceLayout)` 的那个），整棵工作区被 fallback 顶掉。

代价不只是闪一下：边界恢复时**所有 effect 重新挂载**。实测一次点击打出 12 个请求 —— `POST /auth/ticket` ×2（WS 重连两次）、`/auth/me/preferences`、`/message` `/permission` `/question` `/session` 各两遍。空闲基线是 0 请求。

两处修复，缺一不可：

| 修复 | 作用 |
|---|---|
| `WorkspaceLayout` 用 `<Suspense fallback={null}>` 包住 `WorkbenchPanel` | **结构性**：面板里任何挂起都就地兜住，不再掀翻整个 app。以后面板加懒加载路由/命名空间也不会重蹈覆辙 |
| `usePanelEvents` 挂载时 `i18n.loadNamespaces("workbench")` 预热 | 面板还关着的时候就把命名空间取好，打开时根本不挂起，连局部 fallback 都不闪 |

修复后同一次点击：**1 个请求**（就是面板要的 `/diff`），0 白屏帧。

> 诊断手法值得复用：逐帧采样 `main` 的 `getBoundingClientRect().height`。Suspense 隐藏内容时祖先被置 `display:none`，子节点的 `getComputedStyle().display` **仍报原值**，但 rect 高度归零 —— 光看 computed style 会漏判。另外注意别只抓 `/api/` 请求，`.json` 语言包正是从这个筛子里漏掉的关键线索。

回归测试 `workbench.spec.ts`「opening the panel neither blanks the workspace nor refetches the session」：逐帧断言 `main` 高度不为 0，且期间不得出现 `/locales/`、`/auth/ticket`、`/api/agent/session` 请求。已用「回退修复 → 测试必须失败」验证过（回退后 35 帧白屏）。

### D.4.7 第八轮：思考流 / 文件面板范围 / 面包屑 / 新建对话（2026-08-21）

**① 思考过程大段空白（贪吃蛇提示词复现）。** WS 抓帧定位：`step-start` 之后 **24 秒没有任何事件**，然后一个 13,225 字符的工具参数一次性砸下来 —— 模型在思考+攒整个 write 调用，但一个字都没流回来，前端只有骨架屏。两处根因，都在后端：

| 根因 | 修复 |
|---|---|
| `openai/gemini-*`（走 OpenAI 兼容代理）被 `_detect_provider` 归为 openai，`_get_default_thinking_kwargs` 的 openai 分支没匹配 gemini → **压根没请求思考内容** | 对代理直接试了三种参数形状：`reasoning_effort` ✗、`thinkingConfig` ✗、**Anthropic 风格 `thinking:{type:"enabled",budget_tokens}` ✓**（`reasoning_content` 随流返回）。default 与 variant kwargs 都补上 gemini 分支，经 `extra_body` 透传 |
| LiteLLM 1.81 对该代理的函数调用参数**整块缓冲** | 升级 LiteLLM 1.81.11 → **1.97.0**（用户授权）。升级后工具参数逐块流式，屏幕上「展开代码 85 行 → 164 → 260」实时增长 |

复测：`part.created part=reasoning` + 增量正常到达，思考轨迹渲染出真实推理内容；原 24 秒空白被思考轨迹 + 逐块增长的工具卡填满。前端零改动 —— 渲染管线（ReasoningPart → ThinkingTrace）本来就是通的，只是数据从来没来过。

**② 文件面板显示整个 /workspace（应只显示当前项目目录）。** `/workspace` 是 agent 的整个活动空间；会话真正的工作目录是 `project_directory(slug)` = `/workspace/<slug>`。按用户要求加接口参数：`GET /api/agent/session/{sid}` 响应新增 **`directory`** 字段（`workdir_for_session`）。前端 workbench 新增 `useSessionWorkdir`（key `["session-workdir", userId, sessionId]`，staleTime 5min），`FilesTab` 以它为树根；detail 未返回前不渲染树（避免先闪整个 /workspace 再跳回项目）。无会话时（/app）回退 /workspace。

**③ 面包屑显示乱码（容器 ID）。** `FilesTab` 头部原来渲染 `running.name ›` —— 沙箱容器的随机名（`ecd-330zd5…`）。改为项目目录名（`default ›`）。`FilesTree` 面包屑同步收敛：首个 crumb 是项目根目录本身，**浏览永远爬不到项目之上**；打开项目外的文件（如 /workspace/uploads 的附件）时回退为该路径自身的 crumbs，仅保该处可导航。

**④ 新建对话丢失左侧项目选择/展开态。** 根因：顶部「新对话」按钮 `navigate("/app")` 把 `?project=` 参数丢了 → 首条消息建会话时 `project_id=null`；且 `expanded` 只在内存，刷新即失。修复：

- `useWorkspaceUi` 新增 **`selectedProject`**，与 `expanded` 一起**持久化**到 localStorage；
- 选中时机：点项目行（chevron/名称）、点会话行（其所属项目）、项目内「+」/菜单新建；选中项目名旁有强调色小圆点；
- 顶部「新对话」带上 `?project=<selected>`（选中项目已删除时校验回退）；删除项目时清掉指向它的选择；
- 树的展开/选中状态经过新建对话、发送首条消息、整页刷新均不变。

**顺带修复**：后端建会话的兜底标题是 `New session - <裸 ISO 时间戳>`，直接漏进侧栏显示。改为空串（前端本有本地化的「未命名对话」兜底，标题生成器随后补上）；`loop.py` 的标题生成条件同步改为「空或 legacy 前缀」；存量 3 条脏标题已清。

> 排查手法：Playwright `page.on("websocket")` 抓 WS 帧 + 每 2s 采样 `main` innerText,把「空白」翻译成「哪个时间段缺了哪类事件」;对代理**直接 curl 三种参数形状**比翻 LiteLLM 文档快得多。

E2E：`sidebar-project.spec.ts`（选择→新建对话→URL 带 project→POST body 校验→刷新后状态仍在）；`workbench.spec.ts` files 用例改为「任选会话 → 树根不是 workspace、头部无容器 ID、首个文件可打开」。

**补充（同日）**：面板菜单页的提示列原样渲染 `running.name` —— 当前部署下即无影云桌面 ID `ecd-…`（`SANDBOX_PROVIDER=wuying`，经 SSH 隧道接入）。机器 ID 对用户无意义：终端行改示「沙箱在线」（新增 `menu.online` 双语键），文件行示项目目录名（`useSessionWorkdir`），E2E 断言面板不得出现 `ecd-` 形态的 ID。

### D.4.8 云桌面标签（2026-08-21）

右侧面板新增第五个标签 **云桌面**：打开即流式进入沙箱所在的无影云桌面。对接方式抄自 workspace 中 bossip 项目（`apps/codex/v1/src/server/wuying.js` + `cloud-desktop.js`）的既有集成：

**链路**：`GET /api/desktop/ticket`（登录态）→ 后端用 ECD OpenAPI `GetConnectionTicket` 取一次性连接票据 → 前端把票据交给阿里 **WuyingWebSDK**（g.alicdn.com CDN 版 2.12.5-asp3.18.7），`createSession({openType:"inline", iframeId, userInfo:{ticket}, …})` 渲染进 iframe，1920×1080 远端画面按面板尺寸等比缩放。

**后端**（`api/desktop.py`，新增 `alibabacloud_ecd20200930` 依赖）：
- `GetConnectionTicket` 是**异步任务**：桌面上还没有该 end user 会话时首次调用只回 `taskId`+RUNNING，须携带 taskId 轮询到 FINISHED 才有票。请求内轮询预算 14s，超预算回 **202 + {taskId}**（带 Retry-After），前端携 taskId 重试 —— 与 bossip 的 202 通道一致；瞬时网络抖动在预算内按 RUNNING 续轮。
- 凭证链：`ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET` env → **aliyun CLI** profile（`~/.aliyun/config.json`，本机已配置且验证可用）。
- 配置新增 `WUYING_REGION_ID`（cn-hangzhou）、`WUYING_END_USER_ID`（本桌面的 end user，经 `aliyun ecd describe-desktops` 查得）。桌面/区域信息只进 SDK 连接载荷，**永不进 UI 文案**。
- 非 wuying provider 或缺配置 → 503 `{available:false, reason}`。

**前端**（`DesktopTab.tsx`，TabKind `desktop`，glyph `▣`）：
- 状态机 loading / connected / closed / error；连接后默认**只读观看**（agent 正在桌面里干活，抢鼠标须显式勾选「允许操控」，经 `enableInput/setInputEnabled/setTouchEnabled` 尽力生效）；断开/失败有重连按钮。
- SDK 脚本模块级单例加载；卸载时 `stop()/stopConnection()`；`ResizeObserver`+`MutationObserver` 维持等比缩放。
- 实测：真实 Ubuntu 桌面画面在面板内流式渲染成功（只读横幅 + 操控开关，零 ID 露出）。

E2E stub 掉票据接口（真流需要云凭证）：断言菜单行存在、错误态渲染、重连按钮、面板 DOM 不得出现 `ecd-` 形态 ID。

**工具条补全（同日）**：全屏观看 / 剪贴板同步 / 上传文件。SDK 方法名不靠猜 —— 直接下载 CDN bundle grep 确认：`setClipboardEnabled(bool)`、`uploadFile(file, showDialog)`、`enableInput/setInputEnabled/setTouchEnabled`。

- **全屏**：对整个 tab 根容器（含工具条）`requestFullscreen()`，被拒或不可用时降级为 `fixed inset-0 z-50` 覆盖层（Esc 可退）；`fullscreenchange` 兜底复位。缩放交给已有的 ResizeObserver，无需专门处理。
- **剪贴板同步**：连接时默认开（`setClipboardEnabled(true)`），工具条 checkbox 可关；iframe 早已带 `allow="clipboard-read; clipboard-write"`。
- **上传文件**：隐藏 `<input type=file>` → `session.uploadFile(file, true)`，`showDialog=true` 让远端桌面弹自己的进度 UI，本端无需再造。
- 重连语义：连接建立时从 `togglesRef` 应用当前开关状态（React 编译器规则禁止 render 期写 ref，镜像放在 effect 里）。

### D.4.9 附件走 OSS 直传（2026-08-21）

原链路的带宽问题：附件以 base64 分块经后端 `/execute` 灌进沙箱 —— 每个字节都挤 SSH 隧道，大文件不可用。新链路**字节永远不过后端**：

```
浏览器 ──presigned PUT──▶ OSS(openbox-assets-hz01, cn-hangzhou)
                             │
无影桌面 ◀──obx-file get──────┘   （阿里内网，快；隧道零流量）
```

**后端**：
- `file_assets` 表（Alembic `e5b7c9d1f3a6`）：上传台账 —— user/session、原名、OSS key、mime、size、pending→ready。字节不过后端，但**记录必须在库里**。
- `core/oss.py`：手写 V1 预签名（HMAC-SHA1 query 签名，bossip 同款 ~40 行，不引 SDK）。**关键坑（bossip 实测传承）**：string-to-sign 的 Content-Type 行必须与客户端实发严格一致 —— PUT 按申报 mime 签，浏览器必须原样发这个头；GET/HEAD 签空行。`core/aliyun.py` 抽出共享凭证链（env → aliyun CLI profile），desktop.py 同步复用。
- `api/assets.py`：`POST /api/assets`（建 pending 记录 + presigned PUT + 必发 headers）→ 浏览器直传 → `POST /{id}/complete`（HEAD 验对象真的落了，转 ready）→ `GET /{id}/url`（预览用新鲜 GET，可带 download disposition）。未配 OSS 时 503，前端自动回退旧链路。
- **`obx-file`** —— 用户要的"系统级 grep 式"终端工具：`sandbox/assets.py` 在沙箱装入 `/usr/local/bin`（sudo -n，退化 ~/.local/bin），`obx-file get <url> <dest>` / `obx-file put <src> <url>`（put 走空 CT 签名 + `-H 'Content-Type:'`），agent 可在终端手动使用。
- Prompt 链路：`PromptBody.attachments`（asset ids）→ 后台任务在 **run_loop 之前** `deliver()` 拉进 `/workspace/uploads/`（顺序保证：消息文本引用的路径 agent 一定能读到；单文件失败仅告警不炸整轮）→ 同时给用户消息挂 `FilePart{path, mime_type, asset_id, size}`。

**前端**：
- `useAttachments` 重写：OSS 优先（XHR 直传带真实进度百分比），`ApiError 503` 自动回退旧沙箱上传；图片附件在 composer 条里显示 objectURL 缩略图。
- 发送管线全程带 `attachments`：Composer → 两条路由 → useSendChat/useStartChat → prompt body。
- 聊天卡片 `AttachmentCard`：图片 → presigned GET 缩略图（`useAssetUrl`，staleTime 40min < 1h 过期）；其他 → 图标+名+大小卡；点击换新鲜下载 URL 打开。消息模型优先渲染 file parts，老消息回退 `[attachments]` 文本尾巴；顺带修掉「纯附件无文本消息不渲染」。

**桶开通**（aliyun CLI）：`aliyun oss mb` 建 `openbox-assets-hz01` + CORS（PUT/GET/HEAD、AllowedHeader *、expose ETag）。配置 `OSS_BUCKET/OSS_REGION/OSS_ENDPOINT`。

**实测端到端**：真 PNG 经 UI 直传 OSS（网络面板确认 PUT 打 `openbox-assets-hz01.oss-cn-hangzhou.aliyuncs.com`）→ 聊天卡片渲染 OSS 预览 → 桌面 `/workspace/uploads/e2e-pic.png` 2721 字节 magic 头正确。E2E `attachments.spec.ts` 内置生成 PNG 打真实栈；注意 send 门在上传完成（%→大小）后才开。

### D.4.10 多模态视觉 + 停止按钮（2026-08-21）

**多模态：模型在后端,必须让它看到像素。** 两条通路,都经 OSS,不挤隧道：

- **用户上传的图片**：`_to_llm_messages` 给用户消息的图片 FilePart 生成新鲜 presigned GET（key 确定性 `assets/{user}/{asset}/{name}`，零 DB 查询；URL 会过期所以**每次 LLM 调用重签**）。URL 挂在消息的 `_images` 带外字段 —— reminder/缓存/token 计数各 pass 继续处理纯字符串，`_finalize_message` 在 litellm 调用前的最后一刻转成 OpenAI 式 content 数组（Responses API 路径转 `input_image`）。**实测**：纯橙色 PNG 上传后问颜色，gemini 答「橙色」。
- **sandbox 产出的图片**：新工具 **`view_image`** —— 沙箱里 `file --mime-type` 嗅探 + 10MB 上限 → `obx-file put`（带 mime 的签名直传 OSS，obx-file 升级支持第三参 content-type）→ 落 `file_assets` 台账 → assistant 消息挂 FilePart（前端渲染预览卡）→ 消息装配时在 tool result 后追加 `_synthetic` user 消息携带图片（tool 角色消息不是处处能带图，user 消息全 API 合法）。**坑**：agent 工具是显式白名单（`AGENTS[...].tools`），注册进 registry 不等于模型能看到 —— 四个 agent 的白名单都要加。**实测**：agent 调 view_image 看沙箱里的橙色图，下一轮答「橙色」，聊天里出现图片卡。

**停止按钮不生效 —— 根因与 opencode 的差距。** opencode 的 abort 是 AbortSignal **直接取消在途请求**；我们是 `async for event: if abort.is_set(): break` —— 只在 **chunk 边界**检查。模型静默攒大工具调用的 10–30 秒里没有 chunk,break 永远走不到,停止形同虚设。三处修复：

| 修复 | 内容 |
|---|---|
| `_iter_until_abort` | 每次 `__anext__` 与 `abort.wait()` 赛跑；abort 到来即 cancel + `stream.aclose()`（撕掉 provider HTTP 流，opencode 语义） |
| 工具执行赛跑 | `hooks.wrap_execute` 包 task 与 abort 并发等待；长 bash 不再扛住停止按钮，弃单由 loop 的 ABORTED_TOOL_ERROR 清理收尾 |
| **per-run signal** | 原来 per-session 复用 Event：旧 run 已 set 的事件会误杀新 run（prompt_async 的 sleep(0.3) 只是缓解）。改为 opencode 式**每 run 一个新 signal**（`register_run` 覆盖槽位，`clear_abort(sid, signal)` 只清自己的），`trigger_abort` 打到最新 run；并修掉「loop 注册前按停被吞」的竞态 |

**实测**：流式输出中途按停,后续 **0 字符增长**、按钮即时回空闲(修复前 litellm 流会跑完)。E2E `stop.spec.ts`：发出后固定 2s 按停(几乎必然处于生成期,常为静默期 —— 正是回归场景)；等内容流出再点会赶上快答案跑完、按钮消失的时序。

### D.4.11 浏览器双模式:云端 CDP + 远程扩展（2026-08-21）

**背景判断。** 调研后确认 `container/dev-browser` 不是 fork —— 它是自研的 **CDP relay**:把 Chrome 扩展伪装成一个 CDP 端点（监听 9222,暴露 `/cdp` 给 Playwright、`/extension` 给扩展,自己实现了 `Target.attachToTarget` 等命令转发）。这个设计押对了方向:Chrome 136+ 封了默认 profile 下的 `--remote-debugging-port` 且每次连接弹确认框,而扩展路线绕开了它,还能**保住用户真实登录态**。

但它只解决了「操控用户自己电脑的浏览器」,没解决「操控无影云桌面的浏览器」——所以 agent 在云上开浏览器只能用 `computer` 一张张截图点。

**本轮实现两种模式并存:**

| 模式 | 驱动的浏览器 | 链路 | 有用户登录态 |
|---|---|---|---|
| `local` | 云桌面自己的 Chrome | Playwright → **Chrome 原生 CDP**（零 relay 跳） | 否 |
| `remote` | 用户自己的 Chrome | Playwright → relay `/cdp` → 扩展 WS → 后端 → 隧道 | **是** |
| `auto`（默认） | 优先远程,**掉线自动回落 local** | — | 视实际而定 |

**关键设计决策:云端不装插件,直接裸 CDP。** Chrome 137+ 封杀了 `--load-extension`,企业策略装 CRX 太重;而云桌面本来就没有「用户登录态」需要保护,插件在这条路上纯是负担。local 模式下 relay 只做**页面命名簿**（name→targetId,经 Chrome 的 `/json/*` HTTP 接口）,`wsEndpoint` 直接返回 Chrome 自己的 `webSocketDebuggerUrl` —— **Playwright 直连 Chrome,relay 不在数据面上**。这正是「走 CDP」要的性能形态。

云端 Chrome 用**独立 profile** `~/.config/obx-chrome` 启动:Chrome 136+ 拒绝在默认 profile 上开远程调试,独立 profile 是唯一可行解,而这里恰好没有登录态损失。

**回落是产品要求,不是异常处理。** `ensure_browser()` 在 remote/auto 下发现扩展未连接时,主动拉起云端 Chrome 并把 relay 切到 local,**不抛错** —— 用户关掉浏览器不该让任务死掉。只有两条路都失败才报错。

**模式选择落到配置。** 偏好存在既有的 `UserPreference.extra["browser_mode"]`（不新建表),`session/browser_pref.py` 是唯一读写口。注意**词汇分裂**:产品说 `remote`,relay 内部叫 `extension`,`relay_mode()` 是唯一翻译点,两套名字不互相泄漏。

三条落地路径:
- 设置页 UI（`GET/PUT /api/browser/preference`）
- **AI 提问后写回配置**:新增 `browser_mode` 工具（`get`/`set`）。它跑在后端,能直接读写偏好 —— 当任务需要用户身份而当前是云端浏览器时,agent 用 `question` 问,再用 `set` 记下来,下次不用重问
- 技能加载时注入 `<browser_mode>` 块,告诉模型**实际**跑在哪个浏览器上、以及是否发生了回落

**顺带补上系统提示的缺口:** 之前 `computer` 工具没进「web_search → web_fetch → dev-browser」这个阶梯,模型会拿它去干浏览器的活（实际发生过:agent 用 6 次截图点开百度）。现在明确:页面内的事一律走 dev-browser（结构化读取,token 少一个数量级,点的是元素不是猜的像素）,`computer` 只负责页面之外——原生应用、系统对话框,以及 canvas 这类结构表达不了的东西。

### D.5 E2E 约定

- 后端登录限流 5 次/分钟/IP → E2E 采用 **setup project + storageState**：一次真实表单登录（本身即登录用例），其余 spec 复用 refresh cookie 恢复会话；`workers: 1` 串行。
- 无 headless-shell 网络下载依赖：`channel: "chromium"` 用完整浏览器跑新无头模式。
- 已覆盖：落地页访客视角、密码登录、发消息→WS 流式回复、语言切换全界面、主题切换+服务端回灌+还原、文件面板（真实沙箱树+内容预览）。

### D.6 工程结论

- `shared/api` 允许平台资源客户端（auth-store、containers、http、ws），修订反模式 12。
- 跨特性联动（聊天「审阅」→ 打开工作面板）走 `shared/events/bus.ts` 应用内事件，不做特性横向 import。
- 流式消息 store（chat 特性）与 Query 缓存物理隔离；初始快照走 Query，增量走 WS（§7.4 落地形态）。

---
