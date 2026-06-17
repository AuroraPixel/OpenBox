# GKE 实现复盘

更新时间：2026-03-06

## 当前模型

- 当前 sandbox 模型已经统一为：每个用户一个 Docker container，或在 Kubernetes 下每个用户一个 Pod。
- `project_id` 不参与 sandbox 身份；它仍可用于业务层会话和项目数据，但不决定容器、Pod、Service 或 PVC 的命名与复用。
- 同一用户的不同 session 会复用同一个 sandbox，只在容器内使用各自的 `/workspace/sessions/{session_id}` 工作目录。

## 代码实现状态

- 代码层实现已经基本完成，主干能力已经具备。
- Docker 和 Kubernetes provider 都已经按用户级命名和复用。
- `backup` / `restore` 已接入 GCS 参数传递，备份前缀示例也已统一为 `users/{user_id}/workspace/`。
- 当前最主要的剩余风险不是代码结构，而是真实 GKE 环境中的集成验证。

## 已修复的关键项

- 合并冲突已清理。
- container 相关路由已补齐鉴权和所有权校验。
- provider 已改为懒加载，减少导入副作用。
- GCS 备份/恢复链路已接通。
- Docker / Kubernetes 资源命名已统一到用户级。
- `backend/pyproject.toml` 中重复 `blob` 声明问题已修复。
- 相关单元测试已通过。
- `main.py` 多用户基础设施初始化、优雅关闭、路由注册已恢复。
- `containers.py` preview_router、preview-token、配额检查、admin/all 端点已恢复。
- `build_sandbox_image` API 方法已恢复为 POST。
- `action_server.py` backup/restore 改为同步 def 避免阻塞事件循环。
- K8s sandbox Pod 已支持 ServiceAccount（Workload Identity / GCS）。
- `reconcile()` 已补充 Service 存在性保障。
- GKE Ingress 已添加 BackendConfig 支持 WebSocket 长连接。
- `sandbox-pod-template.yaml` 已与代码同步（labels、selector、SA）。

## 主要剩余风险

- 仍需在真实 GKE 中验证 Pod 创建、重启、恢复和删除流程。
- 仍需验证 PVC 持久化、GCS 备份恢复、Ingress 路由、以及 Workload Identity 权限配置是否完整可用。

## 验证命令

`uv run --project backend --extra test pytest backend/tests/unit/test_config.py backend/tests/unit/test_sandbox_manager.py -q`

## 结论

当前最准确的状态表述是：代码级实现基本就绪，sandbox 身份模型已经统一为"每用户一个实例"，剩余重点是完成真实 GKE 集成验证。
