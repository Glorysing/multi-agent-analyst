"""
Multi-Agent Data Analyst - Smart Launcher
=========================================

为什么需要这个脚本而不是直接 batch 启动 uvicorn:
1. 旧版 start.bat 在固定 sleep 3 秒后开浏览器, 但 LangGraph + pandas + ollama 客户端
   冷启动经常需要 5-15 秒, 浏览器抢跑就会看到 ERR_CONNECTION_REFUSED.
2. 如果 uvicorn 因为依赖缺失 / .env 错误 / 端口被占用 而启动失败,
   batch 窗口会瞬间关闭, 用户根本看不到 traceback.

这个脚本做的事:
1. 在启动前先 try-import 核心依赖, 立刻发现"包装到全局 Python 而不是 venv"这种坑
2. 检查 8000 端口是否已被占用
3. 子进程启 uvicorn, stdout/stderr 转发到当前控制台
4. 后台线程轮询 /healthz, 真正 ready 之后才 webbrowser.open
5. 如果 uvicorn 异常退出, 显示退出码并 input() 卡住, 让用户能看到错误

所有平台 (Windows / macOS / Linux) 都跑同一份 Python 代码, 不再维护两套 batch/shell 逻辑。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.environ.get("MAD_PORT", "8000"))
URL = f"http://{HOST}:{PORT}"


# ----------------------------------------------------------------------
# Pretty print helpers (ANSI 在新版 Windows Terminal / PowerShell 都正常)
# ----------------------------------------------------------------------
def _c(code: str, s: str) -> str:
    if os.environ.get("NO_COLOR"):
        return s
    return f"\033[{code}m{s}\033[0m"

def info(msg: str) -> None:    print(_c("36", "[launch] ") + msg, flush=True)
def ok(msg: str) -> None:      print(_c("32", "[launch] ") + msg, flush=True)
def warn(msg: str) -> None:    print(_c("33", "[launch] ") + msg, flush=True)
def err(msg: str) -> None:     print(_c("31", "[launch] ") + msg, flush=True)


def _hold_window() -> None:
    """让 batch 窗口不要瞬间关闭。"""
    if sys.stdin and sys.stdin.isatty():
        try:
            input("\nPress Enter to exit...")
        except (KeyboardInterrupt, EOFError):
            pass


def _pick_python() -> str:
    """优先 .venv/Scripts/python.exe (Win) 或 .venv/bin/python (Unix)."""
    if os.name == "nt":
        cand = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        cand = ROOT / ".venv" / "bin" / "python"
    if cand.exists():
        return str(cand)
    # 没 venv 就用当前解释器, 至少能跑起来
    warn(f".venv 未找到, 退回当前 Python: {sys.executable}")
    warn("  (正常情况下 start.bat 会自动帮你建 .venv)")
    return sys.executable


def _check_imports(py: str) -> bool:
    """用目标 python 试 import 关键依赖, 提前发现"包装错位置"问题。"""
    info("检查依赖...")
    # 注意: 必须显式 `import importlib.util`, 单 `import importlib` 在 <3.12 不会把 util 子模块加载上来
    probe = (
        "import sys, importlib, importlib.util; "
        "missing = [m for m in ['fastapi','uvicorn','pandas','matplotlib',"
        "'seaborn','langgraph','sse_starlette','dotenv'] "
        "if importlib.util.find_spec(m) is None]; "
        "print('|'.join(missing)) if missing else print('OK')"
    )
    try:
        out = subprocess.check_output(
            [py, "-c", probe], text=True, encoding="utf-8", errors="replace",
            timeout=30,
        ).strip()
    except Exception as e:
        err(f"依赖检查失败: {e!r}")
        return False
    if out == "OK":
        ok("依赖齐全")
        return True
    err(f"以下依赖未装: {out}")
    err("解决办法: 删掉 .venv\\ 目录后重新双击 start.bat (会自动重建),")
    err("或手动跑:")
    err(f"  {py} -m pip install -r requirements.txt")
    return False


def _port_busy(host: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def _wait_health(url: str, server_proc: subprocess.Popen, deadline_s: float = 60.0) -> bool:
    """轮询 /healthz, 直到 200 或者 server_proc 退出。"""
    start = time.time()
    last_msg = 0.0
    while time.time() - start < deadline_s:
        if server_proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url + "/healthz", timeout=1.5) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        # 每 5 秒提示一次 "还在等"
        if time.time() - last_msg > 5:
            info(f"还在等服务起来... ({int(time.time() - start)}s)")
            last_msg = time.time()
        time.sleep(0.4)
    return False


def _open_browser_when_ready(server_proc: subprocess.Popen) -> None:
    if _wait_health(URL, server_proc):
        ok(f"服务就绪 -> 打开浏览器 {URL}")
        try:
            webbrowser.open(URL)
        except Exception as e:
            warn(f"自动开浏览器失败: {e!r}, 请手动访问 {URL}")
    else:
        warn(f"等服务超时或服务退出, 浏览器未打开. 请检查上面的错误.")


def main() -> int:
    print()
    print(_c("1;36", "=== Multi-Agent Data Analyst ==="))
    print(f"项目目录: {ROOT}")
    print(f"目标地址: {URL}")
    print()

    # 1. 端口检查
    if _port_busy(HOST, PORT):
        warn(f"端口 {PORT} 已被占用. 可能已有一个实例在跑, 直接打开 {URL}")
        try:
            webbrowser.open(URL)
        except Exception:
            pass
        return 0

    # 2. 选 Python
    py = _pick_python()
    info(f"Python 解释器: {py}")

    # 3. 依赖检查
    if not _check_imports(py):
        _hold_window()
        return 1

    # 4. 启 uvicorn
    info(f"启动 uvicorn (port={PORT})...")
    print()
    cmd = [
        py, "-m", "uvicorn", "backend.main:app",
        "--host", "0.0.0.0", "--port", str(PORT),
    ]
    # 透传 PYTHONUTF8 防 Windows 中文乱码
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env)
    except FileNotFoundError as e:
        err(f"无法启动 Python 子进程: {e}")
        _hold_window()
        return 1

    # 5. 后台线程开浏览器
    t = threading.Thread(target=_open_browser_when_ready, args=(proc,), daemon=True)
    t.start()

    # 6. 阻塞等待 uvicorn (Ctrl+C 直接传给子进程)
    try:
        rc = proc.wait()
    except KeyboardInterrupt:
        info("收到 Ctrl+C, 关闭服务...")
        proc.terminate()
        try:
            rc = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = proc.wait()
        return 0

    if rc != 0:
        err(f"uvicorn 异常退出 (code={rc})")
        err("常见原因:")
        err("  - 端口 8000 被占用 (上面应该有 [Errno 10048])")
        err("  - import 错误 (检查 backend/main.py 上方的 traceback)")
        err("  - Ollama 未启动 (会在第一次调用时才暴露)")
        _hold_window()
    return rc


if __name__ == "__main__":
    sys.exit(main())
