---
name: gke-ingress-setup
description: Set up GKE Ingress with Google Managed Certificate for HTTPS access. Use when creating Ingress, configuring SSL certificates, setting up domain proxy, or troubleshooting GKE Ingress and certificate issues.
---

# GKE Ingress Setup with Google Managed Certificate

## Overview

在 GKE Autopilot 集群上，通过 Ingress + Google Managed Certificate 为服务配置 HTTPS 域名访问。

## Prerequisites

- 已安装 `gcloud` 和 `kubectl`
- 已连接到目标 GKE 集群（`kubectl config get-contexts` 确认）
- 拥有域名的 DNS 管理权限

## 完整流程

### Step 1: 创建 ClusterIP Service

为目标应用创建 ClusterIP Service，暴露应用端口：

```yaml
apiVersion: v1
kind: Service
metadata:
  name: <app>-service
  namespace: default
spec:
  selector:
    app: <app>
  ports:
    - protocol: TCP
      port: <app-port>
      targetPort: <app-port>
  type: ClusterIP
```

> **注意**：Service 端口使用应用实际端口（如 4000），无需改为 80。GCP 负载均衡器会自动在 80/443 上监听并转发到 Service 端口。

### Step 2: 预留全球静态 IP

```bash
gcloud compute addresses create <app>-static-ip \
  --global \
  --project=<project-id>
```

获取分配的 IP：

```bash
gcloud compute addresses describe <app>-static-ip \
  --global \
  --project=<project-id> \
  --format='get(address)'
```

### Step 3: 创建 ManagedCertificate + FrontendConfig + Ingress

一次性创建三个资源：

```yaml
apiVersion: networking.gke.io/v1
kind: ManagedCertificate
metadata:
  name: <app>-certificate
  namespace: default
spec:
  domains:
    - <your-domain>
---
apiVersion: networking.gke.io/v1beta1
kind: FrontendConfig
metadata:
  name: <app>-frontend-config
  namespace: default
spec:
  redirectToHttps:
    enabled: true
    responseCodeName: MOVED_PERMANENTLY_DEFAULT
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: <app>-ingress
  namespace: default
  annotations:
    kubernetes.io/ingress.global-static-ip-name: <app>-static-ip
    networking.gke.io/managed-certificates: <app>-certificate
    networking.gke.io/v1beta1.FrontendConfig: <app>-frontend-config
spec:
  rules:
    - host: <your-domain>
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: <app>-service
                port:
                  number: <app-port>
```

### Step 4: 配置 DNS

在域名 DNS 管理后台添加 A 记录：

```
<your-domain>  →  A  →  <static-ip>
```

### Step 5: 等待证书签发

Google Managed Certificate 签发通常需要 **15-60 分钟**。

检查状态：

```bash
kubectl get managedcertificate <app>-certificate
kubectl describe managedcertificate <app>-certificate
```

证书状态说明：

| 状态 | 含义 |
|------|------|
| `Provisioning` | 正在签发，正常等待 |
| `Active` | 签发完成，HTTPS 可用 |
| `ProvisioningFailed` | 签发失败，检查 DNS |
| `ProvisioningFailedPermanently` | 永久失败，需删除重建 |

域名状态说明：

| 状态 | 含义 |
|------|------|
| `Provisioning` | 正在验证域名 |
| `Active` | 域名验证通过 |
| `FailedNotVisible` | DNS 未正确指向静态 IP |

GCP 侧证书详情：

```bash
gcloud compute ssl-certificates describe <cert-name> \
  --project=<project-id>
```

## 流量链路

```
用户浏览器
  ↓ HTTPS (443) / HTTP (80 → 301 重定向 HTTPS)
GCP 负载均衡器 (静态 IP)
  ↓ 应用端口
ClusterIP Service
  ↓ 应用端口
Pod (容器)
```

## 常见问题排查

### 证书签发失败 (ProvisioningFailedPermanently)

1. 确认 DNS A 记录正确指向 Ingress 静态 IP
2. 删除失败的 ManagedCertificate 并重新创建
3. 如果之前有同域名证书残留，需先清理

### Ingress 删除卡住 (Finalizer)

Ingress 有 GKE finalizer 用于清理 GCP 负载均衡器资源，如果卡住可强制移除：

```bash
kubectl patch ingress <ingress-name> \
  -p '{"metadata":{"finalizers":[]}}' --type=merge
```

> **警告**：强制移除 finalizer 后需到 GCP Console 手动检查并清理残留的负载均衡器资源。

### 健康检查协议错误

如果出现 `Protocol "TCP" is not valid` 错误，需确保 Service 使用 HTTP 协议。可通过 BackendConfig 自定义健康检查：

```yaml
apiVersion: cloud.google.com/v1
kind: BackendConfig
metadata:
  name: <app>-backend-config
spec:
  healthCheck:
    type: HTTP
    port: <app-port>
    requestPath: /
```

然后在 Service 上添加注解：

```yaml
metadata:
  annotations:
    cloud.google.com/backend-config: '{"default":"<app>-backend-config"}'
```

### HTTPS 返回 500 或连接终止

证书还在签发中时，HTTPS 无法正常工作，会出现 500 或连接终止。等证书状态变为 `Active` 即可。

### ClusterIP 无法从外部访问

ClusterIP 只在集群内部可达，这是正常的。外部访问通过 Ingress 的公网 IP。

## 验证清单

```
- [ ] Service 创建成功，Endpoints 不为空
- [ ] 静态 IP 已预留
- [ ] ManagedCertificate 已创建
- [ ] FrontendConfig 已创建
- [ ] Ingress 已创建，Address 已分配
- [ ] DNS A 记录已配置
- [ ] Ingress 后端状态为 HEALTHY
- [ ] 证书状态为 Active
- [ ] HTTP 访问返回 301 重定向
- [ ] HTTPS 访问正常
```

## 有用的命令

```bash
# 查看集群所有 Ingress
kubectl get ingress --all-namespaces

# 查看所有证书
kubectl get managedcertificates --all-namespaces

# 查看 Ingress 详情（含后端健康状态和事件）
kubectl describe ingress <ingress-name>

# 验证 DNS 解析
dig <your-domain> +short

# 测试 HTTP 访问
curl -s -o /dev/null -w "%{http_code}" http://<your-domain>/

# 测试 HTTPS 访问（跳过证书验证）
curl -sk -o /dev/null -w "%{http_code}" https://<your-domain>/

# 列出 GCP 静态 IP
gcloud compute addresses list --global --project=<project-id>

# 列出 GCP SSL 证书
gcloud compute ssl-certificates list --project=<project-id>
```
