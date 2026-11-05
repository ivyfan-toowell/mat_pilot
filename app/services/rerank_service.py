"""调用 DashScope 文本重排模型，严格校验返回的索引和分数。"""

import math

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.retrieval import SearchHit
from app.services.llm_client import LLMClient


class RerankService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = LLMClient(settings)

    def rank(self, question: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        if not hits:
            return []
        if not self.settings.dashscope_api_key:
            raise ServiceError("rerank_not_configured", "请配置 DASHSCOPE_API_KEY。", 503)
        if len(hits) > 100 or any(len(hit.text) > 6000 for hit in hits):
            raise ServiceError("rerank_input_too_large", "重排候选过多或过长，请缩小文档块。", 422)
        count = min(top_k, len(hits))
        try:
            payload = self.client.rerank(
                {
                    "model": self.settings.rerank_model,
                    "input": {"query": question, "documents": [hit.text for hit in hits]},
                    "parameters": {"top_n": count, "return_documents": False},
                }
            )
            rows = payload["output"]["results"]
            if not isinstance(rows, list) or len(rows) != count:
                raise ValueError("incomplete rerank result")
            ranked = []
            seen = set()
            for row in rows:
                index, score = row["index"], row["relevance_score"]
                if (
                    type(index) is not int
                    or not 0 <= index < len(hits)
                    or index in seen
                    or isinstance(score, bool)
                    or not isinstance(score, (float, int))
                    or not math.isfinite(score)
                    or not 0 <= score <= 1
                ):
                    raise ValueError("invalid rerank index or score")
                seen.add(index)
                ranked.append(hits[index].model_copy(update={"rerank_score": float(score)}))
            return sorted(ranked, key=lambda hit: -hit.rerank_score)
        except ServiceError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            raise ServiceError(
                "rerank_failed", "重排请求失败或结果无效，请检查模型权限、地域与接口配置。"
            ) from exc
