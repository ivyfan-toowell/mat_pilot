# 开发与验收记录

更新：2026-11-05。Python 3.13，uv.lock 固定依赖。企业化 P0–P2 已落地；下一可选切片为 P3。

## 当前模块

| 模块 | 实现 | 边界 |
|---|---|---|
| 材料 | MP 实时查询、公式校验、详情/结构、来源单位、租户目录 JSON/CSV | 材料记录尚未迁入数据库 |
| PDF | PyMuPDF + pdfplumber，页码/块/表格，原文件与失败状态 | OCR、复杂跨页表格未完成 |
| 实验 | 原文行号关联方法/条件，检查公式/数值/单位/样品，保留候选历史；有库时 SSOT 为 `mp_experiments` | 需科研审核，未穷尽全文 |
| RAG | pgvector、BM25L、RRF、通义 Rerank、带引用回答、12 问评测；索引与全文表分离 | 单篇论文试验，需扩大样本（P3） |
| 界面 | FastAPI `/api/v1` + Streamlit；长任务走 jobs 轮询 | Edge 真实完整流程通过 |
| Agent | `research` / `tools` / `claims` + 多角色协作；进程内 JobWorker | 需更多任务评测；无跨进程自动恢复 |
| 部署 | 本机 DB Compose、API Key 租户隔离、限流/审计可选 | 全平台容器、OIDC/RBAC/RLS 未完成 |

## 真实材料验收

查询 ID：73c4c0ca-1917-4a1c-ad99-849ffddcf3d9；MP 数据库版本 2026.04.13。
TiO2 结果包括 mp-aaafhsgi、mp-aaabsdvu、mp-aaachguf，已支持实际返回的字母数字 MP-ID。
SDK LazyImport timeout 赋值问题已改为通过 MPRester 构造参数设置。

scripts.verify_materials 已验证快照、CSV、详情与结构 HTTP 请求成功。
首项结构 12 个原子，体积 204.9469218790116 Å³。
记录：data/acceptance/materials.json；查询结果：`data/tenants/local/material_queries/`。
qwen-plus 和 text-embedding-v4（1024 维）已真实调用成功。

## 真实文献验收

Effects of Particle Size on the Structure and Photocatalytic Performance by Alkali-Treated TiO2，
Nanomaterials 2020, 10, 546，DOI 10.3390/nano10030546。
[原文与 CC BY 4.0 许可](https://pmc.ncbi.nlm.nih.gov/articles/PMC7153365/)。
下载脚本拒绝伪装 PDF 的 HTML，最终使用出版社官方 PDF。

- 文件 data/sample_papers/PMC7153365.pdf：14 页，3,596,715 字节。
- SHA256：462e8e749a86098c12b92a8610ca83062fc4dd5f4d757f8a18a98cf82ffe7816。
- 当前文献 ID：377d0571-bae4-4667-9caa-9ba49e059dd8，76 个证据块。
- 第 5 页表 1 已定位并保留表头、样品行和原文。
- 带隙：TiO2 3.27、TiO2-3 3.26、TiO2-12 3.16、TiO2-24 3.42、TiO2-48 3.09 eV。
- 每项保留表格及第 6 页叙述证据，状态 evidence_matched_needs_review。
- 方法和条件选择原文行号，再由服务复制证据；当前关联 DRS、Tauc/Kubelka-Munk 和波长范围。
- 不同解析/提取批次独立保存；历史缺少证据的字段仍为 null，不补写科学数据。
- context_truncated=true，不能声称穷尽全文数据。

原始 PDF、模型候选与审计文件保存在 `data/tenants/{tenant_id}/documents/{文献UUID}/`。
配置 `DATABASE_URL` 后，解析与实验元数据以 `mp_docs` / `mp_experiments` 为准，不再静默回退磁盘 JSON。
旧 ID 4dc41e39-3fa8-46ee-a01c-e491a0bc1e47 为改进表格前的历史输出，不作当前验收。
表格仍可能产生额外候选；原文匹配不代表科研人工审核完成。

## RAG 实现与验收

文本按页和块分割，默认 1800 字符、重叠 200；表格完整保留。UUID5 稳定块 ID。
每批最多 10 条向量化，校验返回索引、维度、非有限值和零向量。
向量侧单事务替换索引登记 stub 与块（全文在 DocumentStore / 本地 JSON）；重复索引不会积累同文献旧块；模型或维度不一致拒绝混用。
Dense 使用精确余弦检索，新增 BM25L、RRF 融合及可选 qwen3-rerank。
来源保留文献、页码、块、原文、链接和许可；分数按类别独立返回。
每条结论提交引文，服务校验来源编号及原文匹配；证据不足时拒答。
引用校验不能证明所有模型解释均被原文科学蕴含。

~~~powershell
# 会调用已配置的模型服务，产生调用费用。
uv run python -m scripts.verify_knowledge --document-id 377d0571-bae4-4667-9caa-9ba49e059dd8
~~~

本机真实 HTTP 验收通过：写入 83 个向量块，重连数据库计数一致，检索返回 8 条证据，
回答 TiO2-24 为 3.42 eV、TiO2-48 为 3.09 eV，引用表 1 及相关原文。
报告 data/acceptance/knowledge.json 保留问题、检索、答案、引文和索引信息。
另完成 12 问 Dense/BM25/Hybrid/Hybrid+Rerank 对照，详见 [检索记录](retrieval.md)。
范围仍为单篇论文，不代表独立盲测或跨论文泛化能力。

## 测试与下一门槛

历史节点：2026-11-04 曾达 137 项；截至 2026-11-05 企业化后 **152+** 项离线测试通过，Ruff 通过。
覆盖 HTTP、认证租户、异步 jobs、SSOT、request_id/限流、来源、持久化、PDF、伪造原文/数值拒绝、
分块、批量 Embedding、引用校验、依赖故障停止重试、引用修复预算、融合、重排及指标。
Jieba 0.42.1 首次导入在 Python 3.13 存在第三方正则转义 SyntaxWarning，不影响本次测试。

真实 Edge 浏览器四阶段报告：data/acceptance/browser/report.json。
真实复合 Agent：data/acceptance/agent.json，材料与论文工具调用、公式约束、材料对比及任务回读通过。
来源选择使用每个工具连续行号；最多一次修复，失败不返回未经校验的答案。
空字段/检索片段不能证明整篇论文未报告该信息，相关断言增加范围校验。

V0.1 本机主流程与企业化 P0–P2 已通过。后续门槛（含 P3）：增加 3–5 篇论文、复杂文档/OCR、
扩大多角色任务与人审队列、检索评测扩容，再推进图谱、报告和完整容器部署。

## 企业改造记录

### 2026-11-05 · P0-a 认证与租户隔离

- 新增 `app/core/auth.py`：`Principal`、`AUTH_MODE=off|api_key`、Bearer 校验（`hmac.compare_digest`）。
- 租户文件根：`tenant_data_dir` → `data/tenants/{tenant_id}/`；向量表增加 `tenant_id`。
- API 直读文件下沉到 `DocumentService` / `catalog_service`。
- 迁移：`uv run python -m scripts.migrate_tenant_local`。
- 测试：`tests/test_auth.py`（未授权 401、跨租户 404、`off` 模式 local 根）。
- 验收：`uv run --locked --all-extras pytest -q` → **140 passed**；`ruff check .` 通过（2026-11-05）。
- 变更明细见根目录 [CHANGELOG.md](../CHANGELOG.md)。
- 状态：**Done**。下一切片曾为 P0-b。

### 2026-11-05 · P0-b 长任务异步化

- 新增 `app/schemas/job.py`、`app/services/job_service.py`、`app/api/jobs.py`（前缀 `/api/v1/jobs`）。
- lifespan 启动/停止 `JobWorker`；配置项 `JOB_WORKERS`。
- UI：`run_job` / `wait_job` 提交并轮询；同步 API 保留。
- 测试：`tests/test_jobs.py`（202、失败落盘、租户隔离、索引缺文献、同步兼容）。
- 验收：`pytest -q` → **146 passed**；`ruff check .` 通过（2026-11-05）。
- 状态：**Done**。

### 2026-11-05 · P0-c 统一持久化

- 新增 `app/services/db.py`、`app/services/document_store.py`；`DocumentService` 在有库时写 `mp_docs`。
- `VectorStore.replace` 仅写索引 stub，消除与磁盘/库的全文双写；有库时读路径不回退 JSON。
- 迁移：`uv run python -m scripts.migrate_docs_to_postgres`。
- 测试：`tests/test_document_store.py`；无库路径回归仍走本地 JSON。
- 验收：`pytest -q` → **148 passed**；`ruff check .` 通过（2026-11-05）。
- 状态：**Done**。

### 2026-11-05 · P1 + P2

- P1-a：`RequestContextMiddleware` / `RateLimitMiddleware`；`LOG_JSON`；错误体（含 429）`request_id`。
- P1-b：请求路径禁用 DDL；`SCHEMA_AUTO_APPLY` + Alembic；`VECTOR_HNSW`。
- P2：`/api/v1`；`LLMClient`；`app/agents/{tools,claims,research}.py`；补全 response_model。
- 验收：`pytest -q` → **152+ passed**；`ruff check .` 通过。
- 状态：**Done**。下一可选切片：**P3 评测扩容与人审队列**。

### 2026-11-05 · 硬化后清理

- 收敛原子写（`app/core/io.py`）、去掉 research 再导出、Comparison schema 归入 `schemas/material`、
  限流前缀对齐 `/api/v1`、health 统一进 `api/health.py`、文档与 CHANGELOG 对齐现状。
OpenAlex 已配置并真实调用成功，提供在线元数据检索与快照回读，见 [论文发现](literature.md)。

2026-10-16 新增验收：OpenAlex 真实 HTTP/界面/科研助手报告在 data/acceptance/openalex/；
多角色协作报告在 data/acceptance/collaboration/，最终任务 5d0bfa4a-e196-4f70-bccc-e0d416534137，
8 次模型调用、4 次工具调用（含一次材料连接失败后的成功重试），检查了筛选条件、引用和阶段回读。
Reviewer 仍需人工补充审核；代码增加泛函/第一性原理归因和全文缺失断言的来源限制，
历史 63200a1a 与 5c7863ba 任务追加审查警告，不作最终通过案例。
