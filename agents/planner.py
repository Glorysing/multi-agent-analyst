"""
Planner Agent
=============
职责: 把"用户目标 + 数据摘要" 变成 5-7 步 JSON 格式分析计划。
所有系统提示词和状态文案走 workflow.i18n 做中英双语。
"""

from __future__ import annotations
import json
import re
from providers import get_provider, Message
from workflow.state import AnalysisState
from workflow.i18n import get_system_prompt, emit_text, label


# 中文兜底计划
_FALLBACK_PLAN_ZH = [
    {"step": 1, "action": "数据概览", "detail": "检查数据形状、字段类型、缺失值与重复值"},
    {"step": 2, "action": "描述统计", "detail": "对数值字段给出均值、中位数、分位数、标准差"},
    {"step": 3, "action": "分组对比", "detail": "按类别字段分组,对比关键指标的差异"},
    {"step": 4, "action": "趋势分析", "detail": "若存在时间字段,按日/月聚合看趋势"},
    {"step": 5, "action": "异常检测", "detail": "找出显著偏离均值或趋势的记录"},
    {"step": 6, "action": "洞察总结", "detail": "用数字支撑 3-5 条关键业务结论"},
]

# 英文兜底计划
_FALLBACK_PLAN_EN = [
    {"step": 1, "action": "Data Overview",       "detail": "Inspect shape, dtypes, nulls, and duplicates"},
    {"step": 2, "action": "Descriptive Stats",   "detail": "Report mean, median, quartiles, and std for numeric columns"},
    {"step": 3, "action": "Group Comparison",    "detail": "Group by categorical fields and compare key metrics"},
    {"step": 4, "action": "Trend Analysis",      "detail": "If a time column exists, aggregate by day/month and plot trends"},
    {"step": 5, "action": "Anomaly Detection",   "detail": "Identify records deviating significantly from mean or trend"},
    {"step": 6, "action": "Insight Summary",     "detail": "Produce 3-5 key business conclusions backed by numbers"},
]


def _fallback_plan(lang: str) -> list[dict]:
    return _FALLBACK_PLAN_EN if lang == "en" else _FALLBACK_PLAN_ZH


def _extract_json_array(text: str) -> list[dict] | None:
    """从模型输出中提取第一个 JSON 数组。兼容 ```json ... ``` 包裹等情况。"""
    # 1. 去掉 markdown 代码块标记
    text = re.sub(r"```(?:json)?", "", text).strip("` \n\t")

    # 2. 先尝试直接 parse
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
    except Exception:
        pass

    # 3. 抓第一个 [...] 块
    m = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, list):
                return obj
        except Exception:
            pass
    return None


def run_planner(state: AnalysisState) -> AnalysisState:
    lang = state.language or "zh"
    state.emit("planner", emit_text("planner_start", lang))

    user_msg = (
        f"{label('analysis_goal', lang)}:\n{state.user_goal}\n\n"
        f"{label('data_summary', lang)}:\n{state.df_summary}\n\n"
        f"{label('instr_planner', lang)}"
    )

    provider = get_provider(config=state.provider_config)
    try:
        raw = provider.chat(
            [Message(role="user", content=user_msg)],
            system=get_system_prompt("planner", lang),
            temperature=0.3,
            max_tokens=2048,
        )
    except Exception as e:
        fallback = _fallback_plan(lang)
        state.emit("planner", f"LLM call failed, using fallback plan: {e}" if lang == "en"
                   else f"LLM 调用失败,使用兜底计划: {e}")
        state.plan = fallback
        return state

    parsed = _extract_json_array(raw)
    if not parsed:
        state.emit("planner", "Model output unparseable as JSON, using fallback plan" if lang == "en"
                   else "模型输出无法解析为 JSON,使用兜底计划")
        state.plan = _fallback_plan(lang)
    else:
        # 规范化: 保证每项都有 step/action/detail
        default_action = "Step" if lang == "en" else "步骤"
        cleaned: list[dict] = []
        for i, item in enumerate(parsed, start=1):
            if not isinstance(item, dict):
                continue
            cleaned.append({
                "step":   int(item.get("step", i)),
                "action": str(item.get("action", "")).strip() or f"{default_action} {i}",
                "detail": str(item.get("detail", "")).strip(),
            })
        state.plan = cleaned or _fallback_plan(lang)

    state.emit("planner", emit_text("planner_done", lang, n=len(state.plan)))
    return state
