# 依赖与换机风险表

## 1. 依赖矩阵

| 依赖 | 谁需要 | 版本/位置 | 缺失症状 | 修法 |
|---|---|---|---|---|
| Node.js | 全部（适配层） | ≥ 18 | DSH 插件加载报语法/模块错误 | 升级 Node |
| `@deepseek-ai/dsh-tools` | plot-tools（`defineTool`） | 随 DSH 提供 | 插件树加载失败 | 用 DSH 自带 profile，别手动装这个包 |
| Python | 全部（业务层） | ≥ 3.8，**实测可用** | `CLI 无输出` / `stdout 非 JSON` | `MCM_PYTHON` 指向真解释器；`node tools/find-python.mjs` |
| matplotlib + seaborn | plot 数据图 | ≥3.6 / ≥0.12 | `module 'matplotlib' has no attribute …` 或直接 ImportError | `pip install -r packages/plot-tools/requirements.txt` |
| pandas + numpy + openpyxl | plot 数据图 | pandas ≥1.5 | 读 csv/xlsx 失败 | 同上 |
| CJK 字体文件 | plot 中文 | 任意 ttf/otf | 图里中文变方框，`font.ok=false` | `PLOT_FONT=<字体路径>` |
| draw.io 桌面版 | 流程图 PNG/PDF | ≥ 21 | 只有 `.drawio`，没有 PNG | 装 draw.io，或手动导出（`diagram/export_figure.py` 里有命令） |
| XeLaTeX（TeX Live/MiKTeX） | 出 PDF | 任意近年版本 | `paper_write` 编译失败 | 装 TeX；或只用 md 交付 |
| `paper-writer` 插件 | 出 PDF | 独立仓库 | 没有 `paper_write` 工具 | 装 paper-writer（本仓库不含） |
| `dsh-pdf-pilot` 插件 | 读赛题 PDF / 评版面 | 可选 | 只能靠文本读题 | 装 pdf-pilot |
| `ctex` / 模板资产 | 中文 LaTeX | 放 `<工作区>/templates/LaTeX/<模板>/` | `paper_write` 回退内置模板 | 从 paper-writer 获取模板 |

## 2. 「换台机器就炸」的六个经典坑（本仓库都已处理，记录在此便于排错）

| # | 坑 | 现象 | 本仓库怎么处理 |
|---|---|---|---|
| 1 | **WindowsApps python 空壳** | `python` 存在但什么都不干；插件报 `CLI 无输出`；`stdout 非 JSON` | `tools/find-python.mjs` 会**实测** `python -c "import sys;print(sys.executable)"`，并显式排除 `WindowsApps` 路径 |
| 2 | **conda 环境未激活** | 子进程 `0xC06D007F` / numpy 导入硬崩（找不到 `Library\bin` 的 OpenBLAS） | `plotcore/env.py:_conda_env_paths()` 依据解释器旁的 `conda-meta/` 自动把 `Library\bin`/`DLLs` 前置到 PATH |
| 3 | **管道 stdio 失败** | Windows 下 `python.exe` 管道初始化失败 `0xC0000142` | 业务层一律**文件重定向**（`cmd /c … > log 2>&1`；POSIX 用 `sh -c`），不走管道 |
| 4 | **字体**：专有字体不能分发 | 开源版若内置 `simhei.ttf` 属侵权；不带又中文乱码 | 探测 `PLOT_FONT` → 包内 `fonts/` → 系统字体（雅黑/苹方/思源/Noto/文泉驿）；都没有则**不让脚本崩**，退化为系统字体名并在 `--self-check` 报 `font.ok=false` |
| 5 | **工作区位置** | 换了目录/换了人，产物散落、`mcm_start` 找不到资产 | `MCM_WORKSPACE` / 配置文件 → `<repo>/workspace` → 会话 cwd 多级解析；适配层还校验 `knowledge_base/` 等标记 |
| 6 | **插件层级** | 在 GUI 里关掉插件却不生效（home patch 覆盖 profile） | 文档明确：这两个插件的行在 home patch，**改 `$DSH_HOME/cordis.patch.yml`** 才有效；GUI 行开关对 home 层返回 `overridden` |

## 3. 环境变量与配置文件优先级

```
python     : $MCM_PYTHON / $PLOT_PYTHON → config.python/plotPython → 探测（py -0p / conda / Programs / PATH）
workspace  : $MCM_WORKSPACE / $PLOT_WORKSPACE → config.workspace → <repo>/workspace → 会话 cwd
CLI 路径    : $MCM_PILOT_CLI → 包内 → <workspace>/plugin/
字体        : $PLOT_FONT → <repo>/packages/plot-tools/fonts/ → 系统字体目录
配置文件    : $MCM_CONFIG → $DSH_HOME/mcm-pilot.config.json → <repo>/mcm-pilot.config.json → ~/.mcm-pilot.config.json
```

配置文件示例：

```json
{
  "python": "C:/Users/me/miniforge3/envs/mathmodel/python.exe",
  "plotPython": "C:/Users/me/miniforge3/envs/mathmodel/python.exe",
  "workspace": "D:/mcm-workspace"
}
```

## 4. 自检

```bash
node tools/doctor.mjs          # 环境/资产/接线
node tools/doctor.mjs --full   # 额外真实跑 mcm_start 冒烟 + plot --self-check
python packages/plot-tools/plot_plugin.py --self-check   # 只看绘图侧快照（JSON）
```
