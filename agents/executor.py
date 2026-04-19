"""
Executor
========
注意: 这不是 LLM, 是一个受限的 Python 子进程执行器。

- 在 subprocess 里跑代码, 以免污染主进程
- 60 秒超时, 防止跑飞
- 黑名单关键字拦截 (os.system / subprocess / eval / exec / shutil.rmtree / __import__)
- 只收集本次执行新生成的 PNG 到 state.chart_paths
"""

from __future__ import annotations
import glob
import os
import re
import subprocess
import sys
import time

from workflow.state import AnalysisState
from workflow.i18n import emit_text


# 黑名单: 简单字符串匹配即可拦截大多数危险操作
_FORBIDDEN_PATTERNS = [
    "os.system",
    "os.popen",
    "subprocess",
    "shutil.rmtree",
    "__import__('os')",
    '__import__("os")',
    "eval(",
    "exec(",
    "pty.spawn",
    "socket.",
    "urllib.request",
    "requests.get",
    "requests.post",
]

# 已知"会炸"或"会产出英文默认标题"的反模式。
# 命中直接不执行, 让 Reviewer 路由回 Coder 改, 比执行后看混乱 traceback 快得多。
# 每条 = (正则, 中文原因, 英文原因)
_LINT_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # seaborn 函数族不接受 figsize kwarg, 常被模型误用
    (re.compile(r"\bsns\.(?:heatmap|barplot|boxplot|violinplot|lineplot|scatterplot|countplot|kdeplot|stripplot|swarmplot|histplot)\s*\([^)]*\bfigsize\s*="),
     "sns.<plot>(..., figsize=...) 不合法: figsize 只能传给 plt.figure / plt.subplots",
     "sns.<plot>(..., figsize=...) is invalid: figsize belongs to plt.figure/plt.subplots"),
    # df.hist / df.plot 等会用原始列名做英文默认标题
    (re.compile(r"(?<![A-Za-z_0-9])df\s*\.\s*(?:hist|boxplot)\s*\("),
     "禁止 df.hist() / df.boxplot(): 会用原始列名做英文 subplot 标题, 混入最终图表. 请手写 for 循环 + 显式中文 title/xlabel/ylabel",
     "Forbidden df.hist() / df.boxplot(): they auto-use raw column names as subplot titles. Hand-write a for loop with explicit title/xlabel/ylabel"),
    (re.compile(r"(?<![A-Za-z_0-9])df\s*\.\s*plot\s*(?:\.\s*(?:bar|line|hist|box|area|pie|scatter)\s*)?\("),
     "禁止 df.plot(...) / df.plot.bar() 等: 会用原始英文列名当图表 title/legend. 请手写循环+显式标题",
     "Forbidden df.plot(...) / df.plot.bar(): uses raw column names for title/legend. Hand-write an explicit loop"),
    # 直接对整张 df 做 corr / to_numpy / values 会吞字符串列
    (re.compile(r"(?<![A-Za-z_0-9])df\s*\.\s*(?:corr|cov|to_numpy)\s*\("),
     "禁止对整张 df 直接调用 .corr() / .cov() / .to_numpy(): 有字符串列时会 ValueError. 请先 df.select_dtypes(include='number')",
     "Forbidden df.corr()/cov()/to_numpy() on full df: string columns cause ValueError. Use df.select_dtypes(include='number') first"),
    # sns.pairplot / sns.heatmap 直接吃整张 df 同样炸
    (re.compile(r"\bsns\.pairplot\s*\(\s*df\b"),
     "禁止 sns.pairplot(df): 带字符串列会炸. 先筛数值列: sns.pairplot(df.select_dtypes(include='number'))",
     "Forbidden sns.pairplot(df): crashes on string columns. Use sns.pairplot(df.select_dtypes(include='number'))"),
    (re.compile(r"\bsns\.heatmap\s*\(\s*df\s*[,)]"),
     "禁止 sns.heatmap(df): 请先 corr = df.select_dtypes(include='number').corr() 再 sns.heatmap(corr, ...)",
     "Forbidden sns.heatmap(df): compute corr first - corr = df.select_dtypes(include='number').corr(), then sns.heatmap(corr, ...)"),
    # df.astype(float) / pd.to_numeric(df[...]) 对字符串列炸
    (re.compile(r"(?<![A-Za-z_0-9])df\s*\.\s*astype\s*\(\s*(?:float|int|np\.float|np\.int)"),
     "禁止 df.astype(float/int): 字符串列会炸. 只对数值列: df[num_cols] = df[num_cols].astype(float)",
     "Forbidden df.astype(float/int): string columns will crash. Only cast numeric cols: df[num_cols] = df[num_cols].astype(float)"),
]


def _lint_code(code: str, lang: str) -> str | None:
    """跑静态 lint, 命中就返回拼好的中/英错误原因; 全都通过返回 None。"""
    hits: list[str] = []
    for pat, zh_msg, en_msg in _LINT_PATTERNS:
        if pat.search(code):
            hits.append(en_msg if lang == "en" else zh_msg)
    if not hits:
        return None
    header = "Static lint rejected the code:" if lang == "en" else "静态检查拦截了代码:"
    return header + "\n- " + "\n- ".join(hits)


# 执行包装脚本 —— 把 df / 绘图环境预先准备好,然后把用户代码 exec 进去
_RUNNER_TEMPLATE = r"""
# -*- coding: utf-8 -*-
import sys, os, warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

# 中文字体 (Windows 系统自带 SimHei / Microsoft YaHei)
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
sns.set_theme(style="whitegrid", font=plt.rcParams["font.sans-serif"][0])

os.makedirs("outputs", exist_ok=True)

# 载入数据 —— 由调度方注入真实 CSV 路径
df = pd.read_csv(r"__CSV_PATH__", encoding="utf-8")

# ============ 用户代码开始 ============
__USER_CODE__
# ============ 用户代码结束 ============
"""


def _contains_forbidden(code: str) -> str | None:
    """返回第一个命中的黑名单关键字,没有则 None。"""
    for pat in _FORBIDDEN_PATTERNS:
        if pat in code:
            return pat
    return None


def execute_code(state: AnalysisState) -> AnalysisState:
    lang = state.language or "zh"
    state.emit("executor", emit_text("executor_start", lang))

    code = state.code or ""
    csv_path = state.csv_path

    if not code.strip():
        state.execution_success = False
        state.execution_result = ("Coder produced no code, nothing to execute." if lang == "en"
                                  else "Coder 未产出代码,无法执行。")
        state.emit("executor", emit_text("executor_empty", lang))
        return state

    bad = _contains_forbidden(code)
    if bad:
        state.execution_success = False
        state.execution_result = (f"Security reject: code contains forbidden op {bad!r}" if lang == "en"
                                  else f"安全拒绝: 代码包含禁止操作 {bad!r}")
        state.emit("executor", emit_text("executor_reject", lang, pat=bad))
        return state

    # 静态 lint: 已知会炸的反模式 (sns.heatmap figsize, df.hist, df.corr 等)
    # 直接拦下避免 60 秒超时/cryptic traceback, 反馈给 Reviewer 让 Coder 下一轮修
    lint_err = _lint_code(code, lang)
    if lint_err:
        state.execution_success = False
        state.execution_result = lint_err
        state.chart_paths = []
        state.emit("executor", emit_text("executor_fail", lang, msg=lint_err.splitlines()[0]))
        return state

    os.makedirs("outputs", exist_ok=True)

    # 拼装运行脚本. 用占位符替换避开 f-string 与大量反斜杠冲突。
    full_code = _RUNNER_TEMPLATE.replace("__CSV_PATH__", csv_path).replace(
        "__USER_CODE__", code
    )

    tmp_file = f"outputs/_tmp_exec_{int(time.time() * 1000)}.py"
    with open(tmp_file, "w", encoding="utf-8") as f:
        f.write(full_code)

    start_mtime = time.time() - 1  # 留 1 秒余量防止文件系统时钟差

    # Windows 上 Python 默认按 GBK 编码写 stdout/stderr, 中文 traceback 会变成乱码.
    # 强制子进程用 UTF-8, 与我们 capture 时声明的 encoding="utf-8" 保持一致.
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        result = subprocess.run(
            [sys.executable, tmp_file],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            env=env,
        )
        state.execution_success = result.returncode == 0
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        state.execution_result = (stdout + ("\n--- stderr ---\n" + stderr if stderr else "")).strip()
    except subprocess.TimeoutExpired:
        state.execution_success = False
        state.execution_result = ("Execution timed out (60s)" if lang == "en"
                                  else "执行超时 (60 秒)")
    except Exception as e:
        state.execution_success = False
        state.execution_result = (f"Execution exception: {e!r}" if lang == "en"
                                  else f"执行异常: {e!r}")
    finally:
        try:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        except OSError:
            pass

    # 收集本次执行新生成的图表 (mtime >= start_mtime)
    new_charts = []
    for p in sorted(glob.glob("outputs/*.png")):
        try:
            if os.path.getmtime(p) >= start_mtime:
                new_charts.append(p.replace("\\", "/"))
        except OSError:
            continue
    state.chart_paths = new_charts

    if state.execution_success:
        state.emit("executor", emit_text("executor_ok", lang, n=len(state.chart_paths)))
    else:
        # 输出过长的 traceback 截断一下, 避免前端面板被淹
        snippet = state.execution_result.strip().splitlines()[-5:] if state.execution_result else []
        state.emit("executor", emit_text("executor_fail", lang, msg=" | ".join(snippet)))

    return state
