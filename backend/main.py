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
from workflow.i18n import norm_lang


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
    tasks[task_id] = {"queue": q, "result": None, "done": False, "error": None}

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

            tasks[task_id]["result"] = {"report": report, "charts": chart_files}
            q.put({"event": "result", "data": json.dumps(
                {"report": report, "charts": chart_files}, ensure_ascii=False
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
