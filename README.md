# Multi-Agent 企业数据分析系统

**简体中文** | [English](README_EN.md)

上传一份 CSV,四个 LLM Agent 自动规划 → 写代码 → 跑数 → 审查 → 出报告。全程本地、零 API 费用、数据不出电脑。前端支持中英文一键切换,所有 agent prompt / 图表标题 / 报告都会跟随语言输出。

## 系统架构

```
      CSV 上传
         │
         ▼
 ┌───────────────┐   5-7 步分析计划 (JSON)
 │   Planner     │──────────────────────────┐
 └───────────────┘                          │
                                            ▼
                                  ┌───────────────┐
                                  │    Coder      │   pandas + matplotlib 代码
                                  └───────────────┘
                                            │
                                            ▼
                                  ┌───────────────┐
                                  │   Executor    │   子进程 + 60s 超时 + 黑名单
                                  └───────────────┘
                                            │
                                            ▼
                                  ┌───────────────┐
                                  │   Reviewer    │   {passed, feedback}
                                  └───────────────┘
                                     │         │
                                  通过       不通过 (≤3 次)
                                     │         │
                                     ▼         └────→ 回到 Planner
                                  ┌───────────────┐
                                  │   Reporter    │   Markdown 最终报告
                                  └───────────────┘
                                            │
                                            ▼
                                   前端展示图表 + 报告
```

## 快速开始

### 最快 —— 真・一键双击 (Windows)

1. 从 GitHub 下载 zip 并解压 (或 `git clone`)
2. 双击 `start.bat`
   - 第一次双击:自动建 `.venv`, 装全部依赖, 拷贝 `.env` (2-5 分钟, 只发生一次)
   - 以后双击:直接启动, 浏览器自动打开 `http://127.0.0.1:8000`
3. 看到浏览器弹出上传页面即可。

**前提 (一次性, 不可跳过)**:
- Python 3.10+ 已装且勾选了 *Add Python to PATH* (python.org)
- Ollama 已装且后台运行, 模型已拉 (下面第 1 步)

> macOS / Linux 不再随项目发脚本。想跑自己动手: `python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python launch.py`

---

### 1. 准备 Ollama 和模型

```powershell
# 拉两个模型 (一次即可, 都在本地跑, 数据不出电脑)
ollama pull qwen2.5:14b         # 通用推理 (~9 GB)
ollama pull qwen2.5-coder:7b    # 代码专用 (~4.7 GB)

# 确认 Ollama 在后台运行
ollama list
```

### 2. 安装项目依赖

```powershell
cd multi-agent-analyst
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. 配置环境变量

```powershell
copy .env.example .env
# 用 Ollama 跑无需改任何值
# 想切 Claude / DeepSeek 编辑 .env 中的 LLM_PROVIDER 与对应 API Key
```

### 4. CLI 烟测 (推荐先跑这一步)

```powershell
python app_cli.py examples/sample_sales.csv                 # 默认中文输出
python app_cli.py examples/sample_sales.csv --lang en       # 切英文
python app_cli.py examples/sample_sales.csv "找出销售异常点"
```

看到终端打印 Planner / Coder / Executor / Reviewer / Reporter 依次完成,最后出现一份 Markdown 报告即 OK。

### 5. 启动 Web 服务

```powershell
uvicorn backend.main:app --reload --port 8000
```

浏览器打开 http://localhost:8000 → 右上角 **中文 / EN** 切语言 → 拖拽 CSV → 填写目标 → 点"开始分析",实时看进度推送、最终图表和报告。语言选择会同步影响图表标题和最终报告。

## 功能特性

- **本地优先**:默认跑 Ollama,数据不出电脑,零 API 费用
- **一键切换云端**:改 `.env` 的 `LLM_PROVIDER` 即可切到 Claude 或 DeepSeek/OpenAI 兼容,Agent 代码不动
- **中英双语全链路**:agent prompt / 状态推送 / 图表标题轴标签 / 报告 / 前端 UI 全部跟随选择的语言;前端右上角一键切换并记忆到 localStorage
- **Coder 用代码专用模型**:`qwen2.5-coder:7b` 生成 pandas 代码比通用模型更稳
- **SSE 流式进度推送**:前端能实时看到每个 Agent 的状态和消息
- **沙箱执行**:Executor 用子进程 + 60 秒超时 + 黑名单关键字拦截,强制 PYTHONUTF8=1 防 Windows 中文乱码
- **智能重试路由**:执行失败 → Coder 直接改 bug;质量不达标 → Planner 换思路;最多 3 轮后强制收口
- **数据类型守护**:Coder prompt 显式禁掉 `df.to_numpy() / df.corr() / sns.heatmap(df) / df.astype(float)` 等会把字符串列硬转 float 的整表 dtype 操作
- **图表中文友好**:自动配置 Microsoft YaHei / SimHei 字体
- **异常容错**:Planner JSON 解析失败走兜底计划;Reviewer 模型挂了宽松放行;Reporter 挂了仍给最小可读报告

## 技术栈

| 模块 | 技术 |
|---|---|
| Agent 编排 | LangGraph |
| 本地模型 | Ollama (qwen2.5:14b / qwen2.5-coder:7b) |
| 云端备选 | Anthropic Claude / OpenAI 兼容 (DeepSeek / Groq / 千问 / Kimi / 硅基流动) |
| 数据处理 | pandas, numpy, matplotlib, seaborn |
| 后端 | FastAPI + sse-starlette |
| 前端 | 原生 HTML + JavaScript + marked.js |
| Python | 3.10+ |

## 目录结构

```
multi-agent-analyst/
├── agents/                      # 4 个 Agent
│   ├── planner.py              # 规划 5-7 步分析计划
│   ├── coder.py                # 生成 pandas + matplotlib 代码
│   ├── executor.py             # 子进程执行 + 安全检查
│   └── reviewer.py             # 判定是否需要重试
├── workflow/
│   ├── state.py                # 共享状态 AnalysisState
│   ├── graph.py                # LangGraph 编排 + reporter 节点
│   └── i18n.py                 # 中英文 prompt / 状态文案 / UI 字典
├── providers/                  # LLM 抽象层
│   ├── base.py                 # BaseLLMProvider / Message
│   ├── ollama_provider.py
│   ├── anthropic_provider.py
│   ├── openai_provider.py      # 兼容 DeepSeek / Groq / OpenAI 等
│   └── factory.py              # get_provider() / get_coder_provider()
├── backend/
│   └── main.py                 # FastAPI + SSE
├── frontend/
│   └── index.html              # 单文件前端
├── examples/
│   └── sample_sales.csv        # 500 行模拟销售数据
├── outputs/                    # 图表 + 临时脚本 + 上传文件 (运行时自动生成)
├── app_cli.py                  # CLI 调试入口 (支持 --lang)
├── launch.py                   # 跨平台启动器: 起 uvicorn + 轮询 /healthz + 开浏览器
├── start.bat                   # Windows 一键: 首次双击自动建 venv + pip install, 之后直启
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE                     # MIT
├── README.md                   # 本文件
└── README_EN.md                # English version
```

## .env 字段说明

| 字段 | 说明 | 默认 |
|---|---|---|
| `LLM_PROVIDER` | `ollama` / `anthropic` / `openai_compatible` | `ollama` |
| `OLLAMA_HOST` | Ollama 服务地址 | `http://localhost:11434` |
| `OLLAMA_MODEL` | 通用模型 (Planner / Reviewer / Reporter) | `qwen2.5:14b` |
| `OLLAMA_CODER_MODEL` | 代码模型 (Coder 专用) | `qwen2.5-coder:7b` |
| `ANTHROPIC_API_KEY` | Claude API Key | 空 |
| `ANTHROPIC_MODEL` | Claude 模型名 | `claude-sonnet-4-5` |
| `OPENAI_API_KEY` | OpenAI 兼容 API Key | 空 |
| `OPENAI_BASE_URL` | OpenAI 兼容服务地址 | `https://api.deepseek.com/v1` |
| `OPENAI_MODEL` | 模型名 | `deepseek-chat` |
| `MAX_ITERATIONS` | Reviewer 最大重试轮次 | `3` |
| `OUTPUT_LANGUAGE` | 默认输出语言: `zh` (中文) / `en` (英文) | `zh` |

## 常见问题

**Q: 第一次启动很慢?**
第一次加载 qwen2.5:14b 需要把模型读到显存,约 10-20 秒。后续就快了。保持 Ollama 常驻即可。

**Q: 能不能用更小的模型?**
能。把 `.env` 里的 `OLLAMA_MODEL` 改成 `qwen2.5:7b` 或 `llama3.1:8b` 就行。7b 质量略降但速度快 1 倍。

**Q: 能用云端模型吗?**
能。编辑 `.env`:`LLM_PROVIDER=anthropic` 并填 `ANTHROPIC_API_KEY`;或者 `LLM_PROVIDER=openai_compatible` 并填 `OPENAI_*` (DeepSeek / Groq 等都走这个)。

**Q: 报"ANTHROPIC_API_KEY 未设置"?**
你选了 anthropic 但没填 key。要么填上,要么改回 `LLM_PROVIDER=ollama`。

**Q: 前端一直显示"分析中..."?**
八成是后端报错了。切到启动 `uvicorn` 的终端看 traceback,或者打开浏览器 DevTools → Network → `stream/<task_id>` 看 SSE 里推了什么。

**Q: 图表中文是方框?**
只在非 Windows 机器上才会出现。在 `agents/executor.py` 的 `_RUNNER_TEMPLATE` 里把 `Microsoft YaHei` 改成你系统实际存在的中文字体即可。

## 验收清单

- [x] `start.bat` 首次双击自动建 venv + 装依赖, 之后直启
- [x] `python app_cli.py examples/sample_sales.csv` 能跑完并输出报告
- [x] `uvicorn backend.main:app --port 8000` 能启动
- [x] 浏览器 http://localhost:8000 能看到界面
- [x] 前端右上角 **中文 / EN** 可一键切换,UI / 图表 / 报告语言跟随
- [x] 上传 CSV,点分析,能看到 SSE 进度推送
- [x] 分析完成后能看到图表和 Markdown 报告
- [x] `.env` 在 `.gitignore` 中,可以安全 `git init` 推送

## License

MIT — 见 [LICENSE](LICENSE)。
