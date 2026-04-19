<div align="center">

# 业务数据分析系统

**一个可以在家跑、也能一键上线的多 Agent 业务分析工作流**

**简体中文** · [English](README_EN.md)

![python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-FF6B6B)
![LLM](https://img.shields.io/badge/LLM-Ollama%20%7C%20Claude%20%7C%20Groq%20%7C%20DeepSeek-8B5CF6)
![License](https://img.shields.io/badge/License-MIT-22C55E)

上传 CSV → Planner 规划 → Coder 生成代码 → Executor 跑数 → Reviewer 审查 → Reporter 输出报告
<br/>自带**分析追问**、**一键导 PPT**、**透明度面板**,本地部署零 API 费用,也可 Railway 一键上线。

</div>

---

## 亮点

| 能力 | 说明 |
|---|---|
| **本地优先** | 默认跑 Ollama (qwen2.5:14b + qwen2.5-coder:7b), 数据不出本机, 零 API 费用 |
| **一键切云端** | Ollama / Claude / Groq / DeepSeek / Kimi / 硅基流动 / OpenAI 全部即选即用, API Key 只在当次请求生命周期里存在, 不写磁盘不落日志 |
| **中英双语全链路** | Agent prompt / 状态推送 / 图表标题轴标签 / Markdown 报告 / 前端 UI 全部跟随所选语言, 右上角一键切换 |
| **分析追问 (Follow-up Chat)** | 分析完成后可以继续问 "为什么华南低" "这个结论对 Q4 靠谱吗", 基于冻结的报告/代码/stdout 直接回答, 不重跑代码 |
| **一键导出 PPT** | 报告 + 图表自动拼成 16:9 商务风 .pptx, 封面 / 按章节拆分 / 每图一页 / 致谢页 |
| **透明度面板** | 一个 `<details>` 折叠区就能看到 Planner 的步骤、Coder 生成的完整代码、Executor 的运行输出 |
| **沙箱执行** | Executor 用子进程 + 60s 超时 + 黑名单关键字 + 静态 lint 拦截已知 bug 模式 (比如 `sns.heatmap(df)` 整表强转) |
| **智能重试路由** | 执行失败 → 回 Coder 改 bug; 质量不达标 → 回 Planner 换思路; 最多 3 轮 |
| **Railway 一键部署** | 项目根自带 `Procfile` + `railway.toml`, 推 GitHub 就能出公开 URL, 图表走 base64 内嵌, 不依赖持久卷 |

---

## 三种使用方式

### 1. 本地零成本 (Windows, 真・一键双击)

适合: 数据敏感、想完全离线、长期高频使用。

前置两项, 只装一次:
- **Python 3.10+** (python.org 下载, 安装时勾选 *Add Python to PATH*)
- **Ollama** (ollama.com 下载), 装完拉两个模型:
  ```powershell
  ollama pull qwen2.5:14b         # 通用推理 (~9 GB)
  ollama pull qwen2.5-coder:7b    # 代码专用 (~4.7 GB)
  ```

然后:
1. 下载仓库 zip 解压, 或 `git clone`
2. **双击 `start.bat`**
   - 首次: 自动建 `.venv`, 装依赖, 拷贝 `.env` (2-5 分钟)
   - 之后: 秒启, 浏览器自动弹出 `http://127.0.0.1:8000`
3. 页面里拖 CSV → 写目标 → 开始分析

### 2. 本地 + 云端模型 (只想要 Agent 逻辑, 模型走 API)

同上装 Python 和双击 `start.bat`。启动后在浏览器 "2. 模型设置" 面板选 Claude / Groq / DeepSeek / Kimi / 自定义, 填入 API Key 即可。Key 只用于当次请求, 不会落到 `.env` 或磁盘。

Groq 特别推荐: [console.groq.com/keys](https://console.groq.com/keys) 免费注册, llama-3.3-70b-versatile 推理延迟 ~500ms, 几乎能当本地模型用。

### 3. 公开 Demo (Railway + Groq, 0 元上线)

适合: 想给别人 demo 链接、不想让体验者装 Python。

1. Fork 本仓库到你自己的 GitHub
2. 去 [railway.app](https://railway.app), 点 *New Project → Deploy from GitHub repo*
3. 选中你 fork 的仓库, 它会自动识别 `Procfile` 和 `railway.toml`
4. Railway 发给你一个 `xxx.up.railway.app` 地址, 发出去即可

体验者打开那个地址, 在 "模型设置" 选 **Groq**, 填自己的 Groq key, 就能完整跑通。图表用 base64 嵌回 SSE, 不依赖服务器持久文件。

> 也可以直接把 `GROQ_API_KEY` 设在 Railway 的环境变量里让所有访客共用一个 key, 代价是你自己的额度会被消耗。

---

## macOS / Linux 手动启动

项目不再随发 `.sh` 脚本, 一条命令就够:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python launch.py
```

`launch.py` 会起 uvicorn、轮询 `/healthz` 健康检查就绪后、再自动打开浏览器。

---

## 系统架构

```
                             ┌─────────────────────┐
                CSV + 目标 ──▶│     Planner         │  5-7 步分析计划
                             └──────────┬──────────┘
                                        ▼
                             ┌─────────────────────┐
                             │      Coder          │  pandas + matplotlib
                             └──────────┬──────────┘
                                        ▼
                             ┌─────────────────────┐
                             │     Executor        │  子进程 + 60s 超时 + 黑名单
                             └──────────┬──────────┘
                                        ▼
                             ┌─────────────────────┐  ┌───── 不通过 (≤3 次)
                             │     Reviewer        │──┤
                             └──────────┬──────────┘  └───── 回 Planner / Coder
                                    通过 │
                                        ▼
                             ┌─────────────────────┐
                             │     Reporter        │  Markdown 业务报告
                             └──────────┬──────────┘
                                        ▼
                    ┌───────────────────┼───────────────────────┐
                    ▼                   ▼                       ▼
            前端 SSE 渲染         分析追问 (/chat)         一键导出 PPT
```

---

## 三个 UX 亮点

### 透明度面板

报告下面有一个 "查看分析过程" 折叠区, 展开后能看到:
- **Plan** — Planner 给出的 5-7 步分析计划
- **Code** — Coder 写出来、真正被执行的 pandas + matplotlib 代码
- **Stdout** — Executor 跑这段代码时的运行输出 (stdout + stderr)

这是让非技术用户"敢相信结论"的关键: 结论怎么来的、算对没算对, 都能自己翻开看一眼。

### 分析追问 (Follow-up Chat)

报告出来之后, 右上角 "展开追问" 按钮打开对话框, 可以继续问:
- "华南地区为什么这么低?"
- "这个结论在 Q4 还成立吗?"
- "你可以帮我看看我应该重点做哪个产品线吗?"

模型拿到的是**冻结的**数据摘要 + Coder 代码 + Executor stdout + 最终报告, 基于这些直接回答, 不会再跑一次代码。想换角度分析请回到 "3. 分析目标" 重新运行。

### 一键导出 PPT

报告卡片右上角 "导出 PPT" 按钮: 后端用 python-pptx 现生成一份 16:9 深蓝商务风 `.pptx`:
- 封面页 (大标题 + 分析目标 + 日期)
- 每个 Markdown `##` 章节自动拆成一页, 带左侧强调色条
- 每张图表单独一页, 图文居中不拉伸
- 致谢页

下载直接推到浏览器, 服务器不留本地文件(导出完会缓存一份在 `outputs/` 便于复制)。

---

## 技术栈

| 模块 | 技术 |
|---|---|
| Agent 编排 | LangGraph |
| 本地模型 | Ollama (qwen2.5:14b + qwen2.5-coder:7b) |
| 云端 Provider | Anthropic Claude / Groq / DeepSeek / Moonshot / OpenAI / 自定义 |
| 数据处理 | pandas, numpy, matplotlib, seaborn |
| 后端 | FastAPI + sse-starlette + python-pptx |
| 前端 | 原生 HTML + JavaScript + marked.js (无 build 步骤) |
| 部署 | Railway (Procfile + railway.toml), 或任意支持 uvicorn 的平台 |
| Python | 3.10+ |

---

## 目录结构

<details>
<summary>展开查看</summary>

```
multi-agent-analyst/
├── agents/
│   ├── planner.py          # 5-7 步分析计划
│   ├── coder.py            # pandas + matplotlib 代码生成
│   ├── executor.py         # 子进程执行 + 静态 lint + 黑名单
│   └── reviewer.py         # 判定是否重试
├── workflow/
│   ├── state.py            # AnalysisState 共享状态
│   ├── graph.py            # LangGraph 编排 + reporter 节点
│   └── i18n.py             # 中英文 prompt / 状态文案 / UI 字典 / 追问 prompt
├── providers/
│   ├── base.py             # BaseLLMProvider / Message
│   ├── factory.py          # get_provider / get_coder_provider 分发
│   ├── ollama_provider.py
│   ├── anthropic_provider.py
│   ├── openai_provider.py  # 兼容 DeepSeek / Kimi / 千问 / 硅基流动 / OpenAI
│   └── groq_provider.py    # Groq 薄封装 (在线 Demo 首选)
├── backend/
│   ├── main.py             # FastAPI + SSE + /chat + /export_pptx + /upload
│   └── pptx_export.py      # python-pptx 报告 -> 商务风 .pptx
├── frontend/
│   └── index.html          # 单文件 (HTML + CSS + JS + i18n)
├── outputs/                # 运行时自动生成: 图表 / 临时脚本 / CSV 上传
├── app_cli.py              # CLI 烟测入口 (--lang zh/en)
├── launch.py               # 跨平台启动器: uvicorn + 健康检查 + 开浏览器
├── start.bat               # Windows 一键: 首次自动建 venv + 装依赖
├── Procfile                # Railway / Heroku 启动命令
├── railway.toml            # Railway builder / healthcheck 配置
├── requirements.txt
├── .env.example
├── LICENSE                 # MIT
├── README.md
└── README_EN.md
```

</details>

---

## 配置说明

所有 `.env` 字段都只是**默认值**。前端 "模型设置" 面板的每次覆盖都只影响当次请求, 不会写回 `.env`。

| 字段 | 说明 | 默认 |
|---|---|---|
| `LLM_PROVIDER` | `ollama` / `anthropic` / `openai_compatible` / `groq` | `ollama` |
| `OLLAMA_HOST` | Ollama 服务地址 | `http://localhost:11434` |
| `OLLAMA_MODEL` | 通用模型 | `qwen2.5:14b` |
| `OLLAMA_CODER_MODEL` | 代码模型 | `qwen2.5-coder:7b` |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | Claude 配置 | 空 / `claude-sonnet-4-5` |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | OpenAI 兼容 (DeepSeek 默认) | 空 / DeepSeek / `deepseek-chat` |
| `GROQ_API_KEY` / `GROQ_MODEL` | Groq (免费额度) | 空 / `llama-3.3-70b-versatile` |
| `MAX_ITERATIONS` | Reviewer 最大重试轮次 | `3` |
| `OUTPUT_LANGUAGE` | 默认输出语言 `zh` / `en` | `zh` |

---

## 常见问题

**第一次启动很慢?**
第一次加载 qwen2.5:14b 需要把模型读到显存, 10-20 秒。之后就快了, 保持 Ollama 常驻即可。

**显存只有 8G 跑不动 14b 怎么办?**
换 `OLLAMA_MODEL=qwen2.5:7b` 或 `llama3.1:8b`, 质量会略降但速度快一倍。或者直接切 Groq (免费) / DeepSeek (便宜)。

**能用云端模型吗?**
能。不想改 `.env` 就在前端 "模型设置" 面板选。Groq 有免费额度, DeepSeek 非常便宜, Claude 质量最稳。

**部署到 Railway 后图表显示不出来?**
确认前端拿到的 `charts_b64` 不是空对象。本项目默认每张图都会同时以 base64 推到 SSE, 不依赖持久文件。如果还是空, 看 Railway 日志里 Executor 是不是没跑成功。

**前端一直显示 "分析中..."**
八成后端报错了。本地切到 uvicorn 终端看 traceback, 或浏览器 DevTools → Network → `stream/<task_id>` 看 SSE 最后推了什么事件。

**图表中文显示方框?**
只在非 Windows 环境出现。在 `agents/executor.py` 的 `_RUNNER_TEMPLATE` 里把 `Microsoft YaHei` 改成你系统实际存在的中文字体 (Linux 上常用 `Noto Sans CJK SC`)。

**追问为什么有时候答 "请重新跑分析"?**
正常追问会基于已有数据直接答。只有当问题必须算一个**新数字**或画一张**新图**才会建议重跑 —— 因为追问模式故意不再执行代码, 保证回答速度和数据一致性。

---

## Roadmap

- [ ] 支持 Excel / Parquet 输入
- [ ] 多文件 join 分析 (比如订单表 + 用户表)
- [ ] 对话式持续分析模式 (每次发问都追加新代码块)
- [ ] Playwright 自动化验收

欢迎提 issue / PR。

---

## License

MIT — 见 [LICENSE](LICENSE).
