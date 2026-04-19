"""
Coder Agent
===========
职责: 根据分析计划生成完整可执行的 pandas + matplotlib 代码。
系统提示词 / 状态文案走 workflow.i18n 做中英双语。
"""

from __future__ import annotations
import re
from providers import get_coder_provider, Message
from workflow.state import AnalysisState
from workflow.i18n import get_system_prompt, emit_text, label


def _strip_code_fence(text: str) -> str:
    """去掉模型可能加的 ```python ... ``` 包裹。"""
    text = text.strip()
    text = re.sub(r"^```(?:python|py)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def run_coder(state: AnalysisState) -> AnalysisState:
    lang = state.language or "zh"
    state.emit("coder", emit_text("coder_start", lang))

    plan_lines = "\n".join(
        f"{p['step']}. {p['action']}: {p['detail']}" for p in state.plan
    )

    # 如果是第 2 轮及以后, 把 Reviewer 的反馈也带进去
    revision_hint = ""
    if state.iteration > 0 and state.review_feedback:
        revision_hint = (
            f"\n\n{label('revision_hint', lang)}:\n{state.review_feedback}\n"
        )

    user_msg = (
        f"{label('analysis_goal', lang)}:\n{state.user_goal}\n\n"
        f"{label('data_summary', lang)}:\n{state.df_summary}\n\n"
        f"{label('analysis_plan', lang)}:\n{plan_lines}"
        f"{revision_hint}\n\n"
        f"{label('instr_coder', lang)}"
    )

    provider = get_coder_provider(config=state.provider_config)
    try:
        raw = provider.chat(
            [Message(role="user", content=user_msg)],
            system=get_system_prompt("coder", lang),
            temperature=0.1,
            max_tokens=4096,
        )
    except Exception as e:
        state.emit("coder", emit_text("coder_llm_fail", lang, e=e))
        state.code = ""
        return state

    state.code = _strip_code_fence(raw)
    n_lines = state.code.count("\n") + 1
    state.emit("coder", emit_text("coder_done", lang, n=n_lines))
    return state
