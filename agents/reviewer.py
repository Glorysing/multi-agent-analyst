"""
Reviewer Agent
==============
职责: 判断本轮分析是否"够用",给 graph.py 提供 review_passed 做路由。
系统提示词 / 状态文案走 workflow.i18n 做中英双语。
"""

from __future__ import annotations
import json
import re
from providers import get_provider, Message
from workflow.state import AnalysisState
from workflow.i18n import get_system_prompt, emit_text, label


def _extract_json_object(text: str) -> dict | None:
    text = re.sub(r"```(?:json)?", "", text).strip("` \n\t")
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return None


def run_reviewer(state: AnalysisState) -> AnalysisState:
    lang = state.language or "zh"
    state.emit("reviewer", emit_text("reviewer_start", lang))

    # 迭代计数 (在进入 Reviewer 时自增, 代表"已完成的分析轮次")
    state.iteration += 1

    # 执行失败直接判 fail, 不用打扰 LLM
    if not state.execution_success:
        state.review_passed = False
        prefix = ("Code execution failed, needs fixing:\n" if lang == "en"
                  else "代码执行失败, 需要修正:\n")
        fallback_body = ("(no error output)" if lang == "en" else "无错误输出")
        state.review_feedback = prefix + (state.execution_result or fallback_body)[-1500:]
    else:
        plan_lines = "\n".join(
            f"{p['step']}. {p['action']}: {p['detail']}" for p in state.plan
        )
        exec_snippet = (state.execution_result or "")[-3000:]

        user_msg = (
            f"{label('analysis_goal', lang)}:\n{state.user_goal}\n\n"
            f"{label('analysis_plan', lang)}:\n{plan_lines}\n\n"
            f"{label('exec_stdout', lang)}:\n{exec_snippet}\n\n"
            f"{label('n_charts', lang)}: {len(state.chart_paths)}\n"
            f"{label('iter_count', lang)}: "
            f"{state.iteration} / {label('max_iter', lang)} {state.max_iterations}\n\n"
            f"{label('instr_reviewer', lang)}"
        )

        try:
            provider = get_provider(config=state.provider_config)
            raw = provider.chat(
                [Message(role="user", content=user_msg)],
                system=get_system_prompt("reviewer", lang),
                temperature=0.2,
                max_tokens=1024,
            )
            obj = _extract_json_object(raw) or {}
            state.review_passed = bool(obj.get("passed", False))
            state.review_feedback = str(obj.get("feedback", "")).strip() or raw[:500]
        except Exception as e:
            # 审查 LLM 崩了: 宽松处理 —— 只要执行成功就算过
            state.review_passed = True
            state.review_feedback = (f"Reviewer LLM error, defaulting to pass: {e}" if lang == "en"
                                     else f"审核 LLM 异常, 默认放行: {e}")

    # 达到最大轮次: 无论如何结束 (强制 passed=True 让图走到 reporter)
    if state.iteration >= state.max_iterations and not state.review_passed:
        state.review_passed = True
        if lang == "en":
            state.review_feedback = (
                f"Reached max iterations ({state.max_iterations}), forcing finalize with best-so-far result."
                + (f" Last feedback: {state.review_feedback}" if state.review_feedback else "")
            )
        else:
            state.review_feedback = (
                f"已达最大迭代次数 {state.max_iterations}, 强制结束并输出当前最佳结果。"
                + (f" 最后一次反馈: {state.review_feedback}" if state.review_feedback else "")
            )

    key = "reviewer_pass" if state.review_passed else "reviewer_fail"
    state.emit("reviewer", emit_text(key, lang, i=state.iteration))
    return state
