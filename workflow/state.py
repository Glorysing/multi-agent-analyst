"""
工作流状态
==========
LangGraph 会在各个节点间传递这个 State 对象。
每个 Agent 读取它所需的字段,并写回它负责的字段。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalysisState:
    # ---- 输入 ----
    csv_path: str = ""
    user_goal: str = ""
    df_summary: str = ""

    # 输出语言 ("zh" | "en"). 控制所有 agent prompt / emit 文案 / 报告 / 图表标题的语言.
    # 默认 zh, 由 .env 的 OUTPUT_LANGUAGE / CLI --lang / API body.language 注入.
    language: str = "zh"

    # ---- Planner 输出 ----
    # 格式: [{"step": 1, "action": "加载数据", "detail": "..."}]
    plan: list[dict] = field(default_factory=list)

    # ---- Coder 输出 ----
    code: str = ""

    # ---- Executor 输出 ----
    execution_result: str = ""
    chart_paths: list[str] = field(default_factory=list)
    execution_success: bool = False

    # ---- Reviewer 输出 ----
    review_passed: bool = False
    review_feedback: str = ""

    # ---- 迭代控制 ----
    iteration: int = 0
    max_iterations: int = 3

    # ---- 最终输出 ----
    final_report: str = ""

    # ---- SSE 事件流 (供 FastAPI 推送进度) ----
    # 每项: {"event": "planner"|"coder"|..., "data": "文字"}
    events: list[dict] = field(default_factory=list)

    # ---- 可选: 进度回调 (FastAPI 后端注入, CLI 下为 None) ----
    # 签名: (event: str, data: str) -> None
    # 不用 field() 避免 dataclass 深拷贝问题
    progress_cb: Any = None

    # ---- 可选: LLM provider 配置覆盖 (前端每次请求带来的覆盖字典) ----
    # 结构: {"provider": "ollama"|"anthropic"|"openai_compatible",
    #        "model": "...", "coder_model": "...", "host": "...",
    #        "api_key": "...", "base_url": "..."}
    # None 表示回退到 .env / 默认值
    provider_config: dict | None = None

    def emit(self, event: str, data: str) -> None:
        """记录事件到 events 列表,并同步给回调(如果有)。"""
        evt = {"event": event, "data": data}
        self.events.append(evt)
        if self.progress_cb is not None:
            try:
                self.progress_cb(event, data)
            except Exception:
                # 回调自身异常不应中断 Agent 流程
                pass
