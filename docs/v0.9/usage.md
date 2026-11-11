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

## 文献名称与作者

文献选择列表按「第一作者 · 论文标题」显示，并保留解析引擎和版本标识。
上传时从 PDF 元数据或首页作者行读取作者；无法识别时显示「作者待补充」。
进入「论文解析」→「编辑论文信息」可以校正标题和作者（每行一位）。
保存不会重新解析、提取或调用模型；文献 ID、原文证据和已有实验记录保留。

快捷选择列表最多显示 10 条记录。点击「查看更多 · 全部已解析论文」进入全部论文，
可按作者、标题或文件名搜索，每页显示 10 条，并打开或删除指定解析版本。
删除会移入回收站，从文献列表与新检索中隐藏；原文、实验记录及审核信息保留，
可在全部论文的「回收站」中恢复。其他解析版本不受影响。

侧栏的「页面动效」控制进入工作区时的卡片移动：点击切换后立即从下方向上平滑到位，
约 0.62 秒完成，全程保持可见。关闭后直接显示页面；填写表单不会重复播放。

## 核心 API
- `PATCH /api/v1/documents/{document_id}/metadata`：保存 `{"title":"论文标题","authors":["作者甲","作者乙"]}`
- `GET /api/v1/documents/catalog?limit=10&offset=0&q=关键词&deleted=false`：分页浏览论文
- `DELETE /api/v1/documents/{document_id}`：将一个解析版本移入回收站
- `POST /api/v1/documents/{document_id}/restore`：恢复解析版本
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
