GKE 改造完整设计方案
一、总体架构
                    Internet
                       │
                       ▼
                   GKE Ingress
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
   Frontend Deployment        Backend Deployment
   (Nginx, 静态资源)           (FastAPI, 1 副本)
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
               Cloud SQL      Memorystore     openbox-sandbox
              (PostgreSQL)     (Redis)         namespace
               (已有)          (已有)              │
                                          ┌───────┼───────┐
                                          ▼       ▼       ▼
                                       Pod A   Pod B   Pod C
                                      (alice)  (bob)  (carol)
                                       + PVC    + PVC   + PVC
切换方式：SANDBOX_PROVIDER=docker|kubernetes 环境变量

二、文件变更清单
新增文件（7 个）
文件	用途	预估行数
backend/sandbox/provider.py	SandboxProvider 抽象接口	~60
backend/sandbox/kubernetes.py	KubernetesProvider 实现	~350
backend/blob/__init__.py	Blob 包初始化	~0
backend/blob/interfaces.py	IBlobStorage 抽象接口	~25
backend/blob/gcs_blob.py	GCS Blob 存储实现（同 IBlobStorage 接口）	~80
k8s/base.yaml	K8s 部署清单（Namespace + RBAC + Backend/Frontend Deployment + Ingress）	~200
k8s/sandbox-pod-template.yaml	沙箱 Pod 模板（参考用，实际由代码创建）	~80
修改文件（8 个）
文件	改动内容	预估改动量
backend/sandbox/__init__.py	根据配置选择 Provider（provider 变量）	~15 行
backend/models/container.py	ContainerInfo 加 host 字段	~1 行
backend/core/config.py	新增 GKE 相关配置项 + 环境变量映射	~30 行
backend/main.py	启动逻辑适配（cleanup_all → reconcile），使用 provider 替代 docker_manager	~10 行
backend/sandbox/manager.py	docker_manager 引用改为 provider，SandboxInfo 加 host 字段，localhost 替换	~30 行
backend/sandbox/docker.py	加 SandboxProvider 继承声明 + host 字段 + supports_build + reconcile 方法 + user_id 参数	~15 行
backend/api/containers.py	docker_manager → provider（全部引用），localhost → host（1 处），build 加 supports_build 判断	~15 行
backend/api/terminal.py	docker_manager → provider（1 处），localhost → host（1 处）	~5 行
backend/api/files.py	docker_manager → provider（2 处）	~3 行
container/action_server.py	新增 /backup /restore 端点	~120 行
backend/pyproject.toml	新增 kubernetes, google-cloud-storage 依赖	~2 行
container/requirements.txt	新增 google-cloud-storage 依赖	~1 行
backend/.env.example	新增 GKE 相关环境变量注释	~10 行
不改的文件
backend/sandbox/client.py — 已参数化 host:port，零改动
frontend/ — 全部不改
三、各模块详细设计
3.1 backend/sandbox/provider.py — 抽象接口
定义 SandboxProvider 抽象基类，统一 Docker 和 K8s 的操作接口：

class SandboxProvider(ABC):
    方法:
    - create_container(name, image, project_id, user_id) → ContainerInfo
    - delete_container(container_id, user_id) → None
    - start_container(container_id, user_id) → None
    - stop_container(container_id, user_id) → None
    - get_container(container_id, user_id) → ContainerInfo
    - list_containers() → list[ContainerInfo]
    - forward_to_container(container_id, method, path, **kwargs) → Response
    - reconcile() → None
    - cleanup_all() → None
    属性:
    - supports_build: bool  (Docker=True, K8s=False)
    可选方法（Docker 才有实现）:
    - image_exists(image) → bool
    - build_sandbox_image() → AsyncGenerator[dict, None]
    内部状态（两个 Provider 都需要）:
    - _containers: dict[str, ContainerInfo]
    - _api_keys: dict[str, str]
3.2 backend/sandbox/docker.py — Docker Provider 改造
最小改动：

class DockerManager(SandboxProvider): — 加继承
ContainerInfo 创建时加 host="localhost" — 所有现有逻辑不变
加 supports_build = True 属性
加 reconcile() 方法（等同于 cleanup_all）
方法签名加 user_id 参数（兼容接口，Docker 模式不使用）
forward_to_container 中 localhost 改为 info.host
_wait_until_ready 加 host 参数

3.3 backend/sandbox/kubernetes.py — K8s Provider
依赖：kubernetes Python SDK（pip install kubernetes）

核心逻辑：

class KubernetesProvider(SandboxProvider):
    __init__:
      - 加载 K8s 配置（in-cluster 自动，本地 fallback kube_config）
      - 创建 CoreV1Api 客户端
      - namespace 从配置读取，默认 "openbox-sandbox"
      - supports_build = False
      - 额外状态: _container_owners, _container_projects
    create_container(name, image, project_id, user_id):
      约束: 每个 user_id 只保留一个沙箱实例，也就是一个用户只对应一个 Pod；project_id 不参与 Pod/Service/PVC 身份
      1. 检查该用户是否已有 Pod（pod_name = sandbox-{safe_user_id}，同一用户始终复用这一套资源）
      2. 如果有且 Running，直接返回
      3. 创建 PVC（如果不存在）:
         - 名称: workspace-{safe_user_id}
         - 大小: 从配置读取，默认 10Gi
         - storageClassName: 从配置读取，默认 standard-rwo
      4. 创建 Pod:
         - 名称: sandbox-{safe_user_id}
         - Labels: app=openbox-sandbox, openbox.dev/user-id
         - 容器镜像: 从配置读取
         - 环境变量: SESSION_API_KEY=随机生成
         - Volume Mounts:
           * PVC → /workspace
           * emptyDir(Memory, 256Mi) → /dev/shm  (Playwright)
           * emptyDir → /data
         - Resources:
           * requests: cpu=250m, memory=256Mi
           * limits: cpu=1000m, memory=1Gi
         - SecurityContext: runAsUser=1000 (sandbox用户)
      5. 创建 Service:
         - 名称: sandbox-{safe_user_id}
         - type: ClusterIP
         - port: 8000 → 8000
         - selector: 匹配 Pod labels
      6. 等待 Pod Ready（轮询 Pod status.phase == Running + Ready condition）
      7. 构造 ContainerInfo:
         - host = "sandbox-{safe_user_id}.{namespace}.svc.cluster.local"
         - port = 8000 (固定)
         - api_key = 生成的 key
      8. 等待 Action Server /alive 就绪
      9. 触发数据恢复（如有 GCS 归档）:
         POST http://{host}:8000/restore
      10. 返回 ContainerInfo
    delete_container(container_id, user_id):
      1. 触发数据备份:
         POST http://{host}:8000/backup
      2. 删除 Pod
      3. 删除 Service
      4. PVC 不删（保留数据）
      5. 清理内存状态
    stop_container:
      - 触发备份
      - 删除 Pod，保留 Service 和 PVC
      - 标记状态为 STOPPED
    start_container:
      - 重新创建 Pod（通过 create_container）
      - 等待 Ready
    reconcile():
      1. list_namespaced_pod(namespace, label_selector="app=openbox-sandbox")
      2. 每个 Pod → 恢复到 _containers / _container_owners
      3. 从 Pod env 恢复 api_key
      4. 标记 Running/Stopped 状态
    forward_to_container(container_id, method, path, ...):
      - info = _containers[container_id]
      - url = f"http://{info.host}:{info.port}{path}"
      - httpx 请求转发
    cleanup_all():
      - GKE 模式下不杀 Pod
      - 只清理内存状态
3.4 backend/sandbox/__init__.py — Provider 选择
逻辑:
  读取 config.sandbox_provider
  如果 == "kubernetes":
    from sandbox.kubernetes import KubernetesProvider
    provider = KubernetesProvider()
  否则:
    from sandbox.docker import DockerManager
    provider = DockerManager()
  对外暴露:
    provider  (替代原来的 docker_manager)
    sandbox_manager (不变)
    SandboxClient (不变)
3.5 backend/models/container.py — ContainerInfo 加 host
ContainerInfo:
  + host: str = "localhost"   # Docker 模式默认值
  Docker 模式: host="localhost", port=动态分配
  GKE 模式:   host="sandbox-xxx.openbox-sandbox.svc.cluster.local", port=8000
3.6 backend/core/config.py — 新增配置项
在 OpenBoxConfig 的 # -- Sandbox -- 区块下新增:
sandbox_provider: str = "docker"            # "docker" | "kubernetes"
k8s_namespace: str = "openbox-sandbox"      # 沙箱 Pod 的命名空间
k8s_storage_class: str = "standard-rwo"     # PVC 存储类型
k8s_storage_size: str = "10Gi"              # 每用户 PVC 大小
k8s_sandbox_cpu_request: str = "250m"
k8s_sandbox_cpu_limit: str = "1000m"
k8s_sandbox_memory_request: str = "256Mi"
k8s_sandbox_memory_limit: str = "1Gi"
sandbox_idle_timeout: int = 1800            # 空闲回收秒数（默认 30 分钟）
环境变量映射:
  sandbox_provider → SANDBOX_PROVIDER
  k8s_namespace → K8S_NAMESPACE
  k8s_storage_class → K8S_STORAGE_CLASS
  k8s_storage_size → K8S_STORAGE_SIZE
  k8s_sandbox_cpu_request → K8S_SANDBOX_CPU_REQUEST
  k8s_sandbox_cpu_limit → K8S_SANDBOX_CPU_LIMIT
  k8s_sandbox_memory_request → K8S_SANDBOX_MEMORY_REQUEST
  k8s_sandbox_memory_limit → K8S_SANDBOX_MEMORY_LIMIT
  sandbox_idle_timeout → SANDBOX_IDLE_TIMEOUT
3.7 backend/main.py — 启动逻辑
改动:
  原来: from sandbox.docker import docker_manager
        await docker_manager.cleanup_all()
  改为: from sandbox import provider
        if config.sandbox_provider == "kubernetes":
            await provider.reconcile()    # GKE: 恢复已有 Pod 状态
        else:
            await provider.cleanup_all()  # Docker: 清理旧容器
3.8 backend/sandbox/manager.py — 引用替换
所有 `from sandbox.docker import docker_manager` 替换为:
  from sandbox import provider
所有 `docker_manager.xxx` 替换为:
  provider.xxx
所有 `http://localhost:{sandbox.port}` 替换为:
  f"http://{sandbox.host}:{sandbox.port}"
SandboxInfo 加 host 字段:
  host: str (必须字段，由 ContainerInfo.host 传入)
涉及 4 处 import，6 处方法调用，3 处 localhost 替换
3.9 API 层替换（3 个文件）
统一模式：from sandbox.docker import docker_manager → from sandbox import provider

文件	替换内容
api/containers.py	docker_manager → provider（全部引用），localhost:{info.port} → {info.host}:{info.port}（1 处），build_sandbox_image 加 supports_build 判断
api/terminal.py	docker_manager → provider（1 处），ws://localhost:{info.port} → ws://{info.host}:{info.port}（1 处）
api/files.py	docker_manager → provider（2 处）
3.10 container/action_server.py — 新增备份恢复端点
新增两个端点:
POST /backup
  请求体: { "provider": "gcs", "bucket": "xxx", "prefix": "users/alice/workspace/" }
  逻辑:
    1. 扫描 /workspace 文件（排除 node_modules 等大目录）
    2. 对比 manifest（本地 /data/.manifest.json）
    3. 增量上传变更文件到 GCS
    4. 更新 manifest
  响应: { "uploaded": 15, "deleted": 2, "total_size": "45MB" }
POST /restore
  请求体: { "provider": "gcs", "bucket": "xxx", "prefix": "users/alice/workspace/" }
  逻辑:
    1. 从 GCS 下载 manifest
    2. 按 manifest 下载文件到 /workspace
    3. 恢复 mtime
  响应: { "restored": 42, "total_size": "120MB" }
这两个端点在 Pod 内执行，不需要 Backend 访问本地文件系统。
依赖: pip install google-cloud-storage (加到 container/requirements.txt)
认证: 通过 Workload Identity 自动获取 GCS 权限，无需 credential 文件
3.11 backend/blob/gcs_blob.py — GCS 实现
实现 IBlobStorage 接口:
  - 用 google-cloud-storage SDK
  - upload / download / delete / exists / list_keys / get_metadata / get_presigned_url
  - 格式与 IBlobStorage 接口完全对称
用途: Backend 侧需要时也可直接访问 GCS（比如管理接口查看用户存储用量）
四、K8s 部署清单设计
k8s/base.yaml
包含以下资源:
1. Namespace: openbox-sandbox, openbox
2. ServiceAccount: openbox-backend (namespace: openbox)
3. Role: sandbox-manager (namespace: openbox-sandbox)
   rules:
     - pods: create, delete, get, list, watch
     - services: create, delete, get, list
     - persistentvolumeclaims: create, delete, get, list
4. RoleBinding: backend-sandbox-manager
   subjects: ServiceAccount/openbox-backend (namespace: openbox)
   roleRef: Role/sandbox-manager
5. PriorityClass: sandbox-priority (value: 100000)
6. Backend Deployment:
   - replicas: 1
   - serviceAccountName: openbox-backend
   - 环境变量从 Secret 注入
   - SANDBOX_PROVIDER=kubernetes
7. Backend Service:
   - type: ClusterIP
   - port: 8080
8. Frontend Deployment + Service
9. Ingress (对外暴露，分 /api, /ws, /health → backend; / → frontend)
k8s/sandbox-pod-template.yaml
参考模板，实际由 KubernetesProvider 代码创建:
每个用户固定对应一套用户级资源：1 个 PVC、1 个 Pod、1 个 Service。
Pod:
  metadata:
    labels:
      app: openbox-sandbox
      openbox.dev/user-id: "{user_id}"
  spec:
    priorityClassName: sandbox-priority
    securityContext:
      runAsUser: 1000
      runAsGroup: 1000
    volumes:
      - name: workspace (PVC)
      - name: dshm (emptyDir, Memory, 256Mi)
      - name: data (emptyDir)
    containers:
      - name: sandbox
        image: gcr.io/{project}/openbox-sandbox:latest
        ports: [{containerPort: 8000}]
        env: [{SESSION_API_KEY: "..."}]
        volumeMounts:
          - workspace → /workspace
          - dshm → /dev/shm
          - data → /data
        resources:
          requests: {cpu: 250m, memory: 256Mi}
          limits: {cpu: 1000m, memory: 1Gi}
        readinessProbe:
          httpGet: {path: /alive, port: 8000}
          initialDelaySeconds: 2
          periodSeconds: 3
        livenessProbe:
          httpGet: {path: /alive, port: 8000}
          initialDelaySeconds: 10
          periodSeconds: 30
Service:
  type: ClusterIP
  ports: [{port: 8000, targetPort: 8000}]
  selector: 匹配 Pod labels
五、依赖变更
backend/pyproject.toml:
  + kubernetes>=29.0.0     # K8s Python SDK
  + google-cloud-storage>=2.14.0   # GCS Blob (可选，仅 GKE 模式需要)
container/requirements.txt:
  + google-cloud-storage>=2.14.0   # Action Server 内备份/恢复用
六、配置示例
# .env (GKE 生产)
SANDBOX_PROVIDER=kubernetes
SANDBOX_IMAGE=gcr.io/my-project/openbox-sandbox:latest
K8S_NAMESPACE=openbox-sandbox
DATABASE_URL=postgresql+asyncpg://openbox:xxx@10.0.0.5:5432/openbox
REDIS_URL=redis://10.0.0.10:6379/0
JWT_SECRET=xxx
BLOB_PROVIDER=gcs
GCS_BUCKET=openbox-backup
# .env (本地开发，和现在一样)
SANDBOX_PROVIDER=docker
SANDBOX_IMAGE=openbox-sandbox:latest
DATABASE_URL=postgresql+asyncpg://openbox:openbox@localhost:5432/openbox
REDIS_URL=redis://localhost:6379/0
七、实施顺序
阶段	内容	前置条件	状态
Phase 1	provider.py 接口 + docker.py 继承适配 + __init__.py 选择逻辑	无	✅ 已完成
Phase 2	ContainerInfo 加 host + 全量 localhost 替换 + docker_manager 引用替换	Phase 1	✅ 已完成
Phase 3	config.py 新增 GKE 配置项 + main.py 启动适配	Phase 1	✅ 已完成
Phase 4	kubernetes.py Provider 实现	Phase 1-3	✅ 已完成
Phase 5	gcs_blob.py + action_server.py 备份恢复端点	Phase 4	✅ 已完成
Phase 6	K8s 部署清单 + 依赖更新	Phase 4	✅ 已完成
Phase 7	GKE 集群联调测试	Phase 1-6 + 手动推送镜像	待执行
Phase 1-3 完成后 Docker 模式应该照常工作（回归验证点）。Phase 4-6 表示代码层实现已经就绪；当前仍待完成的重点是真实 GKE 环境联调与集成验证。
