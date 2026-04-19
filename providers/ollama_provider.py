"""Ollama 本地模型 Provider。运行前请确保 `ollama serve` 已启动。"""

from __future__ import annotations
import ollama
from .base import BaseLLMProvider, Message


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(
        self,
        model: str = "qwen2.5:14b",
        host: str = "http://localhost:11434",
    ):
        self.model = model
        self.client = ollama.Client(host=host)

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

        response = self.client.chat(
            model=self.model,
            messages=msgs,
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        )
        return response["message"]["content"]
