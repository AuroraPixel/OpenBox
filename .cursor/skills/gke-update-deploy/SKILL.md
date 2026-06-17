---
name: gke-update-deploy
description: Update and redeploy OpenBox to GKE after code changes. Use when the user wants to deploy updates, push new images, restart pods, or apply config changes to the running GKE cluster.
---

# GKE 更新部署

代码变更后，将 OpenBox 更新部署到 GKE 集群。

## 前置条件

- kubectl 已连接到 openbox 集群
- gcloud 已认证
- Docker 已登录 GCR（`gcloud auth configure-docker gcr.io --quiet`）

## 连接集群

```bash
gcloud container clusters get-credentials openbox --region=us-central1 --project=<PROJECT_ID>
```

## 更新流程

### 1. 判断需要更新的组件

| 变更内容 | 需要重建的镜像 |
|---------|--------------|
| `backend/` 代码变更 | openbox-backend |
| `frontend/` 代码变更 | openbox-frontend |
| `container/` 代码变更 | openbox-sandbox |
| `k8s/base.yaml` 变更 | 无需重建镜像，直接 apply |
| K8s Secret 变更 | 无需重建镜像，更新 secret 后 restart |

### 2. 重建并推送镜像

**注意**：必须使用 `--platform linux/amd64`，因为 GKE 节点是 amd64。

```bash
cd <项目根目录>

# Backend
docker build --platform linux/amd64 -t gcr.io/<PROJECT_ID>/openbox-backend:latest ./backend
docker push gcr.io/<PROJECT_ID>/openbox-backend:latest

# Frontend
docker build --platform linux/amd64 -t gcr.io/<PROJECT_ID>/openbox-frontend:latest ./frontend
docker push gcr.io/<PROJECT_ID>/openbox-frontend:latest

# Sandbox（仅 container/ 目录变更时）
docker build --platform linux/amd64 -t gcr.io/<PROJECT_ID>/openbox-sandbox:latest ./container
docker push gcr.io/<PROJECT_ID>/openbox-sandbox:latest
```

### 3. 刷新镜像拉取凭证

imagePullSecret 使用临时 token，约 1 小时过期，部署前必须刷新：

```bash
ACCESS_TOKEN=$(gcloud auth print-access-token)
for NS in openbox openbox-sandbox; do
  kubectl delete secret gcr-pull-secret -n $NS 2>/dev/null
  kubectl create secret docker-registry gcr-pull-secret -n $NS \
    --docker-server=gcr.io --docker-username=oauth2accesstoken \
    --docker-password="$ACCESS_TOKEN" --docker-email=<EMAIL>
done
```

### 4. 重启 Deployment

```bash
# 重启 backend（推完 backend 镜像后）
kubectl rollout restart deployment openbox-backend -n openbox

# 重启 frontend（推完 frontend 镜像后）
kubectl rollout restart deployment openbox-frontend -n openbox
```

Sandbox Pod 不需要手动重启，下次用户创建会话时自动使用新镜像。如需立即更新现有 sandbox：

```bash
kubectl delete pods -n openbox-sandbox --all
```

### 5. 应用 K8s 配置变更

```bash
sed "s/PROJECT_ID/<PROJECT_ID>/g" k8s/base.yaml | kubectl apply -f -
```

### 6. 运行数据库 Migration（如有）

```bash
kubectl exec -n openbox deployment/openbox-backend -- uv run alembic upgrade head
```

### 7. 验证

```bash
# Pod 状态
kubectl get pods -n openbox
kubectl get pods -n openbox-sandbox

# Backend 日志
kubectl logs deployment/openbox-backend -n openbox --tail=20

# 健康检查
curl -s https://<DOMAIN>/health
```

## 常见问题

### ImagePullBackOff
imagePullSecret 过期，执行 Step 3 刷新。

### Pod 启动慢
检查 Dockerfile CMD 是否使用了 `uv run`（会重建 venv）。应使用 `pip install` + 直接调用 `uvicorn`。

### 前端 TypeScript 编译失败
先本地 `cd frontend && npx tsc --noEmit` 检查错误，修复后再构建镜像。

### 数据库字段长度不匹配
ORM 模型和数据库 migration 列长度需一致，检查是否需要 ALTER TABLE。
