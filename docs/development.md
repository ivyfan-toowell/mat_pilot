# 开发与验收记录

更新：2026-10-16。Python 3.13.15，按用户要求替换任务书的 3.12，uv.lock 固定依赖。

## 当前模块

| 模块 | 实现 | 边界 |
|---|---|---|
| 材料 | MP 实时查询、公式校验、详情/结构、来源单位、JSON/CSV | 材料记录尚未迁入数据库 |
| PDF | PyMuPDF + pdfplumber，页码/块/表格，原文件与失败状态 | OCR、复杂跨页表格未完成 |
| 实验 | 原文行号关联方法/条件，检查公式/数值/单位/样品，保留候选历史 | 需科研审核，未穷尽全文 |
| RAG | pgvector、BM25L、RRF、通义 Rerank、带引用回答、12 问评测 | 单篇论文试验，需扩大样本 |
| 界面 | FastAPI + Streamlit 五工作区 | Edge 真实完整流程通过 |
| Agent | 单 Agent / 自动路由 / 多角色协作，7 个允许工具，Planner / 两专家 / Analysis / Reviewer | 需更多任务评测，阶段落盘尚不支持自动恢复 |
| 部署 | 本机 DB Compose、localhost:5433、具名卷 | 全平台容器、认证、用户隔离未完成 |

## 真实材料验收

查询 ID：73c4c0ca-1917-4a1c-ad99-849ffddcf3d9；MP 数据库版本 2026.04.13。
TiO2 结果包括 mp-aaafhsgi、mp-aaabsdvu、mp-aaachguf，已支持实际返回的字母数字 MP-ID。
SDK LazyImport timeout 赋值问题已改为通过 MPRester 构造参数设置。

scripts.verify_materials 已验证快照、CSV、详情与结构 HTTP 请求成功。
首项结构 12 个原子，体积 204.9469218790116 Å³。
记录：data/acceptance/materials.json；查询结果：data/material_queries/。
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

原始文件、模型候选和结果保存在 data/documents/当前文献UUID/。
旧 ID 4dc41e39-3fa8-46ee-a01c-e491a0bc1e47 为改进表格前的历史输出，不作当前验收。
表格仍可能产生额外候选；原文匹配不代表科研人工审核完成。

## RAG 实现与验收

文本按页和块分割，默认 1800 字符、重叠 200；表格完整保留。UUID5 稳定块 ID。
每批最多 10 条向量化，校验返回索引、维度、非有限值和零向量。
文献 JSON 与向量块单事务替换；重复索引不会积累同文献旧块；模型或维度不一致拒绝混用。
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

137 项离线测试通过，Ruff 通过（2026-11-04）。新增目录回读、工作区切换、输入保留和缺失值展示测试。覆盖 HTTP、来源、持久化、PDF、伪造原文/数值拒绝、
分块、批量 Embedding、引用校验、依赖故障停止重试、引用修复预算、融合、重排及指标。
Jieba 0.42.1 首次导入在 Python 3.13 存在第三方正则转义 SyntaxWarning，不影响本次测试。

真实 Edge 浏览器四阶段报告：data/acceptance/browser/report.json。
真实复合 Agent：data/acceptance/agent.json，材料与论文工具调用、公式约束、材料对比及任务回读通过。
来源选择使用每个工具连续行号；最多一次修复，失败不返回未经校验的答案。
空字段/检索片段不能证明整篇论文未报告该信息，相关断言增加范围校验。

V0.1 本机主流程已通过，进入 V0.8。后续门槛：增加 3–5 篇论文、复杂文档/OCR、
扩大多角色任务、检索与文献样本评测，然后推进数据库持久化、图谱、报告、认证和完整容器部署。
OpenAlex 已配置并真实调用成功，提供在线元数据检索与快照回读，见 [论文发现](literature.md)。

2026-10-16 新增验收：OpenAlex 真实 HTTP/界面/科研助手报告在 data/acceptance/openalex/；
多角色协作报告在 data/acceptance/collaboration/，最终任务 5d0bfa4a-e196-4f70-bccc-e0d416534137，
8 次模型调用、4 次工具调用（含一次材料连接失败后的成功重试），检查了筛选条件、引用和阶段回读。
Reviewer 仍需人工补充审核；代码增加泛函/第一性原理归因和全文缺失断言的来源限制，
历史 63200a1a 与 5c7863ba 任务追加审查警告，不作最终通过案例。
