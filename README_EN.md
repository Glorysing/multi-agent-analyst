# Multi-Agent Data Analyst

[简体中文](README.md) | **English**

Upload a CSV. Four LLM agents plan → write code → run it → review → produce a report. Runs entirely on your machine, zero API cost, data never leaves your computer.

## Architecture

```
      CSV Upload
         │
         ▼
 ┌───────────────┐   5-7 step analysis plan (JSON)
 │    Planner    │──────────────────────────┐
 └───────────────┘                          │
                                            ▼
                                  ┌───────────────┐
                                  │     Coder     │   pandas + matplotlib code
                                  └───────────────┘
                                            │
                                            ▼
                                  ┌───────────────┐
                                  │   Executor    │   subprocess + 60s timeout + denylist
                                  └───────────────┘
                                            │
                                            ▼
                                  ┌───────────────┐
                                  │   Reviewer    │   {passed, feedback}
                                  └───────────────┘
                                     │         │
                                   pass      fail (≤3 rounds)
                                     │         │
                                     ▼         └────→ back to Planner
                                  ┌───────────────┐
                                  │   Reporter    │   final Markdown report
                                  └───────────────┘
                                            │
                                            ▼
                                   Frontend: charts + report
```

## Quick Start

### Windows (true one-click)

1. Download the zip from GitHub and extract (or `git clone`).
2. Double-click `start.bat`.
   - First run: auto-creates `.venv`, pip-installs dependencies, copies `.env` (2-5 min, once only).
   - Later runs: boots straight to `http://127.0.0.1:8000`.

Prerequisites (install once, not bundled):
- Python 3.10+ with "Add Python to PATH" checked (python.org)
- Ollama running in the background with models pulled (see step 1 below)

> macOS / Linux: no shell script is shipped. Run manually:
> `python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python launch.py`

### Manual install

```bash
python -m venv .venv
# Windows:    .venv\Scripts\Activate.ps1
# Unix/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # copy .env.example .env on Windows
```

### Prepare Ollama (local, free)

```bash
ollama pull qwen2.5:14b         # generalist (~9 GB)
ollama pull qwen2.5-coder:7b    # coder-specialist (~4.7 GB)
ollama list                     # verify the daemon is running
```

Want to use Anthropic Claude or DeepSeek/OpenAI-compatible instead? Edit `.env`
and set `LLM_PROVIDER` + the corresponding API key. No code changes required.

### CLI smoke test

```bash
python app_cli.py examples/sample_sales.csv
python app_cli.py examples/sample_sales.csv "Find sales anomalies" --lang en
```

### Web UI

```bash
uvicorn backend.main:app --reload --port 8000
```

Open http://localhost:8000, switch language with the top-right **中文 / EN** toggle,
drop a CSV, fill in your goal, click Start Analysis. You'll see live SSE progress,
the charts, and the final report.

## Features

- **Local-first**: defaults to Ollama. Data never leaves the machine; zero API cost.
- **One-line cloud swap**: change `LLM_PROVIDER` in `.env` to route every agent
  to Anthropic Claude or any OpenAI-compatible endpoint (DeepSeek / Groq / 千问 / Kimi / SiliconFlow). Agent code is untouched.
- **Dedicated coder model**: Coder runs on `qwen2.5-coder:7b` — pandas code quality noticeably better than a generalist 7B.
- **Bilingual (Chinese / English)** across every surface: agent prompts, SSE status
  messages, chart titles and axis labels, the final Markdown report, and the frontend UI.
- **Streaming progress**: SSE pushes per-agent status to the browser in real time.
- **Sandboxed execution**: Executor runs generated code in a subprocess with a 60s timeout and a denylist on dangerous ops.
- **Smart retry routing**: when an iteration fails, execution errors go straight back to **Coder** (fast bugfix); quality failures go back to **Planner** (fresh approach) — up to 3 rounds, then force-finalize.
- **Robust fallbacks**: Planner JSON-parse failure → canned fallback plan. Reviewer LLM crash → pass-through. Reporter crash → minimal readable report from raw stdout.
- **UTF-8 everywhere**: `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8` forced on the subprocess so Windows doesn't mangle Chinese tracebacks.

## Tech Stack

| Component          | Tech                                                                  |
|--------------------|-----------------------------------------------------------------------|
| Agent orchestration| LangGraph                                                             |
| Local models       | Ollama (qwen2.5:14b / qwen2.5-coder:7b)                               |
| Cloud fallback     | Anthropic Claude / OpenAI-compatible (DeepSeek / Groq / 千问 / Kimi / SiliconFlow) |
| Data processing    | pandas, numpy, matplotlib, seaborn                                    |
| Backend            | FastAPI + sse-starlette                                               |
| Frontend           | Vanilla HTML + JS + marked.js                                         |
| Python             | 3.10+                                                                 |

## Directory Layout

```
multi-agent-analyst/
├── agents/                      # 4 Agents
│   ├── planner.py               # 5-7 step analysis plan
│   ├── coder.py                 # generates pandas + matplotlib code
│   ├── executor.py              # subprocess runner + safety checks
│   └── reviewer.py              # decides whether to retry
├── workflow/
│   ├── state.py                 # shared AnalysisState
│   ├── graph.py                 # LangGraph wiring + Reporter node
│   └── i18n.py                  # bilingual prompts / status / UI strings
├── providers/                   # LLM abstraction
│   ├── base.py                  # BaseLLMProvider / Message
│   ├── ollama_provider.py
│   ├── anthropic_provider.py
│   ├── openai_provider.py       # DeepSeek / Groq / OpenAI compatible
│   └── factory.py               # get_provider() / get_coder_provider()
├── backend/
│   └── main.py                  # FastAPI + SSE
├── frontend/
│   └── index.html               # single-file frontend with language switch
├── examples/
│   └── sample_sales.csv         # 500-row mock sales data
├── outputs/                     # charts + temp scripts + uploads (auto-generated)
├── app_cli.py                   # CLI entry (supports --lang)
├── launch.py                    # cross-platform launcher: uvicorn + healthz poll + browser
├── start.bat                    # Windows one-click: first run auto-installs venv + deps
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE                      # MIT
├── README.md                    # Chinese
└── README_EN.md                 # this file
```

## `.env` Reference

| Key                    | Purpose                                               | Default                          |
|------------------------|-------------------------------------------------------|----------------------------------|
| `LLM_PROVIDER`         | `ollama` / `anthropic` / `openai_compatible`          | `ollama`                         |
| `OLLAMA_HOST`          | Ollama daemon URL                                     | `http://localhost:11434`         |
| `OLLAMA_MODEL`         | Generalist model (Planner / Reviewer / Reporter)      | `qwen2.5:14b`                    |
| `OLLAMA_CODER_MODEL`   | Coder-specialist model (Coder only)                   | `qwen2.5-coder:7b`               |
| `ANTHROPIC_API_KEY`    | Claude API key                                        | *(empty)*                        |
| `ANTHROPIC_MODEL`      | Claude model name                                     | `claude-sonnet-4-5`              |
| `OPENAI_API_KEY`       | OpenAI-compatible API key                             | *(empty)*                        |
| `OPENAI_BASE_URL`      | OpenAI-compatible endpoint                            | `https://api.deepseek.com/v1`    |
| `OPENAI_MODEL`         | Model name on that endpoint                           | `deepseek-chat`                  |
| `MAX_ITERATIONS`       | Reviewer retry ceiling                                | `3`                              |
| `OUTPUT_LANGUAGE`      | Default output language: `zh` or `en`                 | `zh`                             |

## FAQ

**Q: First start is slow?**
The first call has to load `qwen2.5:14b` into VRAM (10-20s). Subsequent calls are fast. Keep Ollama running.

**Q: Can I use a smaller model?**
Yes — set `OLLAMA_MODEL=qwen2.5:7b` (or `llama3.1:8b`) in `.env`. Quality drops a bit; speed roughly doubles.

**Q: Can I use a cloud model?**
Sure. Set `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`, or `LLM_PROVIDER=openai_compatible` +
`OPENAI_*` (works for DeepSeek, Groq, 千问, Kimi, SiliconFlow, etc.).

**Q: Frontend stuck on "Analyzing..."?**
Almost always a backend error. Check the `uvicorn` terminal for a traceback, or open
DevTools → Network → `stream/<task_id>` to see the raw SSE events.

**Q: Chart text shows Chinese characters as squares?**
Happens on non-Windows systems that don't have Microsoft YaHei / SimHei installed.
Edit `_RUNNER_TEMPLATE` in `agents/executor.py` and swap in a CJK font that exists on your system (e.g. `Noto Sans CJK SC`, `PingFang SC`, `WenQuanYi Zen Hei`).

## License

MIT — see [LICENSE](LICENSE).
