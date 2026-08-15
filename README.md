# AI Agent Platform

> 企业级 AI Agent 基础平台 —— 以「平台优先，Agent 其次」为理念，提供从 Agent 编排、工作流引擎、知识库到模型管理的一站式基础设施。

<div align="center">

**FastAPI** · **LangGraph** · **Vue 3** · **PostgreSQL + pgvector** · **Redis**

</div>

---

## ✨ 核心特性

- 🤖 **Agent Runtime** — 基于 LangGraph 的工作流引擎（意图识别 → 知识检索 → 记忆召回 → 工具调用 → LLM 推理 → 人工兜底），支持多 Agent 独立对话
- 📊 **九大核心中心** — Agent / Workflow / Model / Knowledge / Memory / Tool / Human / Permission / Analytics，全量实现
- 🔐 **RBAC 权限体系** — 6 角色 19 权限，JWT 双 Token 认证（access 1h + refresh 7d）
- 📚 **知识库 + 向量检索** — PostgreSQL + pgvector，支持文档上传、自动分块、语义检索
- 🧩 **可视化工作流编辑器** — Vue Flow 画布 + 自定义节点 + 执行路径 Trace 高亮
- 💬 **多模态对话** — 文本 / PDF / Word / Excel / 图片 / 视频，附件作为上下文参与推理
- 🔗 **第三方零代码接入** — 每个 Agent 独立 `chat_token`，支持 API 调用或 iframe 嵌入
- 📈 **全链路可观测** — 执行 Trace / Span / Analytics 统计 / 实时监控面板

---

## 🛠️ 技术栈

| 层级 | 技术 |
| --- | --- |
| **后端** | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · Alembic · LangChain · LangGraph |
| **前端** | Vue 3 · Vite · TypeScript · Ant Design Vue · Vue Flow · Pinia |
| **数据库** | PostgreSQL 16 + pgvector · Redis 7 |
| **LLM** | DeepSeek（Chat / Reasoner）· 可扩展多提供商 |
| **部署** | systemd + Nginx + uvicorn（支持演进至 Docker / K8s） |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端 Admin Portal                     │
│   Vue 3 + Ant Design Vue + Vue Flow 工作流编辑器         │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP /api/v1
┌──────────────────────────▼──────────────────────────────┐
│                   FastAPI 应用层                          │
│  ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌──────────────┐ │
│  │  Auth   │ │  Agents  │ │Workflow │ │ Knowledge    │ │
│  │ (RBAC)  │ │ Runtime  │ │ Editor  │ │ + Vector     │ │
│  └─────────┘ └────┬─────┘ └─────────┘ └──────────────┘ │
│                ┌───▼───┐                                 │
│                │LangGraph│  意图→知识→记忆→工具→LLM→人工  │
│                └───┬───┘                                 │
│  ┌─────────┐ ┌─────▼──────┐ ┌────────┐ ┌────────────┐  │
│  │ Memory  │ │Model Center│ │ Tools  │ │ Analytics  │  │
│  └─────────┘ └────────────┘ └────────┘ └────────────┘  │
└──────────┬──────────────────────────┬───────────────────┘
           │                          │
  ┌────────▼────────┐       ┌─────────▼─────────┐
  │  PostgreSQL 16  │       │     Redis 7       │
  │  + pgvector     │       │  会话/缓存/队列    │
  └─────────────────┘       └───────────────────┘
```

---

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+
- PostgreSQL 14+（需安装 pgvector 扩展）
- Redis 6+

### 1. 克隆项目

```bash
git clone <your-repo-url> ai-agent-platform
cd ai-agent-platform
```

### 2. 后端设置

```bash
# 创建虚拟环境
python3.12 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env   # 若无 .env.example，参考下方配置
# 编辑 .env，填写 DATABASE_URL / REDIS_URL / DEEPSEEK_API_KEY
```

**`.env` 最小配置**：

```ini
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/ai_agent_platform
REDIS_URL=redis://localhost:6379/0
DEEPSEEK_API_KEY=sk-your-api-key
JWT_SECRET_KEY=change-this-to-random-hex
SECRET_KEY=change-this-to-random-hex
```

### 3. 数据库初始化

```bash
# 创建数据库与 pgvector 扩展
sudo -u postgres psql -c "CREATE DATABASE ai_agent_platform;"
sudo -u postgres psql -d ai_agent_platform -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 建表 + 初始化默认数据（角色/权限/模型配置/工作流）
python scripts/init_db.py
```

### 4. 启动后端

```bash
python run.py
# 或: uvicorn app.main:app --reload --port 8000
```

### 5. 启动前端

```bash
cd admin
npm install
npm run dev   # http://localhost:5173
```

### 6. 访问

| 入口 | 地址 |
| --- | --- |
| 管理后台 | http://localhost:5173 |
| API 文档 (Swagger) | http://localhost:8000/docs |
| API 文档 (ReDoc) | http://localhost:8000/redoc |
| 终端对话页 | http://localhost:8000/chat?token=xxxxxxxx |

---

## 📁 项目结构

```
ai-agent-platform/
├── app/                        # 后端应用
│   ├── main.py                 # FastAPI 入口
│   ├── core/                   # 配置管理
│   ├── api/v1/endpoints/       # API 路由（14 个模块）
│   ├── models/                 # SQLAlchemy 数据模型
│   ├── schemas/                # Pydantic 请求/响应模型
│   ├── repositories/           # 数据访问层
│   ├── services/               # 业务逻辑层
│   ├── runtime/                # Agent Runtime（LangGraph 执行引擎）
│   ├── workflows/              # 工作流定义与执行
│   ├── knowledge/              # 知识库解析与向量化
│   ├── memory/                 # 记忆管理
│   ├── tools/                  # 工具注册与适配器
│   ├── auth/                   # JWT 认证 + RBAC 权限
│   ├── analytics/              # 执行 Trace 与统计
│   ├── models_center/          # 模型提供商管理
│   ├── human/                  # 人工任务（转人工）
│   ├── permissions/            # 权限中心
│   └── database/               # 数据库会话 + Redis 客户端
├── admin/                      # 前端 Admin Portal
│   ├── src/
│   │   ├── views/              # 页面（12 个）
│   │   ├── components/         # 组件
│   │   ├── api/                # API 客户端
│   │   ├── stores/             # Pinia 状态管理
│   │   └── router/             # 路由
│   └── vite.config.ts
├── static/                     # 静态资源（chat.html 对话页）
├── uploads/                    # 用户上传文件
├── scripts/                    # 初始化脚本
├── alembic/                    # 数据库迁移
├── docs/                       # 项目文档
├── requirements.txt
└── run.py
```

---

## 📋 功能模块

### 后端 — 九大核心中心

| 中心 | 说明 |
| --- | --- |
| **Agent Center** | Agent CRUD、版本管理、工具/知识/工作流绑定、独立 chat_token |
| **Workflow Center** | LangGraph 工作流定义、可视化编辑、执行路径追踪 |
| **Model Center** | 多 LLM 提供商管理、模型配置、动态切换 |
| **Knowledge Center** | 文档上传、自动分块、pgvector 语义检索、置信度过滤 |
| **Memory Center** | 长期记忆存储与召回，按 user_id 隔离 |
| **Tool Center** | 工具注册、Schema 化、权限检查（内置 5 个业务工具） |
| **Human Center** | 转人工任务、工单分配、处理闭环 |
| **Permission Center** | RBAC（6 角色 19 权限）、JWT 双 Token |
| **Analytics Center** | 执行 Trace、Span 级追踪、统计面板 |

### 前端 — 管理后台页面

| 页面 | 功能 |
| --- | --- |
| Dashboard | 系统总览、关键指标 |
| Agents | Agent 管理、配置抽屉（模型/工具/知识/工作流绑定） |
| Workflow Editor | Vue Flow 可视化工作流编辑 + Trace 高亮 |
| Knowledge | 知识库管理、文档同步 |
| Models | 模型提供商与配置管理 |
| Conversations | 对话历史查看 |
| Memories | 记忆管理 |
| Tasks | 人工任务工单 |
| Analytics | 执行分析与 Trace |
| Monitoring | 系统监控（DB/Redis/LLM 健康） |
| Users | 用户与角色管理 |

### 内置业务工具

| 工具 | 用途 |
| --- | --- |
| `product_query` | 商品信息查询 |
| `order_query` | 订单状态查询 |
| `inventory_query` | 库存查询 |
| `refund_query` | 退款查询 |
| `logistics_query` | 物流查询 |

---

## 🔑 默认账号

| 角色 | 账号 | 密码 | 权限 |
| --- | --- | --- | --- |
| 超级管理员 | `admin` | `admin123456` | 全部权限（superuser） |
| 客服 | `cs_agent` | `cs123456` | 对话查看 + 工单处理 |

> ⚠️ 生产环境部署后请立即修改默认密码。

---

## 📖 文档导航

| 文档 | 说明 |
| --- | --- |
| [架构与方案文档](docs/ARCHITECTURE.md) | 系统架构蓝图、九大中心设计、数据库设计、开发路线图 |
| [系统使用说明书](docs/SYSTEM_USER_GUIDE.md) | 面向运维与业务人员的完整使用指南 |
| [API 参考文档（中文）](docs/API_REFERENCE_ZH.md) | 全量 API 接口说明（84 接口，含权限标注） |
| [API 文档（HTML 版）](docs/API_REFERENCE_ZH.html) | 交互式 API 文档（搜索/深色模式/侧边导航） |
| [第三方集成指南](docs/THIRD_PARTY_AGENT_INTEGRATION.md) | 第三方系统对接 Agent 的场景化接入指南 |
| [部署指南](docs/DEPLOYMENT_GUIDE.md) | 无 Docker/K8s 的手动部署文档（systemd + Nginx） |

---

## 🚢 部署

详细部署步骤请参考 [部署指南](docs/DEPLOYMENT_GUIDE.md)，核心架构：

```
Nginx (:80/:443)
  ├── /          → admin/dist 静态文件 (SPA)
  ├── /api/*     → uvicorn :8000
  └── /docs /chat → uvicorn :8000

systemd: ai-agent.service
  └── uvicorn app.main:app --workers 2~4

PostgreSQL 16 + pgvector  |  Redis 7
```

快速部署命令：

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 初始化数据库
python scripts/init_db.py

# 3. 构建前端
cd admin && npm run build

# 4. 启动（生产）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 🧩 Agent 工作流

每个 Agent 绑定一个或多个工作流，运行时按以下节点顺序执行：

```
用户消息
  │
  ▼
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ 意图识别  │ ──▶ │ 知识检索  │ ──▶ │ 记忆召回  │ ──▶ │ 工具调用  │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                                                        │
                    ┌──────────┐     ┌──────────┐        ▼
                    │ 人工兜底  │ ◀── │ LLM 推理 │ ◀───────┘
                    └──────────┘     └──────────┘
```

- **意图识别**：判断用户意图类型与置信度
- **知识检索**：pgvector 语义搜索 + 置信度过滤
- **记忆召回**：按 user_id 检索相关长期记忆
- **工具调用**：Schema 化工具执行（带权限检查）
- **LLM 推理**：组合上下文生成回答
- **人工兜底**：置信度不足时创建工单转人工

---

## 🔌 第三方接入

第三方系统可通过两种方式接入 Agent 对话：

### 方式一：API 调用

```bash
# 1. 获取 Agent 配置（通过 chat_token）
curl http://your-server/api/v1/public/chat-config?token=Qp0cKHQq

# 2. 发送消息
curl -X POST http://your-server/api/v1/conversations/chat \
  -H "Content-Type: application/json" \
  -d '{"agent_id": 2, "message": "这款产品有XL码吗？", "user_id": 1001}'

# 3. 多轮续聊（回传 conversation_id）
curl -X POST http://your-server/api/v1/conversations/chat \
  -H "Content-Type: application/json" \
  -d '{"agent_id": 2, "message": "那价格多少？", "conversation_id": 123}'
```

### 方式二：iframe 嵌入

```html
<iframe src="http://your-server/chat?token=Qp0cKHQq" width="100%" height="600">
</iframe>
```

详见 [第三方集成指南](docs/THIRD_PARTY_AGENT_INTEGRATION.md)。

---

## 📝 开发规范

- **禁止** Agent 直接执行 SQL 或调用第三方 API，必须走 Service + Tool 封装
- **禁止**直接调用 `openai.call()`，必须通过 Model Center
- Prompt 属于代码资产，需版本管理
- 数据库规范：snake_case、BIGSERIAL、`created_at` / `updated_at`、预留 `tenant_id`、JSONB 用于动态配置
- 工作流必须有失败路径；Tool 必须 Schema 化 + 权限检查
- 三层架构：Schemas → Repositories → Services，Endpoint 只做 HTTP 层

---

## 📄 License

本项目暂未设置开源 License，版权归项目所有者所有。如需使用请联系作者。
