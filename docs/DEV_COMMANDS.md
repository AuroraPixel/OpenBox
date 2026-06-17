# OpenBox 运行命令

## 一键启动（推荐）

自动：停旧进程 → 删旧容器 → 重建镜像 → 安装依赖 → 启动前后端 → 健康检查

```bash
cd OpenBox
make start
```

## 一键部署（远程服务器）

拉代码 + 重建 + 重启：

```bash
cd OpenBox
make deploy
```

## 其他命令

```bash
make stop       # 停止所有服务
make restart    # 重启（重建镜像 + 清容器）
make start      # 一键启动
make deploy     # git pull + 一键启动

make backend    # 只启动后端（前台，带热重载）
make frontend   # 只启动前端（前台）
make dev        # 前台运行前后端

make deps       # 启动依赖（PostgreSQL、Redis、Azurite）
make migrate    # 数据库迁移
make clean      # 清理所有容器
make help       # 查看所有命令
```

## 查看日志

```bash
tail -f /tmp/openbox-backend.log   # 后端
tail -f /tmp/openbox-frontend.log  # 前端
```

## 检查状态

```bash
lsof -ti :8080 && echo "Backend running" || echo "Backend stopped"
lsof -ti :5173 && echo "Frontend running" || echo "Frontend stopped"
```

## 依赖服务

| 服务 | 端口 | 说明 |
|------|------|------|
| PostgreSQL | 5432 | 用户: openbox, 数据库: openbox |
| Redis | 6379 | 事件总线 + 缓存 |
| Azurite | 10000 | Blob 存储（可选） |
