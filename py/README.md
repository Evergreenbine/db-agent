# OA Agent 后端服务

公司自研 OA 智能体后端，基于 FastAPI + OpenAI Agents SDK + DeepSeek + Chroma RAG。

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Web 框架 | FastAPI | 高性能 ASGI 框架，自带 OpenAPI 文档 |
| 智能体 SDK | OpenAI Agents SDK (`openai-agents`) | 智能体编排、工具调用、Handoff |
| LLM 模型 | DeepSeek (`deepseek-chat`) | 通过 OpenAI 兼容接口接入 |
| 向量数据库 | ChromaDB | 嵌入式，纯 Python，工具/接口函数 RAG |
| Embedding 模型 | BAAI/bge-small-zh-v1.5 (512维) | 本地运行，中文语义检索，无需外部 API |
| ORM | SQLAlchemy 2.0 | 现代化 ORM，支持类型注解 |
| 数据库驱动 | oracledb (thin 模式) | 纯 Python 驱动，无需安装 Oracle Client |
| 配置管理 | pydantic-settings + .env | 类型安全的配置加载 |
| 业务数据库 | Oracle (10.3.10.87:1521/orcl) | 公司 Ecology OA 库 |

## RAG 架构

采用 **SKILL.md 文档 → 向量索引 → 动态工具解析** 流程：

```
用户 "我想请两天病假"
    ↓
① bge-small-zh 向量化
    ↓
② Chroma 检索 → submit_leave, query_leave_balance...
    ↓
③ 动态转为 SDK 工具 → Agent(tools=[命中的函数])
    ↓
④ DeepSeek 选对函数 + 填参数 → 执行 → 返回结果
```

| 层 | 职责 | 数据源 |
|----|------|--------|
| 向量库 | 从所有 SKILL.md 中检索 top-K 相关工具 | `skills/*.md` 文件 |
| Agents SDK | 从 K 个里选一个 + 填参数 + 执行 | Python `@tool` 函数 |

## SKILL.md 格式

每个工具对应一个 `.md` 文件，YAML frontmatter + Markdown 正文：

```markdown
---
tool: submit_leave              # Python 函数名，映射回实现
title: 提交请假申请              # 人类可读名称
keywords: 请假;病假;事假;年假    # 触发关键词，增强检索
---

# 提交请假申请

## 功能说明
提交一条请假申请到 OA 系统，等待主管审批。

## 参数
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| days | integer | 是 | 请假天数 |
| reason | string | 是 | 请假事由 |

## 使用场景
- "我想请两天病假" → days=2, reason="病假"

## 示例
输入: {"days": 2, "reason": "病假"}
输出: "请假申请已提交：2天，事由：病假，待主管审批"
```

| 部分 | 作用 | 谁用 |
|------|------|------|
| `tool` | 映射回 Python 函数 | 程序（tool_resolver） |
| `keywords` | 显式关键词增强语义检索 | bge 向量化 |
| 功能说明 + 参数 | 让 LLM 理解做什么、怎么调 | DeepSeek |
| 使用场景 + 示例 | 帮 LLM 判断该不该调、怎么填参数 | DeepSeek |

新增工具只需：写一个 `.md` 文件 + 写一个 `@tool` 函数，启动时自动入库。

## 项目结构

```
py/
├── .env                  # 环境变量（不入 Git）
├── .env.example          # 环境变量模板
├── .gitignore
├── requirements.txt      # Python 依赖
├── README.md             # 本文档
└── app/
    ├── __init__.py
    ├── main.py           # FastAPI 入口，启动时建 RAG 索引
    ├── config.py         # 配置管理（pydantic-settings）
    ├── database.py       # SQLAlchemy 引擎 + 会话
    ├── models.py         # ORM 模型（示例: OaTask）
    ├── agents/
    │   ├── __init__.py
    │   ├── oa_agent.py   # DeepSeek 客户端 + 动态 Agent 创建
    │   ├── tools/                # 工具注册表 + Python 实现
    │   │   ├── __init__.py
    │   │   ├── registry.py       # @tool 装饰器注册 + 元数据
    │   │   └── attendance.py     # 加班/请假/调休/补卡/查考勤/查年假
    │   ├── skills/                # SKILL.md 文档（RAG 索引源）
    │   │   ├── submit_leave.md
    │   │   ├── submit_overtime.md
    │   │   ├── submit_comp_off.md
    │   │   ├── submit_correction.md
    │   │   ├── query_attendance.md
    │   │   └── query_leave_balance.md
    │   └── rag/                  # Chroma 向量检索
    │       ├── __init__.py
    │       ├── embeddings.py     # bge-small-zh 本地向量化
    │       ├── store.py          # 扫描 skills/*.md 索引 + 检索
    │       └── tool_resolver.py  # 检索 → 动态工具列表
    └── api/
        ├── __init__.py
        ├── health.py     # 健康检查路由
        └── agent.py      # 智能体调用路由
```

## 快速开始

### 1. 安装依赖

```bash
cd py
pip install -r requirements.txt
```

> 如网络受限需要代理：`pip install --proxy http://127.0.0.1:7892 -r requirements.txt`

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写 DeepSeek API Key 和 Oracle 连接信息。

### 3. 首次下载 Embedding 模型

```bash
# 通过代理下载（约 100MB）
$env:HTTPS_PROXY="http://127.0.0.1:7892"
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"
```

### 4. 启动服务

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

启动后访问 http://localhost:8000/docs 查看 Swagger 文档。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 基础健康检查 |
| GET | `/health/db` | 数据库连通性检查 |
| POST | `/api/agent/test` | 测试智能体（RAG 检索 + DeepSeek） |

## 工具注册机制

文档与代码分离：

```python
# tools/attendance.py — 只管逻辑
from app.agents.tools.registry import tool

@tool
def submit_leave(days: int, reason: str) -> str:
    return f"请假申请已提交：{days}天，事由：{reason}，待主管审批"
```

```markdown
<!-- skills/submit_leave.md — 只管文档 -->
---
tool: submit_leave
title: 提交请假申请
keywords: 请假;病假;事假;年假;休息
---
# 提交请假申请 ...
```

- `@tool` 装饰器注册 Python 函数为 SDK 工具
- `.md` 文件提供 RAG 索引源（frontmatter 的 `tool` 字段映射回函数名）
- 启动时自动扫描 `skills/*.md` 构建 Chroma 索引
- 产品/运营可以单独维护 `.md`，不碰 Python 代码

## 数据库连接

```
oracle+oracledb://ecology:ecology@10.3.10.87:1521/?sid=orcl
```

对应原 Spring 配置：

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@10.3.10.87:1521:orcl
    username: ecology
    password: ecology
    driver-class-name: oracle.jdbc.OracleDriver
    type: com.alibaba.druid.pool.DruidDataSource
```

## 网络与代理说明

| 目标 | 是否需要代理 | 说明 |
|------|-------------|------|
| GitHub | 是 | `git config --global http.proxy http://127.0.0.1:7892` |
| HuggingFace | 首次下载需要 | 后续从本地缓存加载 |
| DeepSeek API | 否 | 国内服务，直连即可 |
| Oracle DB | 否 | 内网地址 |
