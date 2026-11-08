# mcm-pilot-suite —— 数学建模竞赛（CUMCM / MCM）DSH 一体化工具链

在 [DeepSeek Harness](https://github.com/deepseek-ai)（DSH）上，把「读题 → 建模求解 → 数据图/流程图 → 论文 md → LaTeX PDF」这条数模竞赛流水线变成一组可复用的宿主工具。

本仓库包含两个插件（**互相独立、可单装**）：

| 包 | 提供的能力 | 业务层 |
|---|---|---|
| `packages/mcm-pilot` | `mcm_start`（题目启动 + 缺口问卷 + 建骨架）、`mcm_kb_load`（知识库约束注入）、`mcm_fig_trace`（图←数据←脚本←结果 溯源与重绘）、`mcm_status`（进度看板） | `mcm_pilot.py`（**纯标准库** Python CLI） |
| `packages/plot-tools` | `plot_data_chart`（学术数据图：PDF 矢量 + PNG 预览 + 数据特征）、`generate_diagram`（4 套流程图/技术路线图模板，产出 .drawio + PNG） | `plot_plugin.py` + `plotcore/` + `diagram/`（matplotlib / pandas） |

> 论文写作与 LaTeX 编译**不在本仓库**：那一步由独立的 `paper-writer` 插件承担（`paper_write` 工具）。本仓库只负责把内容与图表准备好、并给出可直接执行的 `paper_write(...)` 调用参数。

## 上手（3 分钟）

**方式 A：让 AI 装（推荐）** —— 把仓库 clone 到本地后，在 DSH 会话里贴：

```
读一下 <仓库路径>/docs/INSTALL.md，按里面的步骤给我装好 mcm-pilot-suite：
1) 跑 node tools/doctor.mjs 先看环境，缺什么告诉我；
2) 跑 tools/install.ps1（Windows）或 tools/install.sh（macOS/Linux）；
3) 装完再跑 node tools/doctor.mjs --full，把 FAIL 项逐条修到 PASS；
4) 最后告诉我需要在 DSH 里做什么（重启/HMR、工作区该放哪）。
不要改仓库里的源码文件，只改环境变量/配置文件。
```

**方式 B：手动**

```bash
git clone <this-repo> mcm-pilot-suite && cd mcm-pilot-suite
node tools/doctor.mjs                 # 先体检：python / 依赖 / 资产
pwsh -File tools/install.ps1          # Windows；或 bash tools/install.sh
node tools/doctor.mjs --full          # 再体检：真实跑一遍 mcm_start 与 plot 自检
```

装完重启 DSH（或等 HMR 重载），会话里就能看到 `mcm_start` / `plot_data_chart` 等工具。

## 依赖一览

| 类型 | 依赖 | 必需？ | 说明 |
|---|---|---|---|
| 运行时 | Node.js ≥ 18 | ✅ | 适配层是 ESM 插件 |
| 宿主 | DeepSeek Harness（含 `@deepseek-ai/dsh-tools`） | ✅ | 提供 `ctx.tools` / `ctx.subprocess` / `ctx.systemPrompt` |
| 运行时 | Python ≥ 3.8 | ✅ | mcm 业务层纯标准库；plot 业务层需要科学计算栈 |
| Python 包 | matplotlib / seaborn / pandas / numpy / openpyxl | 仅 plot | `pip install -r packages/plot-tools/requirements.txt` |
| 字体 | 任意 CJK 字体 | 仅 plot | `PLOT_FONT` 指向 ttf/otf；也会自动探测系统字体（本仓库**不内置**专有字体） |
| 可选 | draw.io 桌面版（CLI） | 仅流程图 PNG | 缺了仍产出 `.drawio`，只是没有 PNG/PDF |
| 可选 | XeLaTeX（TeX Live/MiKTeX） | 仅出 PDF | 由 `paper-writer` 使用 |
| 可选 | `paper-writer` 插件 | 仅出 PDF | 提供 `paper_write`，模板放 `<工作区>/templates/LaTeX/` |
| 可选 | `dsh-pdf-pilot` 插件 | 推荐 | `pdf_case_extract` 读赛题 PDF、`pdf_render_review` 评版面 |

细节与排错见 [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)。

## 换机不炸的接口

所有本机相关的路径都收敛到「**环境变量 → 安装期配置文件**」两层，代码里没有写死任何绝对路径：

| 变量 | 作用 | 默认 |
|---|---|---|
| `MCM_PYTHON` / `PLOT_PYTHON` | Python 解释器 | 配置文件 → 探测（跳过 WindowsApps 空壳） |
| `MCM_WORKSPACE` / `PLOT_WORKSPACE` | 工作区 / 资产根 | 配置文件 → `<repo>/workspace` → 会话 cwd |
| `MCM_PILOT_CLI` | `mcm_pilot.py` 路径 | 包内 → 工作区 `plugin/` |
| `PLOT_FONT` | CJK 字体文件 | 包内 `fonts/` → 系统字体 |
| `MCM_CONFIG` | 配置文件路径 | `$DSH_HOME/mcm-pilot.config.json` → `<repo>/mcm-pilot.config.json` |

安装器会把探测结果写进 `$DSH_HOME/mcm-pilot.config.json`（`{python, plotPython, workspace}`），所以**装一次就固定下来**，不用每次设环境变量。`node tools/doctor.mjs` 会打印每一条的实际解析结果。

## 目录

```
packages/mcm-pilot/        4 个宿主工具 + mcm_pilot.py + 回归测试（tests/run_regression.py）
packages/plot-tools/       2 个宿主工具 + plot_plugin.py + plotcore/ + diagram/
workspace-template/        工作区骨架：knowledge_base/、论文插件需填充的文件/、templates/
tools/                     find-python.mjs / doctor.mjs / install.ps1 / install.sh
docs/                      INSTALL.md / DEPENDENCIES.md / SECURITY.md
```

**工作区**（`workspace-template/` 复制一份改名 `workspace/` 即可）：

```
workspace/
├─ knowledge_base/              *.md 每篇一类约束（front-matter: types/keywords/name）
│                               注意：mcm_kb_load 只扫该目录**根级** md，不递归子目录
├─ 论文插件需填充的文件/          content/00–13 章节模板 + hook.md（mcm_start 复制进新项目）
├─ templates/LaTeX/<模板名>/     paper-writer 用的 LaTeX 模板（本仓库不带模板）
├─ norms/                       paper-writer 的写作规范资产（可选）
└─ outputs/<project>/           mcm_start 生成的产物：results/figures/diagram/content/out/…
```

### 自带的数模知识库（本仓库的"亮点"部分）

`workspace-template/knowledge_base/` 随仓库提供一整套可用的知识库（已脱敏）：`00_国赛总览`（题型决策树）、
`01_题外资料查询指南`、`02_合理假设方法论`、`03_ABC各题型解法特点`、`04_论文写作+插图规范`、`05_历年赛题速查表`、
`06_近五年命题趋势评述`、`07_三人队伍角色分工`、`08_调试错误案例库`、`09_国赛写作扣分错误清单`、
`10_FP反演优化策略`、`11_物理建模方法论`、`12/13_某年题文献与机理积累`（样例）、`论文排版.md`（事故台账）、
`_AGENT_PROTOCOL.md`（多角色协作协议）。`mcm_kb_load` 会按题型/关键词命中后注入项目 `content/hook.md`。

> ⚠️ **只当脚手架，按题做针对性优化**：这些文档给的是"怎么想、按什么顺序做、哪里最容易扣分"，
> 参数、判据、机理耦合方式都必须按你手上的题重新推导；`12`/`13` 是某年具体题目，换题请重写，别照搬。


## 不用 DSH 也能跑业务层

两个业务层都是独立 CLI，可以脱离 DSH 直接命令行使用（便于 CI/回归/排错）：

```bash
python packages/mcm-pilot/mcm_pilot.py --request-file req.json --workdir ./workspace
python packages/plot-tools/plot_plugin.py --request '{"data":[...],"plots":[...]}'
python packages/plot-tools/plot_plugin.py --self-check        # 环境自检快照
python packages/mcm-pilot/tests/run_regression.py             # mcm 业务层回归
```

## 已知限制

- `mcm_kb_load` 不递归子目录（`knowledge_base/**` 只取第一层 `.md`）；要约束生效就把 md 放根级。
- `mcm_start` 的章节骨架来自 `论文插件需填充的文件/content/`；该目录缺失时只建空目录（不报错）。
- 模板匹配用「类型名」（如 `cumcm_1`）而不是目录名（`zh_cumcm_1`）；传错会静默回退内置模板。
- `plot_data_chart` 的 `figure_dir` 必须在 `PLOT_WORKSPACE` 内，`data[].path` 用绝对路径。
- 没有 CJK 字体时图里中文会变方框；`--self-check` 会报 `font.ok=false`。

## 安全

插件是**宿主进程内代码**，安装即等于信任。本仓库的插件自身不联网、不写工作区以外的地方（除安装器），但请务必读一遍 [docs/SECURITY.md](docs/SECURITY.md)，里面写了信任模型、审计点与加固建议。

## 许可

MIT（见 [LICENSE](LICENSE)）。`packages/plot-tools/diagram/references/` 下的模板说明为本文档体系的组成部分，随 MIT 一同发布。仓库不含任何竞赛真题、参赛论文或第三方 LaTeX 模板。
