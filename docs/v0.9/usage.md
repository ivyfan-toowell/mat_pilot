# MatPilot V0.9 试运行与验收说明

## 目标
将 TiO2 论文的样品级实验光学带隙、制备条件、测量方式和页码证据转为可查询观察记录，
再进行跨论文条件比较和报告导出。所有输出均需人工科研审核。

## 安装与数据库
在 Windows PowerShell 中使用 Python 3.13、uv、Docker Desktop 与现有 .env：
```powershell
uv sync --locked --all-extras
docker compose up -d --wait db
uv run --locked --all-extras alembic upgrade head
uv run --locked --all-extras uvicorn app.main:app --host 127.0.0.1 --port 8000
```
新开终端：推荐使用仓库根目录的 `streamlit_app.py` 入口，无需设置 `PYTHONPATH`；也可直接运行 PowerShell 脚本 `./start_ui.ps1`。
```powershell
uv run --locked --all-extras streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```
数据库仍是原 PostgreSQL；迁移添加三张表，旧 mp_experiments 不变。执行迁移前建议备份数据。

## 核心 API
- `POST /api/v1/experimental-knowledge/documents/{document_id}/extract`：付费模型执行 opt-in 样品级提取，仅存证据校验通过的记录
- `GET /api/v1/experimental-knowledge/observations?formula=TiO2&limit=100`：租户过滤查询
- `GET /api/v1/experimental-knowledge/observations/{id}`：观察记录与原文
- `POST /api/v1/experimental-knowledge/observations/{id}/review`：人工通过/拒绝及审核日志
- `POST /api/v1/experimental-knowledge/compare`：接收 `{"observation_ids":["uuid1","uuid2"]}`，返回可比性和规则理由
- `POST /api/v1/experimental-knowledge/report?format=markdown`：结构化事实、来源与比较理由
- `POST /api/v1/experimental-knowledge/report?format=csv`：实验记录 CSV

## Agent tools
原 LangGraph tools 白名单新增 `query_experiment_knowledge`、`compare_experimental_records`、
`build_cross_paper_analysis`。初版报告为确定性模板，不生成新的物性数值或因果结论。
原文来源和样品身份不完整时，需要人工补充证据；不保证所有论文都能产出结果。

## 科研验收
首先导入至少 3–5 篇具有处理许可的真实论文，记录 DOI、文件 hash。
独立标注样品、数值、工艺、测量方法和关联证据；对齐比较前后的人工耗时。
手动审查：空字段、跨论文同名样品、不同晶相、Tauc 假设、结果精度、失败提取后旧记录保留。
**未完成独立标注时不得宣称准确率或效率提升。**

## 当前局限
仅处理文本 PDF，不自动 OCR / 曲线数据化；采用 JSONB 样品级快照而非完整材料知识本体。
当前审核人由 API 请求提供，不提供独立的用户身份审计签名。
长时间提取走同步 API，可能受上游服务和代理超时限制；需要后续接入持久任务队列。
