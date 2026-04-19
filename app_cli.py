"""
CLI 入口 —— 不依赖 FastAPI, 用于本地调试 / 烟测。

用法:
    python app_cli.py path/to/data.csv
    python app_cli.py path/to/data.csv "找出销售异常点"
    python app_cli.py path/to/data.csv "Find sales anomalies" --lang en
    python app_cli.py path/to/data.csv --lang zh

语言 (--lang) 默认读环境变量 OUTPUT_LANGUAGE, 未设置则 zh。
"""

from __future__ import annotations
import os
import sys
from dotenv import load_dotenv

# 必须最先 load, 否则 providers / graph 读不到环境变量
load_dotenv()

import pandas as pd

from workflow.graph import build_graph
from workflow.state import AnalysisState
from workflow.i18n import norm_lang


def get_df_summary(csv_path: str) -> str:
    df = pd.read_csv(csv_path, encoding="utf-8")
    try:
        head = df.head(5).to_string(max_cols=20)
        desc = df.describe(include="all").to_string()
    except Exception as e:
        head, desc = f"(preview failed: {e})", ""
    cols = ", ".join(f"{c}({df[c].dtype})" for c in df.columns)
    return (
        f"rows: {len(df)}, cols: {len(df.columns)}\n"
        f"fields: {cols}\n\n"
        f"Head (5):\n{head}\n\n"
        f"Describe:\n{desc}"
    )


def _print_event(event: str, data: str) -> None:
    tag = {
        "planner":  "🧭 Planner ",
        "coder":    "💻 Coder   ",
        "executor": "⚙️  Executor",
        "reviewer": "🔍 Reviewer",
        "reporter": "📝 Reporter",
        "done":     "✅ Done    ",
        "error":    "❌ Error   ",
    }.get(event, f"   {event:<9}")
    print(f"{tag} | {data}")


def _parse_args(argv: list[str]) -> tuple[str, str, str]:
    """返回 (csv_path, goal, lang). 支持任意位置的 --lang xx 或 --lang=xx。"""
    lang = os.getenv("OUTPUT_LANGUAGE") or "zh"
    positional: list[str] = []
    i = 0
    args = argv[1:]
    while i < len(args):
        a = args[i]
        if a == "--lang" and i + 1 < len(args):
            lang = args[i + 1]
            i += 2
            continue
        if a.startswith("--lang="):
            lang = a.split("=", 1)[1]
            i += 1
            continue
        positional.append(a)
        i += 1

    if not positional:
        sys.stderr.write(
            "Usage: python app_cli.py <path/to/data.csv> [\"goal\"] [--lang zh|en]\n"
        )
        sys.exit(2)
    csv_path = positional[0]
    default_goal_zh = "全面分析这份数据,找出关键业务洞察"
    default_goal_en = "Analyze this dataset thoroughly and surface the key business insights."
    if len(positional) > 1:
        goal = positional[1]
    else:
        goal = default_goal_en if norm_lang(lang) == "en" else default_goal_zh
    return csv_path, goal, norm_lang(lang)


def main() -> None:
    csv_path, goal, lang = _parse_args(sys.argv)

    print(f"CSV:   {csv_path}")
    print(f"Goal:  {goal}")
    print(f"Lang:  {lang}")
    print("-" * 60)

    state = AnalysisState(
        csv_path=csv_path,
        user_goal=goal,
        df_summary=get_df_summary(csv_path),
        language=lang,
        progress_cb=_print_event,
    )

    graph = build_graph()
    final = graph.invoke(state)

    # 兼容 dict / dataclass
    def _get(o, k, d=None):
        return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)

    title = "Final Report" if lang == "en" else "最终报告"
    none_label = "(none)" if lang == "en" else "(无)"
    charts_label = "chart(s) generated" if lang == "en" else "张图表"

    print()
    print("=" * 60)
    print(f" {title}")
    print("=" * 60)
    print(_get(final, "final_report", none_label))

    charts = _get(final, "chart_paths", []) or []
    print()
    print(f"{len(charts)} {charts_label}:")
    for p in charts:
        print(f"  - {p}")


if __name__ == "__main__":
    main()
