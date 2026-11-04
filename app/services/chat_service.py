"""封装通义千问的兼容聊天接口，供智能体生成结果与调用工具。"""

import httpx

from app.core.config import Settings
from app.core.errors import ServiceError


class ChatService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def complete(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        json_output: bool = False,
        forced_tool: str | None = None,
    ) -> dict:
        if not self.settings.dashscope_api_key:
            raise ServiceError("llm_not_configured", "请配置 DASHSCOPE_API_KEY。", 503)
        body = {
            "model": self.settings.llm_model,
            "temperature": 0,
            "max_tokens": 5000,
            "messages": messages,
        }
        if tools:
            body.update(tools=tools, tool_choice="auto", parallel_tool_calls=False)
            if forced_tool:
                body["tool_choice"] = {"type": "function", "function": {"name": forced_tool}}
        if json_output:
            body["response_format"] = {"type": "json_object"}
        try:
            with httpx.Client(timeout=60) as client:
                response = client.post(
                    f"{self.settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": "Bearer "
                        + self.settings.dashscope_api_key.get_secret_value()
                    },
                    json=body,
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ServiceError("llm_failed", "模型调用失败，请检查服务配置或配额。") from exc
