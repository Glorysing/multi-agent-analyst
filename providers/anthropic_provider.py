"""Anthropic Claude Provider。开发调试首选。"""

from __future__ import annotations
import anthropic
from .base import BaseLLMProvider, Message


class AnthropicProvider(BaseLLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5"):
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key)

    def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [m.to_dict() for m in messages],
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)
        # Claude 的返回是 content blocks 列表,只取文字块
        return "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
