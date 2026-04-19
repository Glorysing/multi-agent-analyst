"""
LangGraph 工作流
===============
    planner -> coder -> executor -> reviewer
                                        |
                    +----------------------------------------+
                    |                   |                    |
               passed=Y           exec_fail              quality_fail
                    |                   |                    |
                    v                   v                    v
                 reporter             coder              planner
                                 (直接改 bug,         (重新规划, 新
                                  计划不变)           计划带反馈跑)

路由策略 (_review_branch):
  - review_passed=True  -> reporter
  - execution_success=False -> coder   (代码炸了, 换计划没用, 改代码最快)
  - 否则 (跑通但结论不行) -> planner   (计划本身弱, 换新思路)

这么分路由的原因: 上一版所有失败都回 Planner, 导致即便只是 dtype 这种小 bug
也要让 Planner 重写 5 步计划, 浪费一整轮 iteration。
"""

from __future__ import annotations

import re

from langgraph.graph import StateGraph, END

from agents.planner import run_planner
from agents.coder import run_coder
from agents.executor import execute_code
from agents.reviewer import run_reviewer
from providers import get_provider, Message
from workflow.state import AnalysisState
from workflow.i18n import get_system_prompt, emit_text, label


# ---- 报告正文后处理: 去掉 LLM 可能漏掉的图表引用 ----
# 哪怕 prompt 里禁了, 不同模型还是会写 "[图表: outputs/chart_x.png]"、
# "(见 chart_3.png)"、"see chart_X.png" 之类。regex 按"最外层包装优先"顺序兜底清掉。
# 关键: 圆括号和方括号得各自成对, 否则会把外层 `(` `)` 留下一只脚。
_CHART_SCRUBBERS: tuple[re.Pattern[str], ...] = (
    # 1) 最嵌套的形式: "([图表: outputs/chart_X.png])" — 外层圆括号 + 内层方括号一起删
    re.compile(r"[\(（]\s*[\[【][^\]】\n]*?chart_\d[A-Za-z0-9_\-]*\.(?:png|jpg|jpeg|svg)[^\]】\n]*?[\]】]\s*[\)）]"),
    # 2) "([图表: ...])" 但图表名写别的形式, 还是 括号+方括号 嵌套
    re.compile(r"[\(（]\s*[\[【][^\]】\n]{0,120}?\.(?:png|jpg|jpeg|svg)[^\]】\n]*?[\]】]\s*[\)）]"),
    # 3) 纯方括号整行: "[图表: outputs/chart_X.png]" / "[Chart: ...]"
    re.compile(r"^\s*[\[【][^\]】\n]*?(?:图表|chart|Chart)[^\]】\n]*?\.(?:png|jpg|jpeg|svg)[^\]】\n]*?[\]】]\s*$", re.MULTILINE),
    # 4) 纯方括号行内: "[图表: ... .png]" / "[chart_X.png]"
    re.compile(r"[\[【][^\]】\n]{0,120}?chart_\d[A-Za-z0-9_\-]*\.(?:png|jpg|jpeg|svg)[^\]】\n]*?[\]】]"),
    # 5) 纯圆括号行内: "(见 chart_X.png)" / "(outputs/chart_1.png)"
    re.compile(r"[\(（][^)）\n]{0,120}?chart_\d[A-Za-z0-9_\-]*\.(?:png|jpg|jpeg|svg)[^)）\n]*?[\)）]"),
    # 6) 裸路径: "outputs/chart_X.png"
    re.compile(r"(?:outputs/)?chart_\d[A-Za-z0-9_\-]*\.(?:png|jpg|jpeg|svg)"),
    # 7) "如图所示"/"见下图"等空话, 连接标点一起吃掉
    re.compile(r"[,;,;]?\s*(?:如图所示|如图|见下图|见上图|参见图表|请见图表|详见图表|如下图所示)[,。.;; \u3000]?"),
)


def _scrub_chart_refs(text: str) -> str:
    """剥掉 Reporter 正文里残留的图表文件引用。
    顺序: 先处理嵌套最深的外层包装, 再裸路径, 最后"如图所示"这类空词。
    每条 regex 独立跑, 一条漏了还有下一条兜着。"""
    for pat in _CHART_SCRUBBERS:
        text = pat.sub("", text)
    # 二次清理: 替换产生的空括号 / 行尾空白 / 连续空行
    text = re.sub(r"[\(（]\s*[\)）]|[\[【]\s*[\]】]", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _fallback_report(lang: str, exec_snippet: str, err: Exception) -> str:
    """Reporter LLM 挂了时的兜底报告, 保证至少有一份可读 Markdown。"""
    if lang == "en":
        return (
            f"## Background\nAuto report generation failed ({err}). Raw execution output follows.\n\n"
            f"## Key Findings\n```\n{exec_snippet}\n```\n\n"
            f"## Anomalies\nLLM error during the report-writing stage.\n\n"
            f"## Recommendations\nCheck the Ollama connection or switch LLM_PROVIDER and retry."
        )
    return (
        f"## 背景\n自动报告生成失败 ({err}), 以下为原始执行输出。\n\n"
        f"## 关键发现\n```\n{exec_snippet}\n```\n\n"
        f"## 异常点\n报告撰写阶段 LLM 异常。\n\n"
        f"## 建议\n检查 Ollama 连接或切换 LLM_PROVIDER 后重试。"
    )


def generate_report(state: AnalysisState) -> AnalysisState:
    """Reporter 节点: 调用通用 LLM 把执行结果整理成 Markdown 报告。"""
    lang = state.language or "zh"
    state.emit("reporter", emit_text("reporter_start", lang))

    plan_lines = "\n".join(
        f"{p['step']}. {p['action']}: {p['detail']}" for p in state.plan
    )
    exec_snippet = (state.execution_result or "")[-3000:]
    # 注意: 故意不把 chart_paths 传给 Reporter. 模型看到文件名就会想引用,
    # 即便 prompt 里禁止也不保险. 图表由前端单独渲染即可, 正文专注于数字和结论。

    user_msg = (
        f"{label('analysis_goal', lang)}:\n{state.user_goal}\n\n"
        f"{label('data_summary', lang)}:\n{state.df_summary}\n\n"
        f"{label('analysis_plan', lang)}:\n{plan_lines}\n\n"
        f"{label('exec_stdout_ok', lang)}:\n{exec_snippet}\n\n"
        f"{label('instr_reporter', lang)}"
    )

    try:
        provider = get_provider(config=state.provider_config)
        report = provider.chat(
            [Message(role="user", content=user_msg)],
            system=get_system_prompt("reporter", lang),
            temperature=0.4,
            max_tokens=3000,
        )
        # 即便 prompt 禁了, 模型也可能漏带图表引用. 强制 scrub 一遍。
        state.final_report = _scrub_chart_refs(report.strip())
    except Exception as e:
        # 兜底: 如果 LLM 生成失败, 至少给用户一份包含原始输出的最小报告
        state.final_report = _fallback_report(lang, exec_snippet, e)

    state.emit("done", emit_text("reporter_done", lang, n=len(state.final_report)))
    return state


def _review_branch(state) -> str:
    """Reviewer 之后的条件路由。兼容 state 为 dataclass / dict 两种形态。

    三路分流:
      review_passed=True          -> reporter (出报告)
      execution_success=False     -> coder    (代码炸了, 直接改代码)
      其它 (跑通但结论不足)         -> planner  (换新分析思路)
    """
    def _get(key, default=None):
        if isinstance(state, dict):
            return state.get(key, default)
        return getattr(state, key, default)

    if _get("review_passed", False):
        return "reporter"
    if not _get("execution_success", True):
        return "coder"
    return "planner"


def build_graph():
    graph = StateGraph(AnalysisState)

    graph.add_node("planner", run_planner)
    graph.add_node("coder", run_coder)
    graph.add_node("executor", execute_code)
    graph.add_node("reviewer", run_reviewer)
    graph.add_node("reporter", generate_report)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "coder")
    graph.add_edge("coder", "executor")
    graph.add_edge("executor", "reviewer")

    graph.add_conditional_edges(
        "reviewer",
        _review_branch,
        {"reporter": "reporter", "coder": "coder", "planner": "planner"},
    )
    graph.add_edge("reporter", END)

    return graph.compile()
