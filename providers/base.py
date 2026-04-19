"""
LLM Provider 抽象层
==================
目的: 让 Agent 代码完全不关心底层用的是 Ollama / Claude / DeepSeek 哪个模型。
    - 开发时: 切 Claude API (效果最好,调试省心)
    - 演示时: 切 Ollama (本地,免费,"数据不出电脑")
    - 生产时: 切 DeepSeek (便宜、中文好)

所有 Provider 都实现 BaseLLMProvider.chat() 这个统一接口。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


Role = Literal["system", "user", "assistant"]


@dataclass
class Message:
    role: Role
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class BaseLLMProvider(ABC):
    """所有 LLM Provider 的基类。"""

    name: str = "base"

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """
        发送一轮对话,返回模型的文字回复。

        Args:
            messages:    对话历史 (不包含 system)
            system:      system prompt
            temperature: 采样温度。Planner/Reviewer 用 0.3 求稳,Coder 可用 0.1 求准。
            max_tokens:  最大输出 token

        Returns:
            模型返回的文本 (纯字符串,不含工具调用)
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name}>"
