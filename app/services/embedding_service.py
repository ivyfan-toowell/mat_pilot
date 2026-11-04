"""分批调用 DashScope 向量模型，校验响应顺序、维度及向量有效性。"""

import math

import httpx

from app.core.config import Settings
from app.core.errors import ServiceError


class EmbeddingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.settings.dashscope_api_key:
            raise ServiceError("embedding_not_configured", "请配置 DASHSCOPE_API_KEY。", 503)
        if any(not text.strip() or len(text) > 16000 for text in texts):
            raise ServiceError("invalid_embedding_input", "文本为空或过长，请缩小文档块。", 422)
        vectors = []
        try:
            with httpx.Client(timeout=60) as client:
                for start in range(0, len(texts), self.settings.embedding_batch_size):
                    batch = texts[start : start + self.settings.embedding_batch_size]
                    response = client.post(
                        f"{self.settings.llm_base_url.rstrip('/')}/embeddings",
                        headers={
                            "Authorization": "Bearer "
                            + self.settings.dashscope_api_key.get_secret_value()
                        },
                        json={
                            "model": self.settings.embedding_model,
                            "input": batch,
                            "dimensions": self.settings.embedding_dimensions,
                            "encoding_format": "float",
                        },
                    )
                    response.raise_for_status()
                    items = sorted(response.json()["data"], key=lambda item: item["index"])
                    if [item["index"] for item in items] != list(range(len(batch))):
                        raise ValueError("invalid embedding batch indexes")
                    for item in items:
                        vector = [float(value) for value in item["embedding"]]
                        if (
                            len(vector) != self.settings.embedding_dimensions
                            or not all(math.isfinite(value) for value in vector)
                            or not any(vector)
                        ):
                            raise ValueError("invalid embedding vector")
                        vectors.append(vector)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ServiceError(
                "embedding_failed", "向量化请求失败或返回维度无效，未更新知识库。"
            ) from exc
        return vectors
