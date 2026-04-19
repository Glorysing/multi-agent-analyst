"""
OpenAI 兼容 Provider
===================
一个类吃下所有 OpenAI 兼容的 API:
    - DeepSeek      (便宜稳定)
    - Groq          (免费、快)
    - 硅基流动       (免费额度)
    - 通义千问       (国内直连)
    - Kimi          (中文好)
    - OpenAI        (原版)

只要 base_url 对得上,都能跑。
"""

from __future__ import annotations
from openai import OpenAI
from .base import BaseLLMProvider, Message


class OpenAICompatibleProvider(BaseLLMProvider):
    name = "openai_compatible"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
    ):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(m.to_dict() for m in messages)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
