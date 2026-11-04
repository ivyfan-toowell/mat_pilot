# MatPilot 本机 API

运行后以 `/docs` 和 `/openapi.json` 为机器可读接口契约。
当前仅供本机单人开发，未实现认证和私有数据隔离。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | /health | 进程存活，不代表外部资源就绪 |
| GET | /health/ready | 检查数据库连接和必需配置；不付费探测模型 |
| POST | /api/materials/search | 元素、化学式、带隙和凸包能量筛选，保存快照 |
| GET | /api/materials/queries/{query_id} | 读取已保存查询 |
| GET | /api/materials/queries/{query_id}/csv | 导出快照 CSV，不再次查询 MP |
| GET | /api/materials/{material_id} | 按 MP-ID 获取材料详情 |
| GET | /api/materials/{material_id}/structure | 晶胞参数、体积与 pymatgen 结构 JSON |
| POST | /api/materials/compare | 对比 query_id 对应的材料快照 |
| POST | /api/documents | multipart PDF 上传，含 source_url / license_name |
| GET | /api/documents/{document_id} | 读取页码、块和来源 |
| POST | /api/documents/{document_id}/extract | 提取带原文证据的实验记录 |
| POST | /api/knowledge/documents/{document_id}/index | 分块、向量化并事务替换索引 |
| POST | /api/knowledge/search | Dense / BM25 / Hybrid 及可选 Rerank |
| POST | /api/knowledge/answer | 检索后生成带原文引用的回答 |
| POST | /api/literature/search | 在线论文元数据检索，支持 DOI/关键词/年份/OA |
| GET | /api/literature/queries/{query_id} | 回读论文元数据快照 |
| POST | /api/agent/run | 有工具预算的 LangGraph 科研任务 |
| GET | /api/agent/runs/{run_id}/checkpoint | 回读协作阶段状态 |
| GET | /api/agent/runs/{run_id} | 回读任务、工具轨迹和引文 |

搜索请求示例：

```json
{
  "elements": ["O"],
  "formula": null,
  "band_gap_min": 1.5,
  "band_gap_max": 3.0,
  "energy_above_hull_max": 0.05,
  "limit": 20
}
```

结果包含 query_id、原始查询参数、materials、单位、时间戳、来源及警告。
空结果是合法的 200 响应。达到条数上限提示可能存在更多记录，不代表完整排名。
计算缺失值保持 null，不生成额外数值。

422：请求字段/MP-ID 无效。503：缺少 MP Key 或存储不可写。
502：上游失败或数据校验失败。404：查询快照/材料/结构不存在。
服务错误采用 `{"error":{"code":"...","message":"..."}}`，
FastAPI 字段错误使用标准 `detail` 格式。不得向客户端返回密钥或完整上游异常内容。

知识库 search 与 answer 共用请求：

```json
{
  "question": "TiO2-24 与 TiO2-48 的实验带隙各是多少？",
  "document_id": null,
  "retrieval_mode": "hybrid",
  "rerank": true,
  "top_k": 5,
  "candidate_k": 24,
  "min_similarity": 0.25
}
```

默认 dense、rerank=false；top_k 为 1–12，candidate_k 为 12–100。
min_similarity 仅约束 Dense 召回。Sparse 不调用 Embedding，但索引仍须先创建。
similarity / sparse_score / rrf_score / rerank_score 分别表示余弦、BM25L、RRF 和重排得分；
不适用的分数为 null。Rerank 分数只比较本次候选，不是科学结论的置信度。
BM25 语料达到 SPARSE_CORPUS_LIMIT 时响应 warnings 提示；限定 document_id 可缩小范围。
重排失败返回 rerank_failed，不返回伪装成重排结果的其他排序。

Agent 的 question、document_id、max_steps（1–6）和 required_tools 控制任务。
支持材料查询/详情/结构/快照对比、论文检索、读取已提取实验记录、OpenAlex 在线元数据；不执行模型生成的任意代码。
真实 HTTP 与浏览器证据保存在 data/acceptance/，离线替身测试不充当服务联通证据。

协作参数 workflow_mode=single/auto/collaborative（默认 single）、max_model_calls 与 time_budget_seconds 详见 [协作说明](collaboration.md)。

2026-11-04 界面配套只读接口：

- `GET /api/documents?limit=100`：已解析文献摘要，包含标题、文件名、页数、解析时间和实验归档是否存在。limit 范围 1–100，不返回正文块。
- `GET /api/documents/{document_id}/experiments`：读取已保存实验记录，不触发提取模型；没有记录返回 404。
- `GET /api/agent/runs?limit=50`：已完成任务摘要，limit 范围 1–100，不返回原始工具正文。可继续按任务 ID 获取完整结果。

目录接口最多检查最近 500 个候选归档，忽略损坏、标识不匹配和非最终任务文件。完整原件、候选、失败记录保持原位；旧任务仍可通过已知 ID 回读。接口沿用当前本机单用户边界。
