# 安全说明（请安装前读一遍）

## 1. 信任模型

DSH 插件是**宿主进程内的 JavaScript 代码**，不是沙箱里的脚本。一旦接线（`cordis.patch.yml` 里有它的行），它就能：

- 读写你本机的任意文件（受工作区沙箱策略约束的部分除外：**宿主侧插件代码本身不受工作区沙箱限制**）；
- 起子进程（本仓库用 `ctx.subprocess.spawn` 起 Python）；
- 往每轮对话注入系统提示（本仓库 mcm-pilot 会注入一段工作流说明）；
- 申请工具权限、读写会话状态。

所以「装插件」≈「把本机权限交给这段代码」。**只装你读过、或来源可信的插件。**

## 2. 本仓库的插件实际做了什么

`packages/mcm-pilot`
- 注册 4 个工具 + 一段系统提示；工具调用时：写一个**临时**请求文件（系统 temp 目录，调用结束即删）→ `spawn(python, mcm_pilot.py --request-file … --workdir <工作区>)` → 把 stdout 的 JSON 原样透传。
- 业务层 `mcm_pilot.py`：只用标准库；写 `outputs/<project>/…`（骨架、`project.json`、`content/hook.md` 的 KB 段、`figure_manifest.json` 补登记）、读 `knowledge_base/`、`论文插件需填充的文件/`、`templates/`。
- 「补登记」只追加 `outputs/<project>/figures/figure_manifest.json` 里的条目；不会跨出工作区。
- **不联网**、不读凭据、不修改 DSH 安装本体。

`packages/plot-tools`
- 注册 2 个工具；`spawn(python, plot_plugin.py --request <json>)`，cwd = `PLOT_WORKSPACE`。
- 业务层生成一个**可审计**的渲染脚本（`figures/_gen/<fig>/render.py`）再执行它；读写都在 `PLOT_WORKSPACE` 内（`figure_dir` 必须在其中）。
- 会调用 draw.io CLI（如果装了）把 `.drawio` 导出 PNG；**不联网**（draw.io 以本地 `--export` 模式运行）。

安装器 `tools/install.ps1` / `install.sh`
- 会修改：`$DSH_HOME/mcm-pilot.config.json`（新建）、`$DSH_HOME/cordis.patch.yml`（追加 insert，先备份为 `.bak-<时间戳>`）、`$DSH_HOME/profiles/node_modules/`（复制两个包）、以及往你选定的 Python 里 `pip install` 依赖。
- 不会：改 DSH 安装目录、改系统环境变量（除非你自己 `setx`）、联网（除 pip 下载依赖）。

## 3. 审计清单（10 分钟）

1. `packages/mcm-pilot/index.js` / `packages/plot-tools/index.js`：都在 300 行内，只看 `apply()` 里注册了什么、`spawn` 了什么。
2. 业务层是纯 Python：`mcm_pilot.py` 只看写文件的地方；`plotcore/` 里 `run_command` / `data_chart.py` 的 `render.py` 生成逻辑。
3. 全局搜危险面：`curl`/`fetch`/`http`/`eval`/`exec(` / `rm -rf` / `shutil.rmtree`。
4. 你的插件目录里出现你不认识的文件改动 → 立即停用（见 §4）。

## 4. 停用 / 隔离

```yaml
# $DSH_HOME/cordis.patch.yml —— 给该行加 disabled: true（保留代码便于再启用）
- insert:
    - id: mcm-pilot
      name: 'mcm-pilot'
      disabled: true
```

- **必须改这个 home 级文件**：应用顺序是 bundles → profile patch → home patch，home 层优先级最高；侧边栏「插件」页的行开关写的是 profile 层，对 home 层插入的行会返回 `overridden`。
- 想彻底移除：删掉 insert 块 + 删 `profiles/node_modules/{mcm-pilot,dsh-plot-tools}` + 删 `mcm-pilot.config.json`。
- `disabled: true` 只是不加载，包仍在磁盘上；**不是卸载**，别把「停用」当成「已清除」。

## 5. 加固建议

- 把 DSH 会话的权限模式保持在 `workspace-write`（本仓库不需要 `danger-full-access` 也能跑；业务层产物都在工作区内）。
- 工作区里放的是你的论文与数据：`outputs/`、`knowledge_base/` 建议单独备份，别提交到公开仓库。
- 从 GitHub 装第三方 fork 时，至少 diff 一遍 `index.js` 与 `mcm_pilot.py` 的差异。
- 不要给 Agent 开「自动安装/自动启用插件」的循环；启用前的最后一步留给人。

## 6. 报告问题

发现可疑行为/漏洞：开 issue 时**不要贴**真实路径、token、论文数据；用最小复现 + 版本号即可。
