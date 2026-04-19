"""
Provider 工厂
============
根据显式配置 (前端请求级覆盖) 或环境变量, 返回对应的 LLMProvider 实例。
四个 Agent 只通过 get_provider() / get_coder_provider() 拿模型, 彻底解耦。

配置优先级 (高 -> 低):
  1) 调用参数传入的 config dict (前端每次请求带的 provider_config)
  2) .env / 进程环境变量
  3) 硬编码默认值
"""

from __future__ import annotations
import os
from typing import Any

from .base import BaseLLMProvider
from .ollama_provider import OllamaProvider
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAICompatibleProvider


# config 字典约定的键 (前端 / 后端/ 工厂 三方共用)
#   provider    : "ollama" | "anthropic" | "openai_compatible"
#   model       : 通用模型名 (Planner / Reviewer / Reporter 用)
#   coder_model : 代码专用模型名 (Coder 用, 仅 ollama 走这一档)
#   host        : Ollama 服务地址
#   api_key     : Anthropic / OpenAI 兼容 用
#   base_url    : OpenAI 兼容 用


def _pick(cfg: dict | None, key: str, env_key: str, default: str) -> str:
    """取值顺序: cfg[key] (如果有且非空) -> os.getenv(env_key) -> default"""
    if cfg is not None:
        v = cfg.get(key)
        if v not in (None, ""):
            return str(v)
    return os.getenv(env_key, default)


def get_provider(
    provider_name: str | None = None,
    *,
    model_override: str | None = None,
    config: dict[str, Any] | None = None,
) -> BaseLLMProvider:
    """
    返回对应的 LLMProvider.

    Args:
        provider_name: 不传则从 config["provider"] / env LLM_PROVIDER 里取
        model_override: 显式指定模型 (Coder 走 qwen2.5-coder 时用)
        config: 来自前端每次请求的覆盖配置 dict, 结构见本文件顶部注释

    Returns:
        BaseLLMProvider 的具体实例
    """
    # provider name 解析顺序: 显式参数 > config > env
    if provider_name is None:
        if config is not None and config.get("provider"):
            provider_name = config["provider"]
        else:
            provider_name = os.getenv("LLM_PROVIDER", "ollama")

    if provider_name == "ollama":
        return OllamaProvider(
            model=model_override or _pick(config, "model", "OLLAMA_MODEL", "qwen2.5:14b"),
            host=_pick(config, "host", "OLLAMA_HOST", "http://localhost:11434"),
        )

    if provider_name == "anthropic":
        api_key = _pick(config, "api_key", "ANTHROPIC_API_KEY", "")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY 未设置 (前端面板或 .env 里填一个)")
        return AnthropicProvider(
            api_key=api_key,
            model=model_override or _pick(config, "model", "ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        )

    if provider_name == "openai_compatible":
        api_key = _pick(config, "api_key", "OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY 未设置 (前端面板或 .env 里填一个)")
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=_pick(config, "base_url", "OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
            model=model_override or _pick(config, "model", "OPENAI_MODEL", "deepseek-chat"),
        )

    raise ValueError(f"未知的 provider: {provider_name}")


def get_coder_provider(config: dict[str, Any] | None = None) -> BaseLLMProvider:
    """
    Coder Agent 专用 —— 如果跑 Ollama, 自动切到代码专用模型 (qwen2.5-coder).
    其他 Provider 不变 (云端模型通常通用能力已足够).

    Args:
        config: 前端每次请求的覆盖配置, 同 get_provider
    """
    # provider 解析同 get_provider 第一段
    if config is not None and config.get("provider"):
        provider_name = config["provider"]
    else:
        provider_name = os.getenv("LLM_PROVIDER", "ollama")

    if provider_name == "ollama":
        coder_model = _pick(config, "coder_model", "OLLAMA_CODER_MODEL", "qwen2.5-coder:7b")
        return get_provider("ollama", model_override=coder_model, config=config)
    return get_provider(provider_name, config=config)
