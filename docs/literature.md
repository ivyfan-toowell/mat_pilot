# OpenAlex 论文发现

入口为 Streamlit 的“论文发现”工作区，以及科研助手的“在线论文元数据”资料来源。
支持关键词或 DOI、年份、开放获取筛选、相关性/发表日期/被引次数排序，单次最多 20 条。
检索、回读和下载的 JSON 保留查询条件、时间、标题、DOI、作者、来源、开放获取信息和许可。
只保存第一页；有限结果与去重会显式提示，不能据此声称完成系统性文献综述。

在后端 .env 配置 OPENALEX_API_KEY。密钥使用请求头传递，不进入 URL、快照或模型工具参数。
接口固定为官方 OpenAlex API；请求不自动跟随重定向。超时/临时服务错误至多尝试 3 次，
短暂限流遵循有限等待；长 Retry-After、认证错误直接返回，不无期限重试。
OPENALEX_TIMEOUT_SECONDS 默认 20 秒，是每次 HTTP 操作的超时设置，不是总任务的硬截止时间。

```json
{
  "query": "TiO2 oxygen vacancies photocatalysis",
  "year_from": 2020,
  "year_to": 2026,
  "open_access_only": true,
  "sort": "citations",
  "limit": 5
}
```

POST /api/literature/search 返回 query_id；GET /api/literature/queries/{query_id} 回读快照。
缺少密钥返回 openalex_not_configured；认证失败 openalex_auth_failed；限流 openalex_rate_limited；
不合法查询为 openalex_bad_query；上游结构无效或不保留筛选条件为 openalex_invalid_response。
没有密钥时其他模块继续可用；科研助手不会向模型提供未配置的在线工具。

每条结果标记 bibliographic_metadata，metadata_only=true。
这类结果不能证明已阅读全文，也不能用于核验带隙、合成条件等实验事实。
科研助手区分本地全文 search_papers 与在线元数据 search_academic_papers；只有在线元数据引用
却声称实验测量数值的结论会被拦截。该规则不是完整的科学语义验证，解释仍需人工复核。

OA 标记不等同于再分发授权。PDF 链接、版本和许可取自同一 location，避免将出版社许可
错误地赋给仓储版本。没有许可不推断为 CC BY；不自动下载全文。取得合法 PDF 后可上传解析。
作者展示前 30 位并标明截断；撤稿标记显示提示；被引次数不是科研质量评分。

验收命令：先启动 FastAPI 和 Streamlit，再运行
`uv run python -m scripts.verify_openalex`。
它检查真实 DOI、关键词/年份/OA 查询、快照回读、界面查询和科研助手工具任务，报告与截图
保存在 data/acceptance/openalex/。tests/test_literature.py 使用显式合成元数据测试错误边界，
不充当真实论文结果。

接口语义依据官方[认证说明](https://help.openalex.org/api/authentication/)、
[字段定义](https://help.openalex.org/data/works/attributes/)与
[搜索说明](https://help.openalex.org/api/searching/)。
