# 安装（含「让 AI 装」的提示词）

## 0. 前置条件

- **Node.js ≥ 18**（`node -v` 能跑）
- **DeepSeek Harness**（DSH）已装好并能启动 Web GUI
- **Python ≥ 3.8**：`python`/`python3` 能在终端跑；mcm 业务层只需标准库，plot 业务层需要 matplotlib 等
- （可选）**draw.io 桌面版**：只有要 `generate_diagram` 的 PNG 输出时才需要
- （可选）**XeLaTeX** + **paper-writer 插件**：只有要出 PDF 时才需要

> Windows 用户注意：`where python` 若指向 `...\WindowsApps\python.exe`，那是应用商店空壳，插件会报「CLI 无输出」。装个真 Python（python.org / Miniforge / Anaconda 皆可），或者用 `tools/find-python.mjs` 让它替你挑。

## 1. 给 AI 的一句话安装提示词

把下面整段贴给 DSH 里的 agent（把 `<仓库路径>` 换成你的 clone 路径）：

```
目标：把 <仓库路径> 这个 DSH 插件仓库装到本机并能直接用。

步骤：
1. 先跑 `node <仓库路径>/tools/doctor.mjs`，把 PASS/FAIL 如实报给我；
   不要慌着装，先把 FAIL 的原因讲清楚（尤其 python 是否为 WindowsApps 空壳）。
2. 修环境：
   - 没有可用 Python → 告诉我装哪个、装完怎么设 MCM_PYTHON；
   - plot 依赖缺失 → 用最终选定的那个 Python 执行
     `pip install -r <仓库路径>/packages/plot-tools/requirements.txt`；
   - 没有 CJK 字体 → 告诉我设 PLOT_FONT 指向一个 ttf/otf（不要下载字体文件）。
3. 跑安装器：Windows `pwsh -File <仓库路径>/tools/install.ps1`，
   macOS/Linux `bash <仓库路径>/tools/install.sh`。
4. 再跑 `node <仓库路径>/tools/doctor.mjs --full`，直到 FAIL=0；
   然后告诉我：需要重启 DSH 还是等 HMR、工作区应该放哪、怎么启用/停用。
5. 不要修改仓库源码；需要定制时只改环境变量或
   $DSH_HOME/mcm-pilot.config.json。
```

## 2. 手动安装

```bash
git clone <this-repo> mcm-pilot-suite && cd mcm-pilot-suite
node tools/doctor.mjs            # 体检（不写任何东西）
pwsh -File tools/install.ps1     # Windows；加 -Enable 装完即启用，-NoDeps 跳过 pip
# 或
bash tools/install.sh            # macOS/Linux；加 --enable / --no-deps
node tools/doctor.mjs --full     # 真跑一遍 mcm_start + plot --self-check
```

安装器做四件事（幂等，可重复跑）：

1. 找到**实测可用**的 Python（`tools/find-python.mjs`，跳过 WindowsApps 空壳）；
2. `pip install -r packages/plot-tools/requirements.txt`（`-NoDeps` 可跳过）；
3. 复制 `packages/mcm-pilot` → `$DSH_HOME/profiles/node_modules/mcm-pilot`，
   `packages/plot-tools` → `$DSH_HOME/profiles/node_modules/dsh-plot-tools`；
4. 写 `$DSH_HOME/mcm-pilot.config.json`（`python` / `plotPython` / `workspace`），
   并在 `$DSH_HOME/cordis.patch.yml` 追加两条 `insert`（默认带 `disabled: true` 灰度，先备份）。

## 3. 接线（installer 已做；手工安装时照此）

`$DSH_HOME/cordis.patch.yml`（机器级用户补丁层，对每个 profile 生效）：

```yaml
- insert:
    - id: plot-tools
      name: 'dsh-plot-tools'
- insert:
    - id: mcm-pilot
      name: 'mcm-pilot'
```

要点：

- 这个文件**优先级高于 profile 的 `cordis.patch.yml`**（应用顺序：bundles → profile → home）。所以想停用这两个插件，**必须改这里**；在侧边栏「插件」页给该行点开关只会写 profile 层，会被 home 层覆盖（返回 `overridden`）。
- 想停用：给对应行加 `disabled: true`，或删掉那三行。
- 改完：HMR 启用时即时生效，否则重启 DSH（适配层是 ESM 模块，有缓存）。

另一个入口（若你偏好 profile 级管理）：把包作为 bundle 安装
`dsh plugin --profile web add <仓库路径>/packages/plot-tools`，之后用侧边栏「插件」页开关管理。

## 4. 工作区

`mcm_start` 需要一个工作区（放 `knowledge_base/`、`论文插件需填充的文件/`、`templates/`、`outputs/`）：

```bash
cp -R workspace-template workspace      # Windows: Copy-Item -Recurse workspace-template workspace
```

然后二选一：把 `workspace` 的绝对路径写进 `$DSH_HOME/mcm-pilot.config.json` 的 `workspace`，或设 `MCM_WORKSPACE`。

解析顺序：`MCM_WORKSPACE` → 配置文件 `workspace` → `<repo>/workspace` → 会话 cwd（只接受含
`knowledge_base/` / `outputs/` / `论文插件需填充的文件/` 之一者）。

## 5. 验证

```bash
node tools/doctor.mjs --full
```

期望全 PASS。接着在 DSH 会话里试一句：

```
mcm_start(project="2025A", topic="2025 国赛 A 题 …")
```

应该看到问卷或骨架生成。绘图试：`plot_data_chart(data=[{"path":"<某个 csv>"}], plots=[{"output_name":"fig_demo","chart_type":"line","x":"x","y":"y"}])`。

## 6. 卸载

```bash
rm -rf $DSH_HOME/profiles/node_modules/mcm-pilot $DSH_HOME/profiles/node_modules/dsh-plot-tools
rm -f  $DSH_HOME/mcm-pilot.config.json
# 再从 $DSH_HOME/cordis.patch.yml 删掉对应的 insert 块
```
