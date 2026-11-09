# MatPilot V0.10 — PDF 版面解析与 MinerU 接入（实验性）

## 解析策略

- **PyMuPDF（默认）**：PDF 文本层、全角字符规范化、重复页眉页脚过滤、标题检测、简单双栏排序、章节识别；pdfplumber 继续补充表格。速度快，无需 GPU。
- **MinerU 4.x（可选）**：独立的 GPU/Python 环境，使用 `mineru-kit parse --format zip --tier standard`；MatPilot 读取 ZIP 内 `middle_json.json` 的原始页面与布局块，将正文、表格及带来源坐标的图注转为 `ParsedDocument`。图片字节和 Base64 永远不进入 RAG Chunk。
- **Chunk**：针对同一 PDF 来源块优先按段落与标点切分长文本；表格整体保留。跨来源块不合并，保证现有引用的 `block_id` 不失效。

MinerU 不加入 MatPilot 的 `pyproject.toml` 或 `uv.lock`，以免和 Python 3.13 主服务争夺显卡依赖和虚拟环境。

## Windows 配置

1. 确保独立 MinerU 环境确实存在，比如：
   `E:\AI Learning\matpilot_parser_benchmark\.venv\Scripts\mineru-kit.exe`
2. 在 **MatPilot 根目录的 `.env`** 末尾增加（请替换成实际路径）：

   ```dotenv
   MINERU_CLI_PATH=E:/AI Learning/matpilot_parser_benchmark/.venv/Scripts/mineru-kit.exe
   MINERU_TIMEOUT_SECONDS=1800
   ```

   Windows 下使用正斜线并不影响路径解析，同时减少反斜线转义干扰。

3. 使用原有方式分别启动 8000 后端与 8501 前端。改过 `.env` 后必须重启后端。

   ```powershell
   cd "E:\AI Learning\mat_pilot"
   uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
   # 另一个终端
   uv run streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
   ```

4. 论文解析 → 选择现有文献 → 展开“解析质量优化 · MinerU 高精度解析” → 点击“使用 MinerU 重新解析所选论文”。

**该操作为后台异步任务**，需要 GPU 模型启动；UI 最多轮询 30 分钟。它会创建一个全新的文献版本（新的 UUID），不覆盖旧论文与既有实验审核数据。原来的文献可以继续选择、比较；新版本需要重新提取实验和建立索引。

任务接口：`POST /api/v1/jobs/documents/mineru-reparse`，请求 `{"document_id":"已有文献 UUID"}`，返回 job_id；查询 `GET /api/v1/jobs/{job_id}`。

## 证据质量与限制

- 只从结构化 ZIP 读取带真实页码和 bbox 的块。缺少可靠坐标的块不编造位置，跳过并告警。
- MinerU 的 OCR 文本是模型对 PDF 的转写，必须人工核对原始 PDF，不能自动当成科研真值。
- 对扫描、双栏、长篇 PDF 的首次推理比较慢；不要把它放进同步上传 API。
- 解析文本和图片分离；不在数据库 JSON 中存放 Base64，图像文件保留与可视化将另行实现。
- MinerU 4.x 的数据结构可能随版本变化；此适配器优先使用 ZIP 中 `middle_json.json` 的 `pdf_info/para_blocks`。对于其他格式，先明确报错再补充适配，不猜测坐标。
- 现阶段不自动执行 MinerU 失败后降级和重新写库，以避免用户误以为已经完成高精度解析。
- 旧 PDF 与新 PDF 版本不共享块 ID。研究记录、人审状态、向量索引应明确区分版本。

## 本轮验收

按两篇已审论文建立基线：
- 氮气退火 TiO₂：标题正确、工艺章节完整、500–900℃ 与 3.98/3.97/3.96/3.73/3.30 eV 保留。
- CsPbBr₃/VO₂：双栏阅读顺序合理、章节完整、PL 540 nm 与约 2.3 eV 同上下文；排除背景段落约 2.2 eV 的错误归因。
- 每条科研实验数据的页码、块 ID 和引文需可回到 PDF 原页查验。

离线测试验证合成 MinerU ZIP 的结构转换与异常安全边界。**真实本地 MinerU ZIP → API → PostgreSQL → Chunk → 实验知识库**的全链路仍须运行验收，不能仅凭离线测试宣称完成。
