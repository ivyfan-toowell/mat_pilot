# MatPilot 项目开发任务书

**项目名称：** MatPilot——面向半导体与光电材料科研的多模态 RAG 与多 Agent 智能分析平台

**项目方向：** AI for Science、AI Agent、Agentic RAG、材料信息学、科研数据智能处理

**开发周期：** 5 天

**开发模式：** 三阶段持续迭代，不规定各阶段的固定开发天数

**最终目标：** 完成一个具备科研文献解析、真实材料数据库查询、多 Agent 协作、科研分析、知识图谱、可视化、多用户管理及基础部署能力的可交付产品。

> **现状备注（2026-11-05）：** 下文大量内容为立项期规划，目录结构与部分里程碑可能与仓库现状不一致。
> 以代码与 `CHANGELOG.md` / `docs/architecture.md` 为准。已提前落地：API Key 租户隔离、进程内异步 jobs、
> 文献/实验 Postgres SSOT、`/api/v1`、`LLMClient`、Agent `tools`/`claims` 拆分。
> 仍待：P3 评测扩容与人审、OCR/多模态、OIDC/RBAC、知识图谱与完整容器部署。运行时为 **Python 3.13**。

---

# 一、项目背景与定位

## 1.1 项目背景

在半导体与光电材料科研过程中，研究人员需要查阅大量学术文献，提取论文中的材料成分、制备工艺、实验条件和性能指标，同时结合材料科学数据库进行候选材料筛选与分析。

这类科研任务涉及不同来源的数据，包括 PDF 论文、Word 实验报告、Excel 实验记录、科研图片，以及 Materials Project 等计算材料数据库。

目前主要存在以下问题：

1. 科研文献包含大量复杂表格、公式、图表和实验数据，难以直接进行结构化处理。
2. 同一种材料的实验参数分散在不同论文中，人工整理与比较成本较高。
3. 材料计算数据库与论文实验数据相互独立，缺乏统一的查询与分析入口。
4. 通用大模型可能生成缺少科学依据的材料性能数值，需要结合真实数据库和原文证据进行校验。
5. 复杂科研任务需要同时进行材料筛选、文献检索、数据分析和结果整合，具有明显的多步骤、多工具协作需求。

## 1.2 项目定位

MatPilot 定位为面向半导体与光电材料科研的 AI 智能分析平台。

平台通过多模态文档解析、科研知识库、真实材料数据库、Agent 工具调用和材料分析工具，辅助科研人员完成文献检索、实验数据提取、候选材料筛选和科研分析报告生成。

项目聚焦氧化物半导体材料，研究范围可以覆盖 TiO₂、ZnO、Fe₂O₃ 等常见材料体系。

项目强调真实数据、科研可追溯性和工程可验证性。

## 1.3 项目核心目标

### 业务目标

提供统一的科研信息处理入口，降低研究人员整理文献、查找材料属性和比较实验数据的工作成本。

### 技术目标

构建从科研文件处理、知识库检索，到 Agent 任务调度、科学工具调用和结果生成的完整业务流程。

### 产品目标

完成具备实际交互功能的 Web 产品，支持多用户使用、历史任务查看、科研数据可视化及基础容器化部署。

### 面试展示目标

重点体现以下能力：

- RAG 系统完整设计和性能优化。
- 科研文档结构化解析、清洗与入库。
- Function Calling 和复杂工具调度。
- LangGraph 多 Agent 协作架构。
- 材料科学数据库与领域工具集成。
- 科研数据校验、知识图谱与智能分析。
- AI 应用的工程化、可观测性和产品交付能力。

---

# 二、材料科研业务范围

## 2.1 研究方向

项目选择半导体与光电材料中的氧化物半导体作为主要研究对象。

重点研究以下材料属性：

| 材料属性 | 含义 | 在项目中的用途 |
|---|---|---|
| Band Gap | 电子带隙 | 初步筛选半导体材料 |
| Direct / Indirect Band Gap | 直接与间接带隙 | 分析电子跃迁及光学应用潜力 |
| Formation Energy | 形成能 | 了解材料形成的能量特征 |
| Energy Above Hull | 能量高出凸包 | 辅助判断热力学稳定性 |
| Crystal Structure | 晶体结构 | 了解材料原子排列与空间群 |
| Optical Properties | 光学性质 | 分析材料在光电领域的潜在应用 |
| Experimental Conditions | 实验条件 | 比较不同文献的实验结果 |

项目初期不需要独立运行 VASP 等第一性原理计算软件。

材料计算数据主要来自公开数据库，实验数据来自真实科研文献。

## 2.2 核心科研任务示例

用户输入：

筛选计算带隙在 1.5～3.0 eV、能量高出凸包不超过 0.05 eV/atom 的含氧半导体候选材料。结合相关科研文献，分析不同材料的结构、稳定性、实验性能及潜在光电应用价值。

系统需要完成：

1. 解析用户提出的材料筛选条件。
2. 查询 Materials Project 中的真实材料数据。
3. 获取材料带隙、形成能、稳定性及晶体结构信息。
4. 检索相关科研论文。
5. 提取论文中的实验性能和测试条件。
6. 比较计算数据与实验数据。
7. 分析候选材料的优点、局限和后续研究价值。
8. 生成具有明确来源的科研分析报告。

带隙和能量高出凸包是初步筛选指标。系统需要说明计算方法及数据局限，不能据此直接判定材料的实际器件性能。

---

# 三、整体开发策略

项目分为三个连续阶段：

| 阶段 | 版本 | 核心目标 |
|---|---|---|
| 第一阶段 | V0.1 MVP | 跑通真实材料查询、文献解析、RAG 和 Agent 工具调用的完整业务流程 |
| 第二阶段 | V0.8 增强版 | 完善多 Agent 编排、混合检索、多模态解析、数据校验、异常处理及评测 |
| 第三阶段 | V1.0 交付版 | 增加知识图谱、科研分析、可视化、多用户管理及生产化基础部署 |

三个阶段都属于五天开发范围。

采用先确保主流程可运行，再持续增加能力的策略。

每个阶段完成后立即进行功能验收，通过后进入下一阶段。

遇到复杂依赖问题时，优先采用轻量替代方案，保证全部核心业务可以运行。

五天内完成的生产部署以单机容器化部署、配置管理、持久化、健康检查和基础用户隔离为目标。高可用集群、完整安全审计及大规模并发优化不属于本轮验收范围。

---

# 四、第一阶段：V0.1 最小可行产品 MVP

## 4.1 阶段目标

完成材料科研 Agent 的最小闭环。

用户可以上传科研论文，建立知识库，查询真实材料属性，并通过自然语言让 Agent 调用相关工具完成科研问题回答。

第一阶段必须实现以下五个模块。

## 模块 1：真实材料数据库查询

### 功能要求

1. 对接 Materials Project API。
2. 支持按照元素、化学式、带隙及能量高出凸包筛选材料。
3. 获取材料 MP-ID、化学式、带隙、形成能和稳定性指标。
4. 使用 pymatgen 解析材料化学式和基础晶体结构。
5. 使用 pandas 整理查询结果。
6. 保存查询结果及查询参数。
7. 支持将材料结果导出为 CSV。

### 技术选型

- mp-api
- pymatgen
- pandas
- Pydantic

### 外部资源

- Materials Project 官方网站：https://materialsproject.org/
- API 文档：https://docs.materialsproject.org/downloading-data/using-the-api/getting-started
- mp-api：https://github.com/materialsproject/api
- pymatgen：https://pymatgen.org/

### 需要的 API

Materials Project API Key。

主要使用 `MPRester` 提供的材料查询接口：

- `materials.summary.search()`
- `get_structure_by_material_id()`

### 模块验收

输入材料筛选条件后，能够返回真实材料数据及来源 ID。

所有数据均标注单位及来源，查询失败或没有结果时能够正确反馈。

## 模块 2：科研文献解析与结构化处理

### 功能要求

1. 支持上传 PDF 科研论文。
2. 自动识别和提取标题、正文、章节、页码及表格。
3. 提取表格中的材料成分、实验参数和性能数值。
4. 清理页眉、页脚、异常换行、乱码和重复内容。
5. 将解析结果转换为 Markdown 和结构化 JSON。
6. 使用大模型提取材料化学式、带隙及实验条件。
7. 使用 Pydantic 校验提取结果。
8. 保留原始文档、页码、表格编号和证据内容。

### 技术选型

- PyMuPDF
- pdfplumber
- MinerU
- Pydantic
- LLM Structured Output

### 解析策略

文本型 PDF 优先尝试 PyMuPDF。

规则表格可以使用 pdfplumber。

具有复杂布局、双栏、公式或扫描页面的文档，使用 MinerU。

所有解析器都应输出统一的内部文档结构，包括文本块、表格、图片、页码及来源位置。

### 外部资源

- 3～5 篇真实且允许处理的科研论文。
- MinerU：https://github.com/opendatalab/MinerU
- arXiv：https://arxiv.org/

### 需要的 API

大模型 API，用于科研实验数据的结构化提取。

文档解析优先使用本地工具，减少外部服务依赖。

### 模块验收

至少可以完整解析一篇包含实验表格的半导体论文。

能够生成结构化实验记录，并定位对应原文内容。

## 模块 3：科研文献 RAG

### 功能要求

1. 对解析后的科研文本进行 Chunk 切分。
2. 保留文档 ID、标题、章节及页码。
3. 调用 Embedding 模型生成向量。
4. 将 Chunk 和对应元数据写入向量数据库。
5. 实现基础向量检索。
6. 将检索结果传递给大模型生成回答。
7. 展示答案引用的原始文献片段。

### 技术选型

- Embedding API
- PostgreSQL + pgvector
- LangChain 文档处理组件
- Python

### 数据库策略

优先使用 PostgreSQL + pgvector，统一管理结构化数据和向量数据。

如果已有稳定可复用的 Milvus 环境，也可以采用 Milvus 作为向量数据库。

具体选型在项目初始化时确定，避免重复搭建两套向量存储系统。

### 需要的 API

Embedding API。

可复用此前使用过的 text-embedding-v4 等模型。

### 模块验收

上传论文后能够完成解析、切分、向量化和入库。

用户能够使用自然语言检索论文，并获得带来源信息的回答。

## 模块 4：单 Agent 多工具调用

### 功能要求

1. 基于 LangGraph 构建主 Agent。
2. 使用 Function Calling 判断需要调用的工具。
3. 支持材料数据库查询工具。
4. 支持 RAG 文献检索工具。
5. 支持材料属性比较工具。
6. 允许 Agent 连续调用多个工具。
7. 将工具结果整理成科研问题回答。
8. 记录工具调用过程。

### 初期 Tool 清单

- `search_materials`
- `get_material_details`
- `search_papers`
- `compare_materials`

### 技术选型

- LangGraph
- LangChain
- Function Calling
- 支持工具调用的大模型

### 需要的 API

大模型 API、Materials Project API、RAG 检索服务。

### 模块验收

输入一个需要材料筛选和论文检索的复合问题，Agent 能够正确选择工具并整合结果。

## 模块 5：基础 Web 交互

### 功能要求

建立包含以下页面的基础 Web 界面：

1. 材料查询页面。
2. 科研论文上传页面。
3. RAG 文献问答页面。
4. AI Agent 科研对话页面。

能够展示用户输入、工具调用结果、材料表格和文献引用。

### 技术选型

- Streamlit
- FastAPI

Streamlit 负责交互界面，FastAPI 负责提供统一的后端业务接口。

### 模块验收

可以通过浏览器完整运行材料查询、论文上传、知识库问答和 Agent 科研任务。

## 第一阶段最终验收

必须跑通以下业务链路：

```text
用户上传科研论文
       ↓
文档解析与数据清洗
       ↓
实验数据结构化提取
       ↓
Chunk 切分与 Embedding
       ↓
科研文献知识库入库
       ↓
用户提出科研任务
       ↓
LangGraph Agent
       ↓
调用 Materials Project 与 RAG
       ↓
综合真实科研数据
       ↓
返回有来源的科研回答
```

这一阶段完成后，MatPilot 已经具备完整的核心业务功能。

---

# 五、第二阶段：V0.8 Agent 能力与工程增强

## 5.1 阶段目标

在 MVP 的基础上，进一步提升系统处理复杂科研任务的能力，以及 RAG 检索质量、数据可靠性和整体工程稳定性。

第二阶段重点实现七个模块。

## 模块 1：多 Agent 协作与复杂任务规划

### 功能要求

将第一阶段的单 Agent 扩展为具备明确职责分工的多 Agent 系统。

建议设计以下角色：

**Supervisor / Router**

负责识别科研任务类型、判断复杂程度及选择执行流程。

**Planner Agent**

负责将复杂科研任务拆解成文献检索、材料查询、数据分析等子任务。

**Literature Agent**

负责论文搜索、RAG 检索、文献证据整理。

**Materials Agent**

负责 Materials Project 查询、材料结构分析和候选材料筛选。

**Analysis Agent**

负责整合材料性能、科研实验数据和相关文献，形成初步分析结论。

**Reviewer**

负责检查材料属性数值、数据来源、引用关系和结论完整性。

### 技术选型

- LangGraph StateGraph
- LangChain Tools
- Pydantic
- Checkpointer

### 执行要求

1. 简单任务直接调用工具，不强制进入完整多 Agent 工作流。
2. 复杂任务由 Planner 拆解。
3. 无数据依赖的只读查询允许并行执行。
4. 存在前后依赖的任务按顺序执行。
5. Agent 之间传递结构化执行结果。
6. 支持执行轮数和超时控制。
7. 支持保存任务状态。

### 需要的资源与 API

复用已有大模型 API、材料数据库 API、RAG 服务，不额外强制引入付费服务。

### 模块验收

复杂科研任务能够被正确拆解和分配。

至少能展示两个专业 Agent 的协作，以及 Reviewer 的实际核验步骤。

## 模块 2：完善科研工具体系

### 功能要求

扩展 Agent 可调用工具：

| 工具 | 功能 |
|---|---|
| search_materials | 根据筛选条件查询材料 |
| get_material_details | 查询指定材料完整属性 |
| get_crystal_structure | 获取晶体结构 |
| search_papers | 检索本地论文知识库 |
| search_academic_papers | 查询在线学术文献元数据 |
| compare_materials | 比较材料性能 |
| query_experiments | 查询结构化实验数据 |
| validate_material_data | 检查材料数据与来源 |
| generate_material_chart | 生成材料属性图表 |

### 新增外部资源

OpenAlex API，用于搜索公开科研文献的标题、DOI、作者、发表年份等元数据。

官网：https://openalex.org/

需要 OpenAlex API Key；基础开发可使用免费额度。

全文处理需要另外确认开放获取链接及许可。

### 模块验收

系统能够根据任务需求选择对应工具，完成材料查询、文献检索、实验数据查询和数据比较。

## 模块 3：复杂文档和多模态解析

### 功能要求

在第一阶段 PDF 解析的基础上，增加以下能力：

**PDF**

支持双栏论文、扫描型 PDF、复杂表格和数学公式。

**Word**

解析段落、标题层级、表格和嵌入图片。

**Excel**

解析多个 Sheet、表头、行列关系、合并单元格及实验数值。

**图片**

使用 OCR 提取实验图片或扫描表格中的文字。

**数学公式**

识别并保存 LaTeX 表达式，保留公式编号及对应正文。

**科研图表**

提取图题、坐标轴和图例等信息，必要时利用视觉语言模型辅助理解。

### 技术选型

- MinerU
- PP-StructureV3
- python-docx
- openpyxl
- pandas
- PyMuPDF
- PaddleOCR
- 视觉语言模型 API（可选）

### 解析策略

MinerU 作为复杂文档的主解析工具。

PP-StructureV3 主要用于扫描表格、复杂单元格结构识别及解析结果交叉验证。

对同一类型复杂文档无需默认执行两套解析器，可以根据解析质量判断是否触发备用工具。

### 外部资源

- MinerU：https://github.com/opendatalab/MinerU
- PaddleOCR：https://github.com/PaddlePaddle/PaddleOCR
- PP-StructureV3 官方文档：https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html

### 模块验收

至少验证文本型 PDF、复杂表格 PDF、Word 和 Excel 四类输入。

扫描件 OCR 应能完成至少一个真实样例。

对于无法解析的内容，需要保留错误信息和原始文件，不生成未经验证的实验数据。

## 模块 4：混合检索与 Rerank 优化

### 功能要求

将第一阶段基础 RAG 扩展为 Hybrid RAG。

检索链路：

```text
用户问题
   ↓
Query 预处理
   ↓
并行检索
   ├── Dense Retrieval
   └── Sparse Retrieval
   ↓
RRF 融合
   ↓
Rerank 重排序
   ↓
Top N 文献证据
   ↓
LLM 生成回答
```

### 技术选型

- pgvector / Milvus
- BM25
- jieba
- RRF
- Rerank API

### 具体功能

1. 支持向量语义检索。
2. 支持 BM25 关键词检索。
3. 使用 RRF 融合两路结果。
4. 使用 Rerank 模型重排序。
5. 支持配置 Retrieval Top K 与 Rerank Top N。
6. 保留文档、页码和 Chunk 来源。
7. 对重复和高度相似片段进行去重。

### 需要的 API

Embedding API、Rerank API。

### 模块验收

能分别展示 Dense、Sparse、Hybrid 三种检索结果。

通过小规模评测集比较不同检索方式的 Recall@K、MRR 等指标。

## 模块 5：科研数据清洗与校验

### 功能要求

建立统一的科研数据质量控制流程。

**文档清洗**

去除乱码、重复文本、无意义换行、重复页眉页脚。

**表格清洗**

处理空值、异常行列、重复行、错位表头及合并单元格。

**材料字段标准化**

使用 pymatgen 解析化学式，统一属性名称、单位和字段格式。

**实验数据校验**

检查实验数值、单位、测试方法、实验条件和来源信息是否完整。

**来源交叉验证**

区分 Materials Project 计算结果与科研论文实验结果，不直接将二者合并。

**LLM 提取结果验证**

使用 Pydantic 和规则校验防止数据类型错误、字段遗漏及明显异常。

### 技术选型

- Pydantic
- pandas
- pymatgen
- Python 规则校验
- LLM Structured Output

### 模块验收

能够识别并标记缺失字段、错误数值、单位异常和来源不足的科研数据。

不允许模型自行补全缺少证据的实验数值。

## 模块 6：异常处理与 Agent 可靠性

### 功能要求

1. 为外部 API 设置超时。
2. 对临时网络错误增加有限重试。
3. 对频率限制采用退避策略。
4. 限制 Agent 最大执行轮数。
5. 控制工具并发数量。
6. 为只读工具提供并发执行能力。
7. 为具有副作用的工具增加权限和幂等控制。
8. 支持失败后保留任务状态。
9. 记录工具输入、输出、耗时和错误类型。
10. 对长时间运行的任务展示处理中状态。
11. 对关键状态更新增加检查点恢复。
12. 避免 Agent 在工具失败后无限重复调用。

### 技术选型

- LangGraph Checkpointer
- asyncio
- httpx
- tenacity
- Python logging

当前已有进程内 `JOB_WORKERS` 队列与租户级 job 落盘；仍不强制 Redis / arq。
若需跨进程抢占或崩溃后自动恢复执行，再引入独立后台队列。

### 模块验收

在模拟 API 超时、无结果、工具异常等情况下，系统能够终止、重试、降级或返回明确的失败原因。

## 模块 7：评测与可观测性

### 功能要求

建立基础评测体系，覆盖以下部分：

| 评测对象 | 核心指标 |
|---|---|
| PDF 解析 | 解析成功率、表格识别正确率 |
| 实验字段提取 | Precision、Recall、F1 |
| 向量检索 | Recall@K、Hit@K、MRR |
| 混合检索 | Recall@K、MRR、NDCG |
| Agent | 任务完成率、工具选择正确率 |
| 科研回答 | 来源引用正确率、数据一致性 |
| 工程性能 | 请求耗时、P95 延迟、Token 消耗 |

### 技术选型

- pytest
- 自定义 Evaluation 脚本
- Langfuse（有时间可集成）
- 结构化日志

### 评测数据

建议准备：

- 3～5 篇真实科研论文。
- 10～20 条人工核验的实验字段。
- 10～20 道 RAG 问答。
- 10 道科研 Agent 工具调用任务。

### 模块验收

能够生成真实的评测结果，记录系统失败案例，并对优化前后的结果进行对比。

不要求在五天内达到大型科研 Benchmark 水平，但必须建立可重复执行的测试方法。

## 第二阶段最终验收

完成以下增强业务链路：

```text
复杂科研任务
      │
      ▼
Supervisor / Router
      │
      ▼
Planner 任务规划
      │
      ├── Literature Agent
      │     ├── OpenAlex
      │     └── Hybrid RAG
      │
      ├── Materials Agent
      │     ├── Materials Project
      │     └── pymatgen
      │
      └── Analysis Agent
            ├── 科研数据比较
            └── 实验记录查询
      │
      ▼
科研证据汇总
      │
      ▼
Reviewer 数据核验
      │
      ▼
科研分析结果
```

经过第二阶段，系统应具备复杂科研任务拆分、多工具调用、多 Agent 协作、增强检索、科研数据校验和基本可靠性保障能力。

---

# 六、第三阶段：V1.0 可交付产品建设

## 6.1 阶段目标

在科研智能体核心能力稳定的基础上，增加知识组织、科研分析、可视化、多用户管理、持久化与部署能力，形成可以独立演示和交付使用的 Web 产品。

第三阶段重点实现六个模块。

## 模块 1：材料科研知识图谱

### 功能要求

从材料数据库和论文实验记录中构建基础科研知识图谱。

**核心实体**

- Material：材料。
- Paper：科研论文。
- Property：材料属性。
- Experiment：实验记录。
- Method：制备或测试方法。

**核心关系**

- 论文研究某种材料。
- 材料具有某类性能。
- 实验记录对应某种材料。
- 实验采用某种制备或测试方法。
- 实验结果来源于指定论文。

### 技术选型

优先采用 NetworkX + PostgreSQL 构建轻量科研知识图谱，避免额外数据库增加部署复杂度。

如果开发环境和时间允许，可以使用 Neo4j 存储实体关系。

### Agent 集成

新增图谱查询工具：

- `search_material_relations`
- `get_material_evidence_graph`

支持查询指定材料关联的科研论文、属性和实验记录。

### 模块验收

能够展示至少一种材料的关系图，并支持 Agent 根据图谱查询材料与文献之间的关系。

所有关键关系需要关联原始数据或文献证据。

## 模块 2：科研智能分析

### 功能要求

增加具有材料科研特点的数据分析能力。

主要包括：

1. 多候选材料属性比较。
2. 带隙和热力学稳定性联合筛选。
3. 同一种材料不同论文实验结果对比。
4. 实验数据与计算数据差异分析。
5. 候选材料排序。
6. 相关科研研究方向总结。
7. 生成候选实验研究建议。
8. 生成可溯源的科研分析报告。

### 技术选型

- pandas
- NumPy
- pymatgen
- LangGraph Analysis Agent
- LLM Structured Output

### 科研分析原则

数值计算和筛选规则由确定性 Python 代码执行。

LLM 主要用于整理研究依据、总结分析结果和生成文字说明。

对候选材料的研究价值评估需要注明筛选依据及不确定性。

### 模块验收

系统能够针对多个候选材料生成结构化对比表，并输出包含数据来源、研究优势、局限及后续验证建议的科研报告。

## 模块 3：高级科研数据可视化

### 功能要求

构建面向科研人员的可视化工作台。

主要增加：

**材料筛选图表**

带隙与 Energy Above Hull 散点图。

**材料性能比较**

柱状图、排序图及多属性对比表。

**晶体结构展示**

展示晶胞及原子排列信息。

**科研知识图谱**

可视化材料、论文、属性和实验之间的关系。

**Agent 执行过程**

展示任务规划、工具调用、执行状态和结果。

**科研文献证据**

支持查看论文来源、页码、表格和相关内容。

### 技术选型

- Streamlit
- Plotly
- pandas
- pymatgen
- NetworkX
- py3Dmol（可选）

### 模块验收

能够使用真实材料数据生成交互式科研图表。

支持至少一种材料的晶体结构或知识关系可视化，并展示相关证据来源。

## 模块 4：多用户与科研任务管理

### 功能要求

增加基础用户系统和科研工作空间。

支持：

1. 用户注册及登录。
2. 用户身份认证。
3. 不同用户的文档隔离。
4. 不同用户的聊天记录隔离。
5. 用户科研任务历史记录。
6. 文件上传与删除。
7. 用户科研报告保存。
8. 基础权限验证。

### 技术选型

- FastAPI
- PostgreSQL
- SQLAlchemy
- 密码哈希组件
- Session / Token Authentication

### 安全要求

用户密码必须进行安全哈希，不保存明文密码。

后端根据认证身份检查文档和任务归属，不能仅依赖前端界面实现隔离。

API Key 由服务端统一管理。

### 模块验收

至少使用两个测试账户验证：

- A 用户上传的私有论文不会出现在 B 用户知识库中。
- A 用户的会话和任务记录不会被 B 用户直接访问。
- 未认证请求不能访问受保护的接口。

此阶段实现基础多用户能力，不要求完成企业级统一身份认证。

## 模块 5：系统持久化与基础生产部署

### 功能要求

1. 使用 PostgreSQL 保存用户、材料记录、科研实验数据和任务信息。
2. 保存上传文件及解析产物。
3. 实现数据持久化。
4. 建立统一环境配置。
5. 实现健康检查接口。
6. 增加服务启动和关闭处理。
7. 使用 Docker 构建应用镜像。
8. 使用 Docker Compose 启动后端、前端及数据库。
9. 配置日志输出。
10. 编写部署说明。
11. 确保服务重启后已有数据仍可访问。

### 技术选型

- Docker
- Docker Compose
- FastAPI
- Streamlit
- PostgreSQL
- SQLAlchemy
- pgvector

### 部署策略

优先完成单机容器化部署。

不强制引入 Kubernetes、微服务集群、分布式缓存和复杂 CI/CD 平台。

如果文档解析依赖较大的推理模型，可以将解析服务作为独立进程部署，避免影响 Web 服务启动。

### 模块验收

可以依据 README 在目标开发环境启动服务。

能够从浏览器访问 MatPilot，并完成核心科研业务操作。

服务重启后，用户、论文和历史任务数据仍然存在。

## 模块 6：产品文档、交付与演示

### 功能要求

完成可交付项目所需的说明材料。

需要提供：

1. 项目 README。
2. 项目系统架构图。
3. 核心业务流程图。
4. API 接口说明。
5. 技术栈说明。
6. 环境变量模板。
7. 部署与运行说明。
8. 测试和评测结果。
9. 已知限制和后续扩展方向。
10. 3～5 分钟项目演示视频。
11. 简历项目描述。
12. 项目技术难点及面试问答材料。

### 模块验收

其他开发者可以按照说明启动项目，了解系统核心模块并完成主要演示任务。

## 第三阶段最终验收

在第二阶段 Agent 能力的基础上，增加：

```text
MatPilot Web 平台
        │
        ├── 用户认证与科研工作空间
        │
        ├── 材料智能筛选
        │
        ├── 多模态科研文档解析
        │
        ├── Agentic RAG
        │
        ├── 多 Agent 科研分析
        │
        ├── 材料知识图谱
        │
        ├── 科研可视化
        │
        ├── 研究报告生成
        │
        └── 历史任务管理
                │
                ▼
          FastAPI 服务层
                │
                ▼
       PostgreSQL / pgvector
                │
                ▼
        Docker 单机部署
```

最终形成具备基本用户管理、科研任务处理、科研数据分析和部署能力的 MatPilot V1.0。

---

# 七、项目整体技术栈

| 领域 | 主要技术 |
|---|---|
| 开发语言 | Python 3.13 |
| 项目管理 | uv |
| 后端框架 | FastAPI |
| 前端界面 | Streamlit |
| Agent 编排 | LangGraph |
| LLM 调用 | 支持 Function Calling 的通义千问等模型 |
| Embedding | text-embedding-v4 或兼容模型 |
| 向量数据库 | PostgreSQL + pgvector |
| 关键词检索 | BM25 + jieba |
| 融合检索 | RRF |
| 精排 | Rerank API |
| PDF 解析 | PyMuPDF、pdfplumber |
| 复杂文档解析 | MinerU |
| OCR 与表格识别 | PaddleOCR、PP-StructureV3 |
| Word / Excel | python-docx、openpyxl、pandas |
| 结构化输出 | Pydantic |
| 材料科研 API | Materials Project、OpenAlex |
| 材料信息学 | pymatgen |
| 数据处理 | pandas、NumPy |
| 知识图谱 | NetworkX，兼容 Neo4j 扩展 |
| 图表可视化 | Plotly |
| 数据持久化 | PostgreSQL、SQLAlchemy |
| 自动化测试 | pytest |
| 任务可观测性 | logging，可扩展 Langfuse |
| 部署 | Docker Compose |

技术栈以减少重复基础设施为原则。

项目采用一个主要关系型数据库、一个统一后端服务和一个 Web 界面。

Milvus、Neo4j、Redis 等可以通过适配器扩展，但不强制同时部署。

---

# 八、API 与外部资源汇总

## 8.1 必备 API

| API | 具体用途 | 涉及阶段 |
|---|---|---|
| Materials Project API | 材料计算属性查询 | 第一、二、三阶段 |
| LLM API | 文档字段提取、Agent 决策、科研报告 | 全阶段 |
| Embedding API | 文档向量化和语义检索 | 全阶段 |

## 8.2 增强 API

| API | 具体用途 | 涉及阶段 |
|---|---|---|
| OpenAlex API | 学术论文元数据检索 | 第二、三阶段 |
| Rerank API | 检索结果精排 | 第二、三阶段 |
| 视觉语言模型 API | 复杂科研图片和图表辅助理解 | 第二阶段 |

## 8.3 本地依赖资源

- PostgreSQL 与 pgvector。
- MinerU 本地解析环境。
- PP-StructureV3 运行环境。
- Docker Desktop。
- Python 3.13 虚拟环境（uv + uv.lock）。
- 允许处理的开放科研论文。
- 真实材料数据库查询结果。
- 小规模人工标注测试集。

## 8.4 资源准备要求

开发启动时需要：

1. 确认大模型及 Embedding API 可用。
2. 申请 Materials Project API Key。
3. 准备至少 3～5 篇真实科研论文。
4. 检查本机 Python、Docker、PostgreSQL 环境。
5. 确认 MinerU 的安装及推理方式。
6. 规划模型调用费用和 API 配额。
7. 为 OpenAlex、Rerank 和多模态模型配置可选接口。

外部 API 的实际使用量应受到限制，文献与材料查询结果可以进行缓存。

---

# 九、完整代码结构规划

建议项目采用如下目录结构：

```text
matpilot/
│
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   ├── auth.py
│   │   ├── chat.py
│   │   ├── materials.py
│   │   ├── documents.py
│   │   ├── research.py
│   │   └── health.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── security.py
│   │
│   ├── schemas/
│   │   ├── material.py
│   │   ├── experiment.py
│   │   ├── document.py
│   │   ├── user.py
│   │   └── research.py
│   │
│   ├── ingestion/
│   │   ├── pipeline.py
│   │   ├── parsers/
│   │   │   ├── pdf_parser.py
│   │   │   ├── mineru_parser.py
│   │   │   ├── paddle_parser.py
│   │   │   └── office_parser.py
│   │   ├── cleaner.py
│   │   ├── extractor.py
│   │   ├── validator.py
│   │   └── chunker.py
│   │
│   ├── rag/
│   │   ├── embedding.py
│   │   ├── vector_store.py
│   │   ├── bm25_store.py
│   │   ├── hybrid_search.py
│   │   ├── reranker.py
│   │   └── retriever.py
│   │
│   ├── science/
│   │   ├── materials_project.py
│   │   ├── composition.py
│   │   ├── crystal.py
│   │   ├── screening.py
│   │   └── analysis.py
│   │
│   ├── tools/
│   │   ├── material_tools.py
│   │   ├── literature_tools.py
│   │   ├── experiment_tools.py
│   │   └── graph_tools.py
│   │
│   ├── agents/
│   │   ├── state.py
│   │   ├── supervisor.py
│   │   ├── planner.py
│   │   ├── literature_agent.py
│   │   ├── materials_agent.py
│   │   ├── analysis_agent.py
│   │   ├── reviewer.py
│   │   └── graph.py
│   │
│   ├── knowledge_graph/
│   │   ├── entities.py
│   │   ├── relations.py
│   │   ├── builder.py
│   │   └── query.py
│   │
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── repository.py
│   │
│   └── services/
│       ├── user_service.py
│       ├── document_service.py
│       └── research_service.py
│
├── ui/
│   ├── app.py
│   ├── pages/
│   │   ├── materials.py
│   │   ├── documents.py
│   │   ├── rag_chat.py
│   │   ├── research_agent.py
│   │   └── dashboard.py
│   └── components/
│       ├── charts.py
│       └── graph_view.py
│
├── evaluation/
│   ├── datasets/
│   ├── retrieval_eval.py
│   ├── extraction_eval.py
│   └── agent_eval.py
│
├── tests/
├── scripts/
├── data/
├── docs/
│
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

目录是最终结构规划，实际开发时逐阶段创建和完善。

禁止一次性创建大量没有实现逻辑的空文件。

---

# 十、核心数据模型设计

## 10.1 材料信息 Material

包含：

- material_id
- formula
- band_gap
- formation_energy_per_atom
- energy_above_hull
- crystal_structure
- source_database
- data_version
- retrieved_at

## 10.2 科研论文 Paper

包含：

- paper_id
- title
- authors
- doi
- publication_year
- source_url
- file_path
- owner_id
- parsing_status

## 10.3 实验记录 Experiment

包含：

- experiment_id
- paper_id
- material_formula
- property_name
- property_value
- property_unit
- experimental_method
- experimental_conditions
- page_number
- evidence_text
- verification_status

## 10.4 文献 Chunk

包含：

- chunk_id
- document_id
- owner_id
- content
- section_title
- page_number
- content_type
- embedding
- source_reference

## 10.5 科研任务 ResearchTask

包含：

- task_id
- user_id
- research_query
- task_status
- tool_calls
- results
- report
- created_at
- completed_at

## 10.6 知识图谱实体与关系

包含：

- entity_id
- entity_type
- entity_name
- relation_type
- target_entity_id
- source_reference
- confidence

所有实验数据和科研结论都需要保留来源。

---

# 十一、开发原则与验收方式

## 11.1 开发原则

1. 三个阶段全部纳入五天内的开发目标。
2. 不按照固定天数分配任务，由实际完成情况决定推进速度。
3. 优先打通完整业务流程，再增加复杂功能。
4. 每完成一个模块立即测试。
5. 避免重复实现成熟框架已有的能力。
6. 对科研领域的关键计算使用可验证的程序逻辑。
7. 所有材料数据来自真实科研资源。
8. 保留实验数据与计算数据之间的区别。
9. 每次技术选型优先考虑开发效率、稳定性和可解释性。
10. 及时检查官方文档及依赖版本，避免使用过时代码。

## 11.2 主要验收场景

**场景一：材料性能智能筛选**

用户输入材料筛选条件，系统调用真实材料数据库，展示候选材料和属性对比图。

**场景二：科研论文解析与实验数据提取**

上传论文，识别复杂表格和实验条件，将数据整理成结构化记录。

**场景三：Agentic RAG 科研问答**

用户提出涉及多个文献的科研问题，系统通过混合检索和 Rerank 返回证据并生成回答。

**场景四：多 Agent 科研任务**

用户提出复合材料研究任务，多个 Agent 协作完成查询、检索、分析和核验。

**场景五：科研知识图谱**

查询指定材料相关的论文、性能和实验关系，并展示关系图。

**场景六：可交付产品验证**

完成不同用户的数据隔离测试、历史任务持久化测试和 Docker 部署测试。

## 11.3 最终交付标准

MatPilot V1.0 应交付：

- 完整源代码。
- 可运行的 Web 平台。
- 真实材料数据库查询能力。
- 科研文献解析与结构化数据处理。
- RAG 检索与来源溯源。
- 多 Agent 科研任务编排。
- 材料科学工具调用。
- 科研数据校验和基本评测。
- 基础材料知识图谱。
- 科研数据可视化。
- 多用户管理和数据隔离。
- 单机容器化部署。
- README 和 API 文档。
- 系统架构图。
- 演示视频。
- 简历项目介绍及面试技术讲解材料。

所有已完成能力必须通过实际运行或测试证明，不能仅以创建模块文件或演示静态页面作为完成依据。

---

# 十二、开发风险与范围控制

由于开发周期只有五天，三个阶段都需要采用精简实现。

针对复杂模块设定以下最低可验收范围：

| 功能模块 | 五天版本的最低可验收实现 |
|---|---|
| 多 Agent | Supervisor、至少两个专业 Agent 和 Reviewer 能实际协作 |
| 复杂文档解析 | PDF、Word、Excel 解析及至少一个复杂表格或 OCR 示例 |
| 混合检索 | Dense + BM25 + RRF，并提供可运行的 Rerank |
| 科研数据校验 | 化学式、单位、缺失值和证据来源校验 |
| 知识图谱 | 实体、关系、数据来源及一种关系查询 |
| 科研分析 | 候选材料筛选、属性比较及来源明确的研究报告 |
| 高级可视化 | 交互式材料图表与至少一种结构或关系图 |
| 多用户管理 | 两个用户的认证、文档隔离和历史记录隔离 |
| 生产部署基础 | Docker Compose、持久化、健康检查、环境变量管理 |
| 评测 | 小规模真实数据集及可重复运行的评测脚本 |

如果某项功能开发成本超出预期，应缩小该模块的实现范围，优先保留端到端能力和可测试性。

禁止为了追求功能数量而牺牲真实数据、来源引用和核心流程稳定性。

---

# 十三、新对话开发执行要求

本任务书将作为 MatPilot 新项目的主要开发依据。

新对话中的 AI 开发助手需要严格遵循以下要求：

1. 从零创建 MatPilot 项目，先检查本地环境和可复用资源。
2. 首先完成 V0.1 MVP，跑通材料数据库、文献处理、RAG 与 Agent 的完整链路。
3. MVP 验收成功后，继续完成 V0.8，重点提升 Agent 调度、检索质量、文档处理及可靠性。
4. 随后完成 V1.0，增加知识图谱、科研分析、可视化、多用户和部署能力。
5. 三个阶段的总体开发周期为五天，不按固定天数安排阶段任务。
6. 每开发一个模块，说明模块在整体架构中的位置、关键函数及调用关系。
7. 代码需要提供必要的类型注解、异常处理、日志和测试。
8. 对外部库的版本和 API 用法进行官方文档核对。
9. 对出现的环境问题提供具体的 Windows PowerShell 解决方法。
10. 不要一次性生成完整项目代码，应逐模块开发、测试并验收。
11. 如果已有模块可复用，优先复用成熟实现或技术方案，减少重复开发。
12. 对材料科学概念、参数及科研数据进行必要解释，帮助开发者在技术面试中准确表达。
13. 每完成一个阶段，整理已完成模块、运行测试、关键难点、存在的问题和下一阶段任务。
14. 项目推进始终以五天内形成完整可运行的 V1.0 作品为目标。
15. 对尚未完成或未通过测试的功能进行明确标注，禁止虚构功能完成情况或评测指标。

---

# 十四、项目启动任务

新的对话开始后，请先进行以下工作：

**第一步：检查开发环境**

确认 Windows、Python、uv、Docker、PostgreSQL 和已有模型 API 的可用情况。

**第二步：确认项目技术选型**

根据现有环境确定数据库、文档解析器、Embedding 模型和 Agent 框架的具体实现方案。

**第三步：初始化项目**

创建 MatPilot 根目录、虚拟环境、基础配置、日志模块及必要的项目文件。

**第四步：接入真实材料数据库**

配置 Materials Project API，完成第一次真实的半导体材料属性查询。

**第五步：推进 MVP 业务闭环**

在材料查询基础上继续实现文献解析、RAG 和 Agent 工具调用。

当 MVP 通过验收后，立即进入第二阶段和第三阶段，直到完成 V1.0。

**现在请按照本任务书，从 MatPilot 项目初始化与开发环境检查开始，逐步指导我完成整个项目。**
