# 混合检索与真实论文试验

2026-10-15。Python 3.13，BM25L + Jieba，pgvector 精确余弦召回，RRF(k=60)，
通义 qwen3-rerank。默认仍为 Dense，不自动增加重排调用费用。

## 行为

知识库页面选择 Dense、BM25 或 Hybrid，可勾选 Rerank。
同一文献的解析内容继续保留页码、块、来源链接与许可。
NFKC 规范化仅用于分词，保留 TiO₂、TiO2-24 等样品名称和小数；原文不改写。
RRF 融合排名，不直接相加余弦和 BM25 分值。
仅去除同来源、同页、文本完全相同的重复证据，不合并数值不同的相似实验记录。
Dense 和 BM25 在独立连接上并行召回，合并后再可选重排。

Rerank 复用 DASHSCOPE_API_KEY，RERANK_MODEL 和 RERANK_URL 可配置。
[官方接口](https://help.aliyun.com/zh/model-studio/text-rerank-api) 对模型、地域和输入 Token 有限制；
当前默认模型为 qwen3-rerank。返回索引必须唯一、在候选范围内，分数必须有限且在 0–1。
失败明确报错；没有静默降级。返回文本与来源沿用原始候选，不采用模型改写的文档。

各分数独立返回；不适用的分数为 null。它们用于排序，不表示科学可信度。
当前 BM25 为有上限的内存索引，每次查询读取当前数据库；上限默认 10000 块，超过会警告。
这适用于本机开发语料；更大规模语料应持久化稀疏索引并评估更新开销。

## 试验与复现

数据为 [CC BY 4.0 开放论文 PMC7153365](https://pmc.ncbi.nlm.nih.gov/articles/PMC7153365/)，
DOI 10.3390/nano10030546。使用 83 个索引块、12 个中英文问题。
eval/retrieval_pilot.json 保存问题、相关证据块及原文短句；运行前检查论文 SHA256 和短句匹配。
开发者对照解析原文标注，尚无独立科研人员复审；不是独立盲测。

| 检索方式 | Recall@5 | MRR@5 | NDCG@5 |
|---|---:|---:|---:|
| Dense | 1.000 | 0.674 | 0.737 |
| BM25L | 0.653 | 0.556 | 0.551 |
| Hybrid / RRF | 0.917 | 0.746 | 0.772 |
| Hybrid + Rerank | 1.000 | 1.000 | 0.995 |

只做 RRF 在部分问题上损失前五条召回，例如比表面积问题，因此不声称混合检索总会改善结果。
本次重排改善了排序；单篇、12 问且部分相关块尚未穷尽，不能推断跨论文泛化效果。
Recall 按已标注相关块计算；MRR 计算首个相关块排名；NDCG 使用二值相关性。
同块重复分片占据排名位置但不重复计分。批量复用问题向量以控制费用，耗时不等于在线延迟。
原始排名、分数、标注、模型、版本与参数保存在 data/acceptance/retrieval-pilot.json。

```powershell
# 先解析并索引这篇论文，将 UUID 替换为本机输出。
uv run python -m scripts.evaluate_retrieval --document-id 377d0571-bae4-4667-9caa-9ba49e059dd8
# --skip-rerank 可跳过付费重排；Dense 仍调用 Embedding。
uv run python -m scripts.verify_hybrid --document-id 377d0571-bae4-4667-9caa-9ba49e059dd8
```

verify_hybrid 通过实际 HTTP 检查三种策略、就绪状态与字段约束，再用 Edge 在界面选择
Hybrid + Rerank、生成并检查 3.42 / 3.09 eV 引用回答，输出报告和截图。
验收材料是实际服务返回；tests/test_hybrid_retrieval.py 与 test_evaluation.py 则为明确的合成契约测试。
