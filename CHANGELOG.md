# Changelog

本文件记录 MatPilot 对用户与运维可见的变更。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]

### Added

- **P1-a 可观测与限流**：`X-Request-ID`、审计日志、可选 `LOG_JSON`；`RATE_LIMIT_*` 令牌桶（默认关闭）；ServiceError 与 429 错误体均含 `request_id`。
- **P1-b Schema 治理**：`apply_schema` / Alembic；请求路径不再 DDL；可选 `VECTOR_HNSW`。
- **P2 契约与结构**：业务 API `/api/v1/...`；补全 response_model；共享 `LLMClient`；Agent 拆为 `tools` / `claims` / 编排。
- **P0-c 统一持久化（SSOT）**：配置 `DATABASE_URL` 后，文献与实验提取写入 `mp_docs` / `mp_experiments`；磁盘保留 PDF 原件与审计/导出文件。向量索引不再双写完整 `parsed`；有库时读路径不回退磁盘 JSON。迁移：`python -m scripts.migrate_docs_to_postgres`。无库时回退本地 JSON。
- **P0-b 长任务异步化**：`POST /api/v1/jobs/...` 返回 `202` + `job_id`；租户目录 `jobs/` 原子落盘；进程内 `JOB_WORKERS` 线程池。
- UI 长任务改为异步提交并轮询；同步 `/api/v1/agent/run` 等接口保留给 CLI/测试。
- 共享 `app/core/io.atomic_write_text`，Job / Agent / 材料与文献快照统一原子写。

- **P0-a 认证与租户隔离**：`AUTH_MODE=off|api_key`，`AUTH_API_KEYS=tenant_id:key,...`。
- 业务 API 经 Bearer API Key 解析为 `Principal(tenant_id)`；`/health` 与 `/health/ready` 不要求认证。
- 租户文件根目录：`{DATA_DIR}/tenants/{tenant_id}/`（documents、material_queries、literature_queries、agent_runs、jobs）。
- 向量表 `mp_documents` / `mp_chunks` 增加 `tenant_id`，检索与索引均按租户过滤。
- 迁移脚本 `python -m scripts.migrate_tenant_local`（扁平目录 → `tenants/local`，并回填 DB）。
- UI 通过环境变量 `MATPILOT_API_KEY` 附加 `Authorization` 头。
- Agent / 实验记录回读下沉到 service，API 层不再直接读磁盘文件。

### Changed

- 默认 `AUTH_MODE=off` 时使用隐式租户 `local`，路径落在 `tenants/local/`（与旧扁平布局不兼容，需跑迁移脚本）。
- 业务 HTTP 路径统一为 `/api/v1/...`；限流高成本前缀仅匹配 v1 路由。
- Comparison 请求/响应模型归入 `app/schemas/material.py`；`/health` 并入 `app/api/health.py`。
- 文档对齐现状：`README.md`、`docs/architecture.md`、`docs/api.md`、`docs/development.md`、`docs/collaboration.md`、`docs/github.md`、`docs/design/ui-ux-proposal.md`、`.env.example`。
- 离线测试 152+ 项。

### Planned

- **P3（可选）**：检索评测扩容与人审队列；跨进程 job 恢复仍属后续。
