FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git vim nano tree htop jq \
    net-tools iputils-ping procps \
    build-essential sudo ca-certificates gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 创建 sandbox 用户
RUN useradd -m -s /bin/bash -u 1000 sandbox && \
    usermod -aG sudo sandbox && \
    echo 'sandbox ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers && \
    passwd -d sandbox

# 安装 Python 依赖
COPY requirements.txt /opt/action_server/requirements.txt
RUN pip install --no-cache-dir -r /opt/action_server/requirements.txt

# 复制 action server
COPY action_server.py /opt/action_server/action_server.py

# 创建工作空间和持久化数据目录
# /data 和 /workspace 会被 bind mount，镜像内的内容会被覆盖
RUN mkdir -p /workspace && chown sandbox:sandbox /workspace
RUN mkdir -p /data/skills /data/mcp/logs && chown -R sandbox:sandbox /data

# 系统目录：/opt/openbox/skills/ — 内置 skill，不被 bind mount 覆盖
# 用户目录：/data/skills/ — 用户安装的 skill，bind mount 持久化
COPY dev-browser/ /opt/openbox/skills/dev-browser/
RUN cd /opt/openbox/skills/dev-browser && npm install --omit=dev \
    && chown -R sandbox:sandbox /opt/openbox

WORKDIR /workspace

ENV SESSION_API_KEY=""
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "/opt/action_server/action_server.py", "--port", "8000"]
