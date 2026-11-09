# MatPilot V0.9 基线与差距核对

基线分支：main（核对日期：2026-11-09）。

## 已有工程能力
- Python 3.13 / uv、FastAPI /api/v1、Streamlit 五个工作区。
- Materials Project 计算属性与晶体结构；OpenAlex 元数据发现。
- 文本 PDF 解析、页码块、表格、原始文件留存。
- 光学相关实验带隙单篇提取，引用原文复制、数值单位与身份字段验证。
- PostgreSQL mp_docs/mp_experiments SSOT、pgvector 索引、混合检索与可选 Rerank。
- LangGraph 单 Agent、Planner/材料专家/文献专家/Analysis/Reviewer、工具权限和预算。
- API key 租户隔离、进程内 job 状态和离线测试。

## 关键缺口
1. 单篇实验提取主要存一个 band_gap 和自然语言条件，缺少可筛选的样品、工艺、测量语义。
2. 文献原文检索不能替代样品/测试/数值关系核验。
3. 不支持按科学条件过滤、审核和跨论文的规则式比较。
4. 缺少独立跨论文标注集、科学家复核与人工耗时基线。
5. 扫描件、曲线数字化、Supplementary Information 解析尚未提供。

## V0.9 增量实现边界
- 新表 mp_knowledge_runs / mp_knowledge_observations / mp_knowledge_reviews；原表保持不变。
- 结构化抽取 opt-in；无法证明样品与数值关系的候选直接拒绝。
- 初版仅 optical_band_gap (eV)，不计算材料机理与因果。
- PostgreSQL + JSONB 存储结构化观察记录；尚非完整知识图谱/实体分表。
- 字段 status=not_extracted 不表示原文未报告。
- 仅支持人工审核状态，不实现机构级 OIDC / RBAC / 电子签章。
- 新增 API、受控 Agent tools、可比性引擎和 Streamlit 演示工作台。

## 运行限制与后续科研验收
本分支代码经远程 API 写入，未接触用户本机数据库、密钥和已上传的论文内容。
离线单元测试只能检验规则/契约，不能替代真实科研场景测评。
请使用具有许可的论文验证样品关联、物性测量定义和跨论文可比性。
