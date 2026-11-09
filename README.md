# MatPilot

**面向半导体与光电材料科研的文献 RAG 与多 Agent 分析平台。**

从材料筛选、论文发现和 PDF 解析，到实验信息提取、带引用问答与多角色协作，
MatPilot 将材料计算数据和论文原文组织在同一个科研工作台中。
当前优先围绕氧化物半导体场景开发，使用中文界面与中文模型提示词。

每条科研结论应能追溯到数据来源：计算值与实验值分别保存，缺失字段保留为空，
模型输出保留原文、页码与处理轨迹，便于研究者核查。

**项目状态：** 已完成 V0.1 本机工作流验收与企业化 P0–P2（租户、异步任务、文档 SSOT、可观测、`/api/v1`）。
默认本机租户 `local`；完整多模态与 P3（评测扩容 / 人审）仍在建设中。

## 核心功能

| 工作区 | 当前能力 | 数据与证据 |
| --- | --- | --- |
| 材料筛选 | 按化学式、元素、带隙及稳定性条件查询，查看材料详情、结构和比较结果 | Materials Project 实时计算数据，保存查询参数及 JSON / CSV 快照 |
| 论文发现 | DOI / 关键词查询，按年份、开放获取状态等筛选 | OpenAlex 在线元数据；检索到论文不代表已读取全文 |
| 论文解析 | 文本 PDF 解析，保留页码、文本块及表格，提取带隙与相关实验信息 | 本地上传的全文；提取记录关联原文证据并保留待审核状态 |
| 文献知识库 | 文献索引、Dense / BM25L / RRF 混合检索、可选 Rerank、带引用问答 | PostgreSQL + pgvector，支持查看匹配片段和页码 |
| 科研助手 | LangGraph 单 Agent、自动路由及多角色协作，回读历史任务 | 有界工具调用、来源引用、阶段记录及独立 Reviewer 复核 |

界面采用米白、暖灰和浅棕配色，优先使用微软雅黑。电脑端使用侧边导航，手机尺寸视口使用底部导航，
支持按名称选择文献、原文弹窗与跨工作区保留输入。响应式布局不会自动将本地服务发布到手机或公网。

## 项目架构

~~~mermaid
flowchart TD
    UI["Streamlit · 五个工作区"] --> API["FastAPI · /api/v1"]
    API --> AUTH["Principal · API Key / local"]
    AUTH --> TENANT["tenants/{id} 文件与向量"]
    API --> JOBS["JobWorker · 异步长任务"]
    API --> MAT["材料查询与比较"]
    API --> LIT["论文发现"]
    API --> DOC["DocumentService / DocumentStore"]
    API --> RAG["文献检索与引用问答"]
    API --> AGENT["research + tools/claims + collaboration"]
    MAT --> MP["Materials Project"]
    LIT --> OA["OpenAlex · 元数据"]
    DOC --> PARSE["PyMuPDF / pdfplumber"]
    DOC --> LLM["LLMClient · DashScope"]
    DOC --> FILES["租户目录 · PDF / 审计 / 快照 / jobs"]
    RAG --> LLM
    RAG <--> PG[("PostgreSQL · mp_docs / mp_chunks")]
    AGENT --> MAT
    AGENT --> LIT
    AGENT --> RAG
    AGENT --> FILES
    JOBS --> AGENT
    JOBS --> DOC
    JOBS --> RAG
~~~

协作流程包含 Planner、材料专家、文献专家、Analysis 和独立 Reviewer，按任务依赖调用受限工具。
详细调用关系见 [架构说明](docs/architecture.md) 与 [多角色协作](docs/collaboration.md)。

| 层次 | 技术 |
| --- | --- |
| 运行环境 | Python **3.13**，uv 与 `uv.lock` |
| 界面与接口 | Streamlit、FastAPI、Pydantic |
| 材料与论文 | mp-api、pymatgen、OpenAlex |
| PDF 解析 | PyMuPDF、pdfplumber |
| 检索与存储 | PostgreSQL 17、pgvector、Jieba、BM25L、RRF |
| 模型与编排 | DashScope、通义千问、LangGraph |
| 开发检查 | pytest、Ruff |

## 快速开始

以下命令使用 **PowerShell**，请在项目根目录执行。主要开发与验收环境为 Windows；
其他系统需自行调整终端命令并验证运行环境。

### 1. 准备环境并克隆

需要 Git、Python **3.13**、uv、Docker Desktop（或支持 Compose 的 Docker 环境）。
本仓库为私有仓库时，克隆前需要使用有访问权限的 GitHub 账户完成 Git 身份验证。

~~~powershell
git clone https://github.com/ivyfan-toowell/mat_pilot.git
Set-Location mat_pilot
uv sync --locked --all-extras

# 仅在 .env 不存在时复制，保留已有配置。
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
~~~

`--all-extras` 安装界面与 PostgreSQL 依赖；后续 `uv run` 同样带上该选项，保持环境一致。
依赖由 `uv.lock` 固定，当前默认使用阿里云 PyPI 镜像。

### 2. 配置服务

在本地编辑 `.env`，填写自己的密钥。密钥由服务端读取，不要提交到仓库或粘贴到讨论区。

| 配置项 | 用途 | 说明 |
| --- | --- | --- |
| `MP_API_KEY` | Materials Project 材料查询 | 材料工作流及完整就绪检查需要 |
| `DASHSCOPE_API_KEY` | 文本生成、Embedding 和可选 Rerank | 建立向量索引、模型提取与问答需要 |
| `OPENALEX_API_KEY` | OpenAlex 论文发现 | 可选；不影响其他模块的配置检查 |
| `LLM_BASE_URL` / `LLM_MODEL` | 通义兼容接口与生成模型 | 默认北京地域接口、`qwen-plus` |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` | 向量模型与维度 | 默认 `text-embedding-v4`、1024 维 |
| `RERANK_URL` / `RERANK_MODEL` | 重排接口与模型 | 默认 `qwen3-rerank`；重排默认关闭 |
| `DATABASE_URL` / `POSTGRES_*` | 数据库连接 | 首次本地使用可由下方脚本填充缺失凭据 |
| `AUTH_MODE` / `AUTH_API_KEYS` | API Key 认证与租户 | 默认 `off`（租户 `local`）；共享部署设为 `api_key` |
| `MATPILOT_API_KEY` | Streamlit 调用后端 | 与某个 `AUTH_API_KEYS` 中的 key 一致 |
| `JOB_WORKERS` | 异步任务线程数 | 默认 2；界面长任务经 `/api/v1/jobs/*` 入队 |
| `RATE_LIMIT_*` / `LOG_JSON` | 限流与日志 | 默认限流关闭；生产建议开启并使用 JSON 日志 |
| `SCHEMA_AUTO_APPLY` / `VECTOR_HNSW` | 库表与向量索引 | 启动自动 DDL；可选 HNSW |

业务数据保存在 `data/tenants/{tenant_id}/`。推荐迁移顺序：

~~~powershell
# 1) 填充缺失的本地数据库密码与连接串（不打印密码）。
uv run --locked --all-extras python -m scripts.setup_database
# 2) 旧扁平 data/* → tenants/local（若仍有旧布局）。
uv run --locked --all-extras python -m scripts.migrate_tenant_local
# 3) 启动 DB 后，schema 可由 SCHEMA_AUTO_APPLY 或显式执行：
#    uv run --locked --all-extras python -m scripts.apply_schema
#    或：uv run --locked --all-extras alembic upgrade head
# 4) 旧 parsed.json / experiments.json → Postgres SSOT。
uv run --locked --all-extras python -m scripts.migrate_docs_to_postgres
~~~

生产建议：`AUTH_MODE=api_key` + `AUTH_API_KEYS` + UI `MATPILOT_API_KEY`；
`RATE_LIMIT_PER_MINUTE>0`、`LOG_JSON=true`；可选 `VECTOR_HNSW=true`。

完整变量见 [`.env.example`](.env.example)。DashScope 接口地域必须与密钥匹配，
跨地域使用时应同时核对生成、Embedding 与 Rerank 配置。
更改 Embedding 模型或维度后，应重新建立兼容索引。

### 3. 启动数据库和后端

先启动 Docker Desktop，然后执行：

~~~powershell
uv run --locked --all-extras python -m scripts.setup_database
docker compose up -d --wait db

# 保持这个终端运行。
uv run --locked --all-extras uvicorn app.main:app --host 127.0.0.1 --port 8000
~~~

数据库映射到 `127.0.0.1:5433`，数据保存在 Docker 具名卷中。
现有 Compose **仅启动数据库**，后端与界面分别运行。

### 4. 启动界面

统一从仓库根目录的 `streamlit_app.py` 启动；Windows 也可直接运行 `./start_ui.ps1`。两种方式都不依赖临时设置 `PYTHONPATH`。原 `ui/app.py` 入口同样保留兼容性修复。


新开终端并进入同一个项目目录：

~~~powershell
uv run --locked --all-extras streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
~~~

- 科研工作台：[http://127.0.0.1:8501](http://127.0.0.1:8501)
- API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 进程存活：[`/health`](http://127.0.0.1:8000/health)
- 配置与数据库就绪：[`/health/ready`](http://127.0.0.1:8000/health/ready)

`/health/ready` 不调用付费模型；它检查必需密钥是否配置及数据库连接，
不能代替第三方 API 的真实连通性验证。关闭服务终端或重启电脑后，需要重新启动服务。

## 使用流程

1. **筛选材料**：设置化学式、带隙和稳定性条件，查询并保存 Materials Project 计算数据。
2. **发现论文**：检索 DOI 或关键词，查看元数据、开放获取链接与许可信息。
3. **解析全文**：自行获取有使用权限的 PDF 并上传，核对逐页文本和表格，再按需提取实验信息。
4. **建立知识库**：将已解析文献加入索引，选择检索策略，查看原文或进行带引用问答。
5. **开展分析**：使用科研助手调用材料与文献工具，回看答案、引用及协作轨迹并进行人工审核。

页面读取已有文献与历史结果不会重新运行模型。索引、模型提取、生成回答及开启重排会调用外部服务，
实际费用取决于服务商配置与用量。

### 公开许可样例与命令行

仓库提供样例下载脚本，论文 DOI 为 `10.3390/nano10030546`、PMCID 为 `PMC7153365`。
脚本同时保存来源、CC BY 4.0 许可与文件哈希。下载后的 PDF 和解析结果仅保留在本地。

~~~powershell
uv run --locked --all-extras python -m scripts.download_sample_paper
uv run --locked --all-extras python -m scripts.parse_paper data/sample_papers/PMC7153365.pdf

# 将占位文字替换为上一步实际返回的 document_id。
$documentId = '替换为解析返回的文献 UUID'
uv run --locked --all-extras python -m scripts.extract_experiments $documentId
uv run --locked --all-extras python -m scripts.knowledge index --document-id $documentId
uv run --locked --all-extras python -m scripts.knowledge answer --document-id $documentId --question '论文报告了哪些光学带隙？'

# 仅进行关键词检索；如需混合检索可选择 hybrid，按需增加 --rerank。
uv run --locked --all-extras python -m scripts.knowledge search --document-id $documentId --question 'DRS 测试的扫描波长范围？' --retrieval-mode sparse
~~~

材料查询示例：

~~~powershell
uv run --locked --all-extras python -m scripts.query_materials --formula TiO2 --band-gap-min 0 --band-gap-max 10 --limit 3
~~~

## 目录结构与数据保存

~~~text
mat_pilot/
├── app/
│   ├── agents/       # research 编排、tools、claims、多角色协作
│   ├── api/          # HTTP 接口（路由前缀 /api/v1）
│   ├── core/         # 配置、认证、中间件、日志与错误处理
│   ├── evaluation/   # 检索评测指标
│   ├── ingestion/    # PDF、表格、实验信息提取与分块
│   ├── schemas/      # 数据模型与验证
│   ├── science/      # 材料领域与 Materials Project 适配
│   └── services/     # 检索、模型、向量库及业务服务
├── ui/               # 五个工作区、共享组件与主题样式
├── scripts/          # 环境检查、启动、导入及真实验收脚本
├── tests/            # 离线自动化测试
├── eval/             # 小规模检索评测标注
├── docs/             # 架构、接口、设计规范和任务书
├── .streamlit/       # 无密钥的界面配置
├── data/             # 本地生成的数据与验收报告，不上传 Git
├── .env.example      # 配置模板
├── docker-compose.yml
├── pyproject.toml
└── uv.lock
~~~

`data/tenants/<tenant_id>/documents/<文献 UUID>/` 保存 PDF 原件与导出/审计文件；
配置数据库后，解析结果与实验提取以 PostgreSQL `mp_docs` / `mp_experiments` 为准。
材料查询快照、Agent 任务与异步 job 状态仍在租户目录；向量块在 `mp_chunks`（含 `tenant_id`）。
若本地仍有旧版 `parsed.json`，可执行：

~~~powershell
uv run --locked --all-extras python -m scripts.migrate_docs_to_postgres
~~~
首次克隆不会获得开发机上的论文、实验记录、向量索引和历史任务，需要自行导入。

`.gitignore` 排除真实环境配置、数据、日志、缓存、数据库备份和本机沙箱排障资料。
文件仍保留在本地；Git 仓库不能代替科研数据与 Docker 数据卷备份。
详见 [GitHub 使用说明](docs/github.md)。

## 开发与验证

~~~powershell
uv run --locked --all-extras pytest -q
uv run --locked --all-extras ruff check .
uv lock --check
~~~

截至 **2026-11-05**，开发环境中 **152+ 项离线测试通过，Ruff 检查通过**。
测试使用明确的替身隔离外部服务；真实材料查询、PDF、RAG、OpenAlex 与协作案例另外验收，
报告保存在本地 `data/acceptance/`，未随代码发布。
响应式页面已检查 320–1440 px 视口；目前的检索评测仅包含单篇真实论文的 12 个问题，
不能据此推断跨论文效果。详见 [检索评测](docs/retrieval.md)。

### 常见问题

- **8501 拒绝连接**：确认 Streamlit 终端仍在运行，并使用终端输出的端口；仅启动后端不会启动界面。
- **界面能打开，但提示后端不可用**：确认 8000 端口的 FastAPI 服务已启动，`BACKEND_URL` 与其一致。
- **就绪接口返回 503**：检查 Docker 数据库和必需配置；先用 `docker compose ps` 查看数据库状态。
- **已有数据库无法认证**：修改 `.env` 不会重设已初始化数据卷中的密码，需保持配置与已有数据库一致。
- **克隆后没有历史文献**：科研数据不在仓库内；请重新导入全文并建立索引。

## 当前边界与路线

- **科研审核**：原文匹配、数值检查和模型 Reviewer 辅助复核，不能代替研究者审核。MP 计算带隙与论文实验带隙需分别解释。
- **检索范围**：材料查询首批最多 100 条，不代表全库排名；检索分数不是置信概率；元数据不能作为已阅读全文的证据。
- **文档能力**：当前主要支持文本 PDF；扫描件会提示需要 OCR。Word、Excel、复杂版式和完整多模态解析仍待开发。
- **运行方式**：当前绑定 localhost；默认 `AUTH_MODE=off`（租户 `local`）。共享部署须开启 `api_key`。长任务有进程内异步队列与状态落盘，但尚无跨进程抢占或崩溃后自动恢复执行。
- **后续计划（P3 / V0.8+）**：跨论文评测扩容、人审队列、OCR/多模态、跨进程 job 恢复；再推进 V1.0 知识图谱、报告、OIDC/RBAC 与完整服务部署。异步任务与文档 SSOT 已在 P0-b/c 落地。

## 项目文档

- [架构与调用关系](docs/architecture.md) · [API 说明](docs/api.md)
- [论文发现](docs/literature.md) · [文献检索与评测](docs/retrieval.md) · [多角色协作](docs/collaboration.md)
- [UI / UX 设计规范](docs/design/ui-ux-proposal.md) · [开发记录](docs/development.md)
- [项目任务书与路线](docs/taskbook.md) · [仓库维护](docs/github.md)


## V0.9 跨论文实验知识分析（开发分支）

V0.9 新增样品级光学带隙提取、实验知识库（PostgreSQL JSONB）、字段级原文证据、
规则式可比性判断、人工审核、Markdown/CSV 导出及 Streamlit “实验知识库”工作区。
初期仅支持文本 PDF 的实验光学带隙，**不推断因果关系或材料机理**。
可在原五个工作区外选择新入口，原有单 Agent、协作 Agent 和 Materials Project 仍可使用。

- [操作和 API](docs/v0.9/usage.md)
- [基线与差距](docs/v0.9/baseline.md)
- [分阶段验收](docs/v0.9/acceptance.md)
- [科研局限](docs/v0.9/limitations.md)

完整真实科研验证仍需用户在本机导入具有许可的论文、运行模型和数据库，并建立独立人工标注数据集。
