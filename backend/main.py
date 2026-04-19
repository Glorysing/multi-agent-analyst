"""
FastAPI 后端
============
路由:
  POST /upload            上传 CSV          -> {file_id, filename, path}
  POST /analyze           触发分析           body: {file_id, goal} -> {task_id}
  GET  /stream/{task_id}  SSE 流式进度推送
  GET  /result/{task_id}  获取最终报告和图表列表
  GET  /chart/{filename}  返回图表 PNG
  GET  /                  返回前端 index.html
  GET  /healthz           健康检查
"""

from __future__ import annotations

import asyncio
import base64
import glob
import json
import os
import platform
import queue
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# 必须在 import providers/workflow 之前 load .env, 否则环境变量读不到
load_dotenv()

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from workflow.graph import build_graph
from workflow.state import AnalysisState
from workflow.i18n import norm_lang, get_system_prompt, label
from providers.base import Message
from providers.factory import get_provider
from backend.pptx_export import build_report_pptx


# ---- 项目根目录: backend/ 的父目录 ----
ROOT_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = ROOT_DIR / "outputs" / "uploads"
OUTPUTS_DIR = ROOT_DIR / "outputs"
FRONTEND_DIR = ROOT_DIR / "frontend"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


app = FastAPI(title="Multi-Agent Data Analyst", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- 内存态 (单进程, 无需 Redis) ----
uploads: dict[str, str] = {}        # file_id -> 绝对路径
tasks: dict[str, dict[str, Any]] = {}  # task_id -> {"queue", "result", "done", "error"}


class AnalyzeBody(BaseModel):
    file_id: str
    goal: str = "全面分析这份数据,找出关键业务洞察"
    # 输出语言: "zh" | "en"; 为空时读 .env 的 OUTPUT_LANGUAGE, 再退化到 "zh"
    language: str | None = None
    # LLM 覆盖配置 (可选). 如果前端传了, 完全覆盖 .env 里的同名字段。
    # 结构: {"provider": "ollama"|"anthropic"|"openai_compatible",
    #        "model": "...", "coder_model": "...", "host": "...",
    #        "api_key": "...", "base_url": "..."}
    # 注意: api_key 只在内存中存活一次请求, 不写磁盘, 不写 .env, 不日志打印.
    provider_config: dict | None = None


class ChatBody(BaseModel):
    """追问接口请求体"""
    message: str


def _summarize_csv(path: str) -> str:
    """生成给 Planner 看的数据摘要 —— 行列数 + 前 5 行 + describe。"""
    df = pd.read_csv(path)
    try:
        head = df.head(5).to_string(max_cols=20)
        desc = df.describe(include="all").to_string()
    except Exception as e:
        head = f"(预览失败: {e})"
        desc = ""
    cols_with_dtype = ", ".join(f"{c}({df[c].dtype})" for c in df.columns)
    return (
        f"行数: {len(df)}, 列数: {len(df.columns)}\n"
        f"字段: {cols_with_dtype}\n\n"
        f"前 5 行预览:\n{head}\n\n"
        f"描述统计:\n{desc}"
    )


def _attr(obj: Any, key: str, default=None):
    """state-or-dict 兼容取值。LangGraph 不同版本返回类型不一。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _format_plan_md(plan: Any, lang: str) -> str:
    """
    把 Planner 的 list[dict] 格式化成给"透明度面板"用的 Markdown 列表。
    兼容形如 [{"step":1,"action":"...","detail":"..."}, ...] 或纯字符串列表。
    """
    if not plan:
        return ""
    lines: list[str] = []
    if isinstance(plan, str):
        return plan
    if not isinstance(plan, list):
        return str(plan)
    for i, item in enumerate(plan, 1):
        if isinstance(item, dict):
            n      = item.get("step", i)
            action = (item.get("action") or "").strip()
            detail = (item.get("detail") or item.get("description") or "").strip()
            head = f"**{n}. {action}**" if action else f"**Step {n}**"
            if detail:
                lines.append(f"{head} — {detail}")
            else:
                lines.append(head)
        else:
            lines.append(f"{i}. {str(item).strip()}")
    return "\n\n".join(lines)


def _clean_old_charts() -> int:
    """删除 outputs/ 下旧的 chart_*.png + _tmp_exec_*.py。
    严格只清根目录直接子文件, 不递归, 不碰 uploads/ 子目录。
    返回删除的文件数。"""
    n = 0
    for pattern in ("chart_*.png", "_tmp_exec_*.py"):
        for p in glob.glob(str(OUTPUTS_DIR / pattern)):
            try:
                if os.path.isfile(p):
                    os.remove(p)
                    n += 1
            except OSError:
                pass
    return n


def _open_in_file_explorer(path: Path) -> None:
    """用系统文件管理器打开目录. 跨平台。"""
    p = str(path)
    if sys.platform.startswith("win"):
        os.startfile(p)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])


# ---- 路由 ----

@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"


@app.get("/", response_class=HTMLResponse)
async def index():
    idx = FRONTEND_DIR / "index.html"
    if not idx.exists():
        return HTMLResponse(
            "<h1>frontend/index.html 不存在</h1>",
            status_code=500,
        )
    return HTMLResponse(idx.read_text(encoding="utf-8"))


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith((".csv", ".tsv", ".txt")):
        raise HTTPException(400, "只支持 .csv / .tsv / .txt 文件")
    file_id = uuid.uuid4().hex[:12]
    safe_name = Path(file.filename).name  # 防路径穿越
    dest = UPLOAD_DIR / f"{file_id}_{safe_name}"
    content = await file.read()
    dest.write_bytes(content)
    uploads[file_id] = str(dest)
    return {"file_id": file_id, "filename": safe_name, "path": str(dest)}


@app.post("/analyze")
async def analyze(body: AnalyzeBody):
    if body.file_id not in uploads:
        raise HTTPException(404, "file_id 未找到, 请先 /upload")
    csv_path = uploads[body.file_id]
    if not os.path.exists(csv_path):
        raise HTTPException(410, "上传的文件已不存在")

    # 每次新分析前清掉旧图表, 避免 outputs 越堆越多, 也避免前端上一组图混进这一组
    removed = _clean_old_charts()

    task_id = uuid.uuid4().hex[:12]
    q: queue.Queue = queue.Queue()
    tasks[task_id] = {
        "queue": q,
        "result": None,
        "done": False,
        "error": None,
        # 追问 (/chat) 用:
        #   context   —— 分析跑完后塞进去的只读快照 (csv_summary, goal, code, stdout, report, lang, provider_config)
        #   chat_history —— [{"role": "user"|"assistant", "content": "..."}], 内存态, 重启即丢
        "context": None,
        "chat_history": [],
    }

    def progress_cb(event: str, data: str) -> None:
        try:
            q.put({"event": event, "data": data})
        except Exception:
            pass

    if removed:
        # 通过 SSE 告诉前端清了几张, 以便 UI 展示
        q.put({"event": "cleanup", "data": str(removed)})

    # 解析语言: body.language > env OUTPUT_LANGUAGE > "zh"
    lang = norm_lang(body.language or os.getenv("OUTPUT_LANGUAGE") or "zh")

    # provider_config 直接透传给 state. 注意不打日志, api_key 属敏感信息
    cfg = body.provider_config if isinstance(body.provider_config, dict) else None

    def runner():
        try:
            df_summary = _summarize_csv(csv_path)
            state = AnalysisState(
                csv_path=csv_path,
                user_goal=body.goal,
                df_summary=df_summary,
                language=lang,
                max_iterations=int(os.getenv("MAX_ITERATIONS", "3")),
                progress_cb=progress_cb,
                provider_config=cfg,
            )
            graph = build_graph()
            # graph.invoke 可能返回 dict 或 dataclass, 统一处理
            final = graph.invoke(state)

            report = _attr(final, "final_report", "") or ""
            chart_paths = _attr(final, "chart_paths", []) or []
            # 前端只需要文件名
            chart_files = [os.path.basename(p) for p in chart_paths]

            # 把用于"追问"的上下文冻结下来, 供后续 /chat 路由使用
            exec_result = _attr(final, "execution_result", "") or ""
            code_ran = _attr(final, "code", "") or ""
            plan_raw = _attr(final, "plan", []) or []
            plan_md = _format_plan_md(plan_raw, lang)

            # 图表同时打 base64, 让"无状态"部署 (Railway/Render) 也能显示
            charts_b64: dict[str, str] = {}
            for p in chart_paths:
                try:
                    with open(p, "rb") as fh:
                        charts_b64[os.path.basename(p)] = base64.b64encode(fh.read()).decode("ascii")
                except OSError:
                    # 找不到文件就跳过, 前端会回退到 /chart/{fn} 拉取
                    pass

            tasks[task_id]["context"] = {
                "csv_summary": df_summary,
                "user_goal": body.goal,
                "code": code_ran,
                "execution_result": exec_result,
                "final_report": report,
                "language": lang,
                # provider_config 保留 (包含 api_key), 后续追问用同一家 LLM
                "provider_config": cfg,
                # 图表绝对路径, 导出 PPT 时要用
                "chart_paths_abs": list(chart_paths),
                # 透明度面板要用
                "plan_md": plan_md,
            }

            tasks[task_id]["result"] = {"report": report, "charts": chart_files}
            q.put({"event": "result", "data": json.dumps(
                {
                    "report": report,
                    "charts": chart_files,
                    "charts_b64": charts_b64,
                    "plan": plan_md,
                    "code": code_ran,
                    "stdout": exec_result,
                },
                ensure_ascii=False,
            )})
        except Exception as e:
            tasks[task_id]["error"] = repr(e)
            q.put({"event": "error", "data": repr(e)})
        finally:
            tasks[task_id]["done"] = True
            q.put({"event": "_close", "data": ""})

    threading.Thread(target=runner, daemon=True, name=f"analyze-{task_id}").start()
    return {"task_id": task_id}


@app.get("/stream/{task_id}")
async def stream(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "task_id 未找到")
    q: queue.Queue = tasks[task_id]["queue"]

    async def event_gen():
        loop = asyncio.get_event_loop()
        while True:
            try:
                item = await loop.run_in_executor(
                    None, lambda: q.get(timeout=30)
                )
            except queue.Empty:
                # 心跳: 防止反向代理/浏览器掐连接
                yield {"event": "ping", "data": "."}
                continue
            if item.get("event") == "_close":
                break
            yield {"event": item["event"], "data": item["data"]}

    return EventSourceResponse(event_gen())


@app.get("/result/{task_id}")
async def result(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404)
    t = tasks[task_id]
    if not t["done"]:
        return {"status": "running"}
    if t["error"]:
        return {"status": "error", "error": t["error"]}
    return {"status": "done", **(t["result"] or {})}


@app.post("/chat/{task_id}")
async def chat(task_id: str, body: ChatBody):
    """
    基于已完成的分析做追问 (read-only).
    - 不会再跑代码, 只用已有的 csv_summary / code / stdout / report 回答
    - 使用当初跑分析时的同一套 provider_config (同一家 LLM, 同一个 key)
    - 聊天历史只存在内存中, 后端重启即丢; 对 v1 足够用
    """
    if task_id not in tasks:
        raise HTTPException(404, "task_id 未找到")
    t = tasks[task_id]
    if not t["done"]:
        raise HTTPException(409, "分析尚未结束, 请等 result 事件后再提问")
    if t["error"]:
        raise HTTPException(409, f"分析失败, 无法追问: {t['error']}")
    ctx = t.get("context")
    if not ctx:
        raise HTTPException(409, "缺少分析上下文, 无法追问 (请重新分析)")

    user_msg = (body.message or "").strip()
    if not user_msg:
        raise HTTPException(400, "message 不能为空")

    lang = ctx["language"]
    base_system = get_system_prompt("chat", lang)

    # 截断过长的执行结果/报告, 避免吃爆 8K 上下文模型的窗口
    exec_snippet = (ctx.get("execution_result") or "")[-2000:]
    report_snippet = (ctx.get("final_report") or "")[:4000]
    code_snippet = (ctx.get("code") or "")[:2000]

    # 把所有上下文拼到 system prompt 里, 当成"你手上的资料", 这样模型不会把它
    # 误当成"用户的第一条提问"去回答。messages 里只放真实的多轮对话。
    ref_hdr = "你手上的参考资料如下:" if lang == "zh" else "Reference materials at hand:"
    system = (
        f"{base_system}\n\n"
        f"---\n{ref_hdr}\n\n"
        f"{label('data_summary', lang)}:\n{ctx['csv_summary']}\n\n"
        f"{label('analysis_goal', lang)}:\n{ctx['user_goal']}\n\n"
        f"{label('executed_code', lang)}:\n```python\n{code_snippet}\n```\n\n"
        f"{label('exec_stdout_ok', lang)}:\n{exec_snippet}\n\n"
        f"{label('final_report', lang)}:\n{report_snippet}\n"
    )

    # messages 只放真实对话: 历史 (可空) + 本次用户提问
    messages: list[Message] = []
    for turn in t["chat_history"]:
        r = turn.get("role")
        c = turn.get("content") or ""
        if r in ("user", "assistant") and c:
            messages.append(Message(role=r, content=c))
    messages.append(Message(role="user", content=user_msg))

    try:
        provider = get_provider(config=ctx.get("provider_config"))
        reply = provider.chat(
            messages,
            system=system,
            temperature=0.3,
            max_tokens=1024,
        ).strip()
    except Exception as e:
        raise HTTPException(500, f"LLM 调用失败: {e!r}")

    # 追加进历史, 方便下一轮上下文连续
    t["chat_history"].append({"role": "user", "content": user_msg})
    t["chat_history"].append({"role": "assistant", "content": reply})
    return {"reply": reply}


@app.post("/export_pptx/{task_id}")
async def export_pptx(task_id: str):
    """
    一键把分析结果打包成 PPTX 返回给浏览器下载.
    复用 tasks[task_id]['context'] 里冻结的 report + chart_paths_abs.
    """
    if task_id not in tasks:
        raise HTTPException(404, "task_id 未找到")
    t = tasks[task_id]
    if not t["done"]:
        raise HTTPException(409, "分析还没结束, 不能导出")
    if t["error"]:
        raise HTTPException(409, f"分析失败, 无法导出: {t['error']}")
    ctx = t.get("context")
    if not ctx:
        raise HTTPException(409, "缺少分析上下文 (请重新分析)")

    lang = ctx.get("language", "zh")
    title = "业务数据分析报告" if lang == "zh" else "Business Data Analysis Report"

    out_path = OUTPUTS_DIR / f"report_{task_id}.pptx"
    try:
        build_report_pptx(
            title=title,
            user_goal=ctx.get("user_goal", ""),
            report_md=ctx.get("final_report", ""),
            chart_paths=ctx.get("chart_paths_abs", []),
            language=lang,
            out_path=out_path,
        )
    except Exception as e:
        raise HTTPException(500, f"PPT 生成失败: {e!r}")

    download_name = f"analysis_report_{task_id}.pptx"
    return FileResponse(
        str(out_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=download_name,
    )


@app.get("/chart/{filename}")
async def chart(filename: str):
    # 严格只允许 outputs/ 直接子文件 + .png
    safe = Path(filename).name
    if not safe.lower().endswith(".png"):
        raise HTTPException(400, "只允许 .png")
    p = OUTPUTS_DIR / safe
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(str(p), media_type="image/png")


@app.get("/outputs_info")
async def outputs_info():
    """返回 outputs 目录的绝对路径, 供前端展示/复制."""
    return {"path": str(OUTPUTS_DIR.resolve()), "platform": platform.system()}


@app.post("/open_outputs")
async def open_outputs():
    """用系统文件管理器打开 outputs/ 目录.
    只在本地服务端执行 (os.startfile / open / xdg-open), 不暴露给远程。"""
    try:
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        _open_in_file_explorer(OUTPUTS_DIR)
        return {"ok": True, "path": str(OUTPUTS_DIR.resolve())}
    except Exception as e:
        raise HTTPException(500, f"打开失败: {e!r}")
