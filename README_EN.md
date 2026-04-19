<div align="center">

# Multi-Agent Data Analyst

**A multi-agent business analytics workflow — run locally or deploy online in one click**

[简体中文](README.md) · **English**

![python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-FF6B6B)
![LLM](https://img.shields.io/badge/LLM-Ollama%20%7C%20Claude%20%7C%20Groq%20%7C%20DeepSeek-8B5CF6)
![License](https://img.shields.io/badge/License-MIT-22C55E)

Upload CSV → Planner designs a plan → Coder writes code → Executor runs it → Reviewer checks → Reporter outputs the report
<br/>Built-in **follow-up chat**, **one-click PPT export**, and **transparency panel**. Runs locally at zero cost, or deploy to Railway in minutes.

</div>

---

## Highlights

| Capability | Description |
|---|---|
| **Local-first** | Defaults to Ollama (qwen2.5:14b + qwen2.5-coder:7b). Data never leaves your machine, zero API cost. |
| **One-click cloud swap** | Ollama / Claude / Groq / DeepSeek / Kimi / SiliconFlow / OpenAI — all switchable from the UI. API keys exist only for the duration of the request; never written to disk or logs. |
| **Bilingual end-to-end** | Agent prompts, SSE status messages, chart titles & axis labels, Markdown report, and frontend UI all follow the selected language. Toggle top-right. |
| **Follow-up Chat** | After the report is generated, keep asking — "Why is the South region low?", "Does this hold for Q4?" — the model answers against the frozen report/code/stdout without re-running the pipeline. |
| **One-click PPT Export** | Report + charts auto-assembled into a 16:9 business-style `.pptx`: cover page, one slide per `##` section, one slide per chart, acknowledgements page. |
| **Transparency Panel** | A collapsible `<details>` block shows the Planner's step-by-step plan, the exact code Coder generated, and the Executor's full stdout — so anyone can verify the conclusion. |
| **Sandboxed Execution** | Executor runs code in a subprocess with a 60s timeout, a dangerous-op denylist, and a static lint pass that intercepts known crash patterns (e.g. `sns.heatmap(df)`, `df.astype(float)` on mixed-type frames) before they ever run. |
| **Smart Retry Routing** | Execution failure → back to **Coder** (fast bugfix, no re-planning); quality failure → back to **Planner** (fresh approach). Max 3 rounds, then force-finalize. |
| **Railway One-Click Deploy** | `Procfile` + `railway.toml` included. Push to GitHub, connect Railway, get a public URL. Charts are base64-embedded in SSE — no persistent volume needed. |

---

## Three Ways to Use

### 1. Local, Zero Cost (Windows — true one-click)

Best for: sensitive data, fully offline use, frequent long-term use.

Install once:
- **Python 3.10+** (python.org — check *Add Python to PATH*)
- **Ollama** (ollama.com), then pull two models:
  ```powershell
  ollama pull qwen2.5:14b         # generalist (~9 GB)
  ollama pull qwen2.5-coder:7b    # coder-specialist (~4.7 GB)
  ```

Then:
1. Download the repo zip and extract, or `git clone`.
2. **Double-click `start.bat`**
   - First run: auto-creates `.venv`, installs dependencies, copies `.env` (2–5 min, once only).
   - Later runs: boots instantly, browser opens at `http://127.0.0.1:8000`.
3. Drop a CSV → type your goal → click Start Analysis.

### 2. Local App + Cloud Model (just want the agent logic, model via API)

Same as above — install Python and double-click `start.bat`. Once running, open the **Model Settings** panel in the browser, choose Claude / Groq / DeepSeek / Kimi / custom, and paste your API key. The key is used only for that request and is never persisted.

**Groq is especially recommended:** sign up free at [console.groq.com/keys](https://console.groq.com/keys). `llama-3.3-70b-versatile` has ~500 ms latency — nearly as fast as a local model.

### 3. Public Demo (Railway + Groq — free, no install for visitors)

Best for: sharing a demo link, letting others try it without installing anything.

1. Fork this repo to your own GitHub.
2. Go to [railway.app](https://railway.app) → *New Project → Deploy from GitHub repo*.
3. Select your fork. Railway auto-detects `Procfile` and `railway.toml`.
4. In Railway **Variables**, add `GROQ_API_KEY` and `LLM_PROVIDER=groq`.
5. Railway gives you an `xxx.up.railway.app` URL — share it.

Visitors open the URL, pick **Groq** in Model Settings, paste their own Groq key, and get the full experience. Charts are base64-embedded in SSE, so no server-side file storage is needed.

> You can also set `GROQ_API_KEY` as a Railway environment variable so all visitors share one key — at the cost of your own free quota.

---

## macOS / Linux

No shell script is shipped. One command:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python launch.py
```

`launch.py` starts uvicorn, polls `/healthz` until ready, then opens the browser automatically.

---

## Architecture

```
                         ┌─────────────────────┐
          CSV + goal ───▶│       Planner       │  5-7 step analysis plan
                         └──────────┬──────────┘
                                    ▼
                         ┌─────────────────────┐
                         │        Coder        │  pandas + matplotlib code
                         └──────────┬──────────┘
                                    ▼
                         ┌─────────────────────┐
                         │      Executor       │  subprocess + 60s timeout + denylist
                         └──────────┬──────────┘
                                    ▼
                         ┌─────────────────────┐  ┌── fail (≤3 rounds)
                         │      Reviewer       │──┤
                         └──────────┬──────────┘  └── exec fail → Coder
                                pass│                  quality fail → Planner
                                    ▼
                         ┌─────────────────────┐
                         │      Reporter       │  Markdown business report
                         └──────────┬──────────┘
                                    ▼
               ┌────────────────────┼────────────────────┐
               ▼                    ▼                    ▼
       Frontend SSE render    Follow-up Chat        PPT Export
```

---

## Three UX Highlights

### Transparency Panel

Below the report, a collapsible "View Analysis Process" section reveals:
- **Plan** — the Planner's 5–7 step analysis plan
- **Code** — the exact pandas + matplotlib code that was executed
- **Stdout** — the Executor's full runtime output (stdout + stderr)

This is what makes non-technical users trust the conclusion: they can see exactly how it was derived.

### Follow-up Chat

After the report appears, click "Open Follow-up" in the top-right corner and keep asking questions:
- "Why is the South region performing so poorly?"
- "Is this conclusion still valid for Q4?"
- "Which product line should I prioritize?"

The model answers against the **frozen** data summary + Coder code + Executor stdout + final report — no re-run. To explore a completely different angle, go back to the goal input and start a new run.

### One-Click PPT Export

Click "Export PPT" in the report card header. The backend uses `python-pptx` to generate a 16:9 dark-blue business `.pptx`:
- Cover slide (title + goal + date)
- Each Markdown `##` section → one slide, with a colored accent bar
- Each chart → its own slide, centered without distortion
- Acknowledgements slide

The file is streamed directly to your browser. No permanent copy is kept on the server.

---

## Tech Stack

| Module | Tech |
|---|---|
| Agent orchestration | LangGraph |
| Local models | Ollama (qwen2.5:14b + qwen2.5-coder:7b) |
| Cloud providers | Anthropic Claude / Groq / DeepSeek / Moonshot / OpenAI / custom |
| Data processing | pandas, numpy, matplotlib, seaborn |
| Backend | FastAPI + sse-starlette + python-pptx |
| Frontend | Vanilla HTML + JavaScript + marked.js (no build step) |
| Deployment | Railway (Procfile + railway.toml), or any uvicorn-compatible platform |
| Python | 3.10+ |

---

## Directory Layout

<details>
<summary>Expand</summary>

```
multi-agent-analyst/
├── agents/
│   ├── planner.py          # 5-7 step analysis plan
│   ├── coder.py            # pandas + matplotlib code generation
│   ├── executor.py         # subprocess runner + static lint + denylist
│   └── reviewer.py         # pass / retry decision
├── workflow/
│   ├── state.py            # shared AnalysisState
│   ├── graph.py            # LangGraph wiring + Reporter node + retry routing
│   └── i18n.py             # bilingual prompts / status text / UI strings / chat prompts
├── providers/
│   ├── base.py             # BaseLLMProvider / Message
│   ├── factory.py          # get_provider() / get_coder_provider()
│   ├── ollama_provider.py
│   ├── anthropic_provider.py
│   ├── openai_provider.py  # DeepSeek / Kimi / Qwen / SiliconFlow / OpenAI compatible
│   └── groq_provider.py    # Groq thin wrapper (recommended for online demo)
├── backend/
│   ├── main.py             # FastAPI + SSE + /chat + /export_pptx + /upload
│   └── pptx_export.py      # python-pptx: Markdown report → business .pptx
├── frontend/
│   └── index.html          # single-file (HTML + CSS + JS + i18n)
├── outputs/                # runtime: charts / temp scripts / uploads
├── app_cli.py              # CLI smoke-test entry (--lang zh/en)
├── launch.py               # cross-platform launcher: uvicorn + healthz poll + open browser
├── start.bat               # Windows one-click: auto venv + deps on first run
├── Procfile                # Railway / Heroku start command
├── railway.toml            # Railway builder + healthcheck config
├── requirements.txt
├── .env.example
├── LICENSE                 # MIT
├── README.md               # Chinese
└── README_EN.md            # this file
```

</details>

---

## `.env` Reference

All `.env` values are **defaults only**. Anything set in the frontend Model Settings panel overrides them for that request and is never written back to `.env`.

| Key | Purpose | Default |
|---|---|---|
| `LLM_PROVIDER` | `ollama` / `anthropic` / `openai_compatible` / `groq` | `ollama` |
| `OLLAMA_HOST` | Ollama daemon URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Generalist model (Planner / Reviewer / Reporter) | `qwen2.5:14b` |
| `OLLAMA_CODER_MODEL` | Coder-specialist model | `qwen2.5-coder:7b` |
| `ANTHROPIC_API_KEY` | Claude API key | *(empty)* |
| `ANTHROPIC_MODEL` | Claude model name | `claude-sonnet-4-5` |
| `OPENAI_API_KEY` | OpenAI-compatible API key | *(empty)* |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint | `https://api.deepseek.com/v1` |
| `OPENAI_MODEL` | Model name on that endpoint | `deepseek-chat` |
| `GROQ_API_KEY` | Groq API key | *(empty)* |
| `MAX_ITERATIONS` | Reviewer retry ceiling | `3` |
| `OUTPUT_LANGUAGE` | Default output language: `zh` or `en` | `zh` |

---

## FAQ

**Q: The first analysis is slow — is that normal?**
Yes. The first call loads `qwen2.5:14b` into VRAM (10–20s). Subsequent calls are fast. Keep Ollama running in the background.

**Q: Can I use a smaller model to go faster?**
Yes — set `OLLAMA_MODEL=qwen2.5:7b` (or `llama3.1:8b`) in `.env`. Output quality drops a bit; speed roughly doubles.

**Q: How do I use a cloud model?**
Set `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`, or `LLM_PROVIDER=openai_compatible` + `OPENAI_*` (compatible with DeepSeek, Groq, Qwen, Kimi, SiliconFlow, etc.). For Groq specifically, use `LLM_PROVIDER=groq` + `GROQ_API_KEY`.

**Q: The frontend is stuck on "Analyzing..."**
Almost always a backend error. Check the uvicorn terminal for a traceback, or open DevTools → Network → the `stream/<task_id>` request to read the raw SSE events.

**Q: Chart text shows boxes instead of Chinese characters**
This happens on non-Windows systems without Microsoft YaHei / SimHei. Edit `_RUNNER_TEMPLATE` in `agents/executor.py` and replace the font with one available on your system (e.g. `Noto Sans CJK SC`, `PingFang SC`, `WenQuanYi Zen Hei`).

**Q: I deployed to Railway but charts aren't showing**
Make sure you're on the latest commit — chart data is now base64-embedded in SSE events and rendered directly in the browser, with no dependency on server-side file storage.

---

## License

MIT — see [LICENSE](LICENSE).
