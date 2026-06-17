---
name: gke-full-deploy
description: Full GKE deployment of OpenBox from scratch. Use when setting up a new GKE cluster, doing a fresh deployment, or migrating OpenBox to a new environment.
---

# GKE 全新部署

从零将 OpenBox 部署到 GKE 集群的完整流程。

## 架构概览

```
同一个 GKE 集群
├── Namespace: openbox              ← 应用层
│   ├── Backend Deployment (FastAPI)
│   ├── Frontend Deployment (Nginx)
│   ├── Ingress (对外入口 + HTTPS)
│   └── Secret (凭证)
└── Namespace: openbox-sandbox      ← 沙箱层
    ├── Pod sandbox-{user_id}       ← 动态创建
    ├── Service sandbox-{user_id}
    └── PVC workspace-{user_id}     ← 持久化存储
```

## 前置条件

- [ ] `gcloud` CLI 已安装并认证
- [ ] `kubectl` 已安装
- [ ] Docker 已安装
- [ ] 拥有域名 DNS 管理权限
- [ ] 准备好以下凭证（不要写入代码或 skill）：
  - PostgreSQL 连接串
  - Redis URL（密码中特殊字符需 URL 编码）
  - Blob Storage 连接串
  - JWT Secret
  - LLM API Key
  - Search API Key（如 Tavily）

## 部署步骤

### Step 1: 创建 GKE 集群

```bash
gcloud container clusters create <CLUSTER_NAME> \
  --region=<REGION> \
  --num-nodes=1 \
  --machine-type=e2-standard-2 \
  --disk-size=50 \
  --workload-pool=<PROJECT_ID>.svc.id.goog \
  --enable-ip-alias \
  --release-channel=regular \
  --project=<PROJECT_ID>
```

验证连接：`kubectl get nodes`

### Step 2: 创建 Namespace

```bash
kubectl create namespace openbox
kubectl create namespace openbox-sandbox
```

### Step 3: 创建 PostgreSQL 数据库

如果数据库在 GKE 内网，通过集群内 Pod 连接：

```bash
kubectl run pg-client --rm -i --tty --restart=Never --namespace=openbox \
  --image=postgres:16-alpine \
  --command -- psql "<POSTGRES_URL>" -c "CREATE DATABASE openbox;"
```

### Step 4: 构建并推送 Docker 镜像

**必须使用 `--platform linux/amd64`**（GKE 节点是 amd64）。

```bash
gcloud auth configure-docker gcr.io --quiet

# 三个镜像并行构建
docker build --platform linux/amd64 -t gcr.io/<PROJECT_ID>/openbox-sandbox:latest ./container
docker build --platform linux/amd64 -t gcr.io/<PROJECT_ID>/openbox-backend:latest ./backend
docker build --platform linux/amd64 -t gcr.io/<PROJECT_ID>/openbox-frontend:latest ./frontend

# 推送
docker push gcr.io/<PROJECT_ID>/openbox-sandbox:latest
docker push gcr.io/<PROJECT_ID>/openbox-backend:latest
docker push gcr.io/<PROJECT_ID>/openbox-frontend:latest
```

### Step 5: 创建 K8s Secret

**重要**：Redis 密码中的特殊字符 `!@#$%` 等必须 URL 编码。

```bash
kubectl create secret generic openbox-secrets -n openbox \
  --from-literal=DATABASE_URL='<ASYNCPG_URL>' \
  --from-literal=REDIS_URL='<REDIS_URL_ENCODED>' \
  --from-literal=JWT_SECRET='<JWT_SECRET>' \
  --from-literal=SANDBOX_IMAGE='gcr.io/<PROJECT_ID>/openbox-sandbox:latest' \
  --from-literal=OPENBOX_API_KEY='<API_KEY>' \
  --from-literal=BLOB_AZURE_CONNECTION_STRING='<BLOB_CONN>' \
  --from-literal=BLOB_AZURE_CONTAINER='<CONTAINER_NAME>' \
  --from-literal=TAVILY_API_KEY='<TAVILY_KEY>' \
  --from-literal=OPENAI_API_KEY='<OPENAI_KEY>'
```

### Step 6: 创建镜像拉取凭证

```bash
ACCESS_TOKEN=$(gcloud auth print-access-token)
for NS in openbox openbox-sandbox; do
  kubectl create secret docker-registry gcr-pull-secret -n $NS \
    --docker-server=gcr.io --docker-username=oauth2accesstoken \
    --docker-password="$ACCESS_TOKEN" --docker-email=<EMAIL>
done

# 绑定到 ServiceAccount
kubectl patch serviceaccount default -n openbox \
  -p '{"imagePullSecrets": [{"name": "gcr-pull-secret"}]}'
```

### Step 7: 部署 K8s 资源

`k8s/base.yaml` 包含所有资源定义。部署前需：

1. 确认 `BLOB_PROVIDER` 值（azure 或 gcs）
2. 确认环境变量与 Secret key 匹配

```bash
sed "s/PROJECT_ID/<PROJECT_ID>/g" k8s/base.yaml | kubectl apply -f -
```

部署后绑定 imagePullSecret 到创建的 ServiceAccount：

```bash
kubectl patch serviceaccount openbox-backend -n openbox \
  -p '{"imagePullSecrets": [{"name": "gcr-pull-secret"}]}'
kubectl patch serviceaccount sandbox-pods -n openbox-sandbox \
  -p '{"imagePullSecrets": [{"name": "gcr-pull-secret"}]}'
```

### Step 8: 运行数据库 Migration

```bash
kubectl exec -n openbox deployment/openbox-backend -- uv run alembic upgrade head
```

**注意**：检查 migration 中的列长度是否与 ORM 模型一致（常见问题：`VARCHAR(26)` vs `String(64)`）。如不一致需手动 ALTER。

### Step 9: 配置外部访问（Ingress + HTTPS）

#### 预留静态 IP

```bash
gcloud compute addresses create <APP>-static-ip --global --project=<PROJECT_ID>
gcloud compute addresses describe <APP>-static-ip --global --format='get(address)'
```

#### 创建 ManagedCertificate + Ingress

参考 `.claude/gke-ingress-setup/SKILL.md` 中的完整流程。关键资源：

- ManagedCertificate（域名 SSL 证书，签发需 15-60 分钟）
- FrontendConfig（HTTP → HTTPS 跳转）
- Ingress（路由规则：`/api` `/ws` → backend，`/` → frontend）

#### 配置 DNS

在域名管理后台添加 A 记录：`<DOMAIN> → <STATIC_IP>`

### Step 10: 验证

```bash
# Pod 状态
kubectl get pods -n openbox

# 健康检查
curl -s https://<DOMAIN>/health

# 证书状态
kubectl get managedcertificate -n openbox

# Backend 日志
kubectl logs -f deployment/openbox-backend -n openbox
```

## 凭证管理

部署完成后，将所有凭证保存到本地文件（如 `gke-credentials.md`），并加入 `.gitignore`：

```bash
echo "gke-credentials.md" >> .gitignore
```

## 关键注意事项

### Redis URL 编码
密码中的 `!@#$%` 必须 URL 编码，否则 URL 解析器会把 `@` 当作主机分隔符。

### 交叉编译 .venv 问题
在 ARM Mac 上用 `--platform linux/amd64` 构建时，`uv sync` 创建的 `.venv` 在 amd64 容器中不可用。Backend Dockerfile 应使用 `pip install` 而非 `uv sync`。

### Sandbox Pod 权限
Sandbox Pod 默认以 root 运行。如需限制权限，在 `kubernetes.py` 的 pod spec 中添加 `securityContext`，并确保 PVC 目录权限正确（通过 `fsGroup` 或 `initContainer`）。

### imagePullSecret 过期
使用 `gcloud auth print-access-token` 生成的 token 约 1 小时过期。每次部署前需刷新。长期方案是配置 Workload Identity（需要 `iam.serviceAccountAdmin` 权限）。

### 集群费用
GKE Standard 集群管理费免费，按节点 VM 计费。3 个 `e2-standard-2` 节点约 $145/月。不用时记得删除集群。
