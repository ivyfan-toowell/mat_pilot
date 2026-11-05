"""共享 DashScope / OpenAI 兼容 HTTP 客户端，统一鉴权与超时。"""

from __future__ import annotations

import httpx

from app.core.config import Settings
from app.core.errors import ServiceError


class LLMClient:
    def __init__(self, settings: Settings, *, timeout: float = 60) -> None:
        self.settings = settings
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.settings.dashscope_api_key:
            raise ServiceError("llm_not_configured", "请配置 DASHSCOPE_API_KEY。", 503)
        return {
            "Authorization": "Bearer " + self.settings.dashscope_api_key.get_secret_value()
        }

    def post_json(self, url: str, body: dict, *, error_code: str, error_message: str) -> dict:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=self._headers(), json=body)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise ServiceError(error_code, error_message) from exc

    def chat_completions(self, body: dict) -> dict:
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        payload = self.post_json(
            url, body, error_code="llm_failed", error_message="模型调用失败，请检查服务配置或配额。"
        )
        try:
            return payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ServiceError("llm_failed", "模型调用失败，请检查服务配置或配额。") from exc

    def embeddings(self, body: dict) -> dict:
        url = f"{self.settings.llm_base_url.rstrip('/')}/embeddings"
        return self.post_json(
            url,
            body,
            error_code="embedding_failed",
            error_message="向量化请求失败或返回维度无效，未更新知识库。",
        )

    def rerank(self, body: dict) -> dict:
        return self.post_json(
            self.settings.rerank_url,
            body,
            error_code="rerank_failed",
            error_message="重排请求失败或结果无效，请检查模型权限、地域与接口配置。",
        )
