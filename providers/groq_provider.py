"""
Groq Provider
=============
Groq 完全兼容 OpenAI ChatCompletions 接口, 所以实现上就是把 base_url 钉死、
默认模型换成 llama-3.3-70b-versatile。单独开这个文件的唯一目的是让"显式命名"
的 provider=groq 能被后端直接识别, 并避免用户在部署到线上 Demo 时
必须记住 base_url 是什么。

免费 Key 注册: https://console.groq.com/keys
"""

from __future__ import annotations

from .base import BaseLLMProvider, Message
from .openai_provider import OpenAICompatibleProvider


GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# 通用模型 (Planner / Reviewer / Reporter / Coder 共用, Groq 没有专门的 coder 模型).
# llama-3.3-70b-versatile 在 Groq 上推理延迟 ~500ms, 质量足够跑本项目工作流。
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(OpenAICompatibleProvider):
    """
    Groq 的薄封装: base_url 钉死, 默认模型改好。
    其他行为 (chat 签名、流式等) 完全复用 OpenAICompatibleProvider。
    """

    name = "groq"

    def __init__(
        self,
        api_key: str,
        model: str = GROQ_DEFAULT_MODEL,
        base_url: str = GROQ_BASE_URL,
    ):
        super().__init__(api_key=api_key, base_url=base_url, model=model)

    def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        # Groq 对 max_tokens 上限比较敏感 (部分模型 8k), 这里留着父类实现即可。
        return super().chat(
            messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
