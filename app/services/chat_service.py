"""封装通义千问的兼容聊天接口，供智能体生成结果与调用工具。"""

from app.core.config import Settings
from app.services.llm_client import LLMClient


class ChatService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = LLMClient(settings)

    def complete(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        json_output: bool = False,
        forced_tool: str | None = None,
    ) -> dict:
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
        return self.client.chat_completions(body)
