# mcm-pilot（包内说明）

4 个宿主工具，业务层是同目录的 `mcm_pilot.py`（**纯标准库**，Python ≥3.8 即可跑）：

| 工具 | 作用 | 关键返回 |
|---|---|---|
| `mcm_start(project, topic, …)` | 读题 → 找缺口（协作模式/语言/模板/题号/交付文件）→ 返回 `needs_input + questions[]`，或直接建 `outputs/<project>/{content,figures,diagram,out,results,solver,scripts}` + `project.json` | `decided` / `questions` / `created` / `next[]` |
| `mcm_kb_load(project, types=[…], keywords=[…])` | 扫 `knowledge_base/`（**只看根级 md**）命中后，把约束追加进 `outputs/<project>/content/hook.md` 的【KB】段，并写 `content/kb_hook.md` 溯源 | `loaded[]` / `injected_paths[]` / `totals` |
| `mcm_fig_trace(project, action=inspect\|register\|redraw)` | 图 ← 数据 ← 脚本 ← 结果 的溯源巡检，维护 `figures/figure_manifest.json`；`redraw` 给出重跑/重绘指令 | `traces[]` / `redraw_commands` |
| `mcm_status(project)` | 缺口看板：results/figures/manifest/content/out/main.pdf | `counts` / `missing[]` / `next[]` |

## 设计要点

- **两层**：`index.js` 只做参数校验、临时请求文件、`spawn` 与 JSON 透传（< 320 行）；所有业务在 `mcm_pilot.py`，可以脱离 DSH 直接跑（见下）。
- **不硬编码路径**：`$MCM_PILOT_CLI` / `$MCM_PYTHON` / `$MCM_WORKSPACE` → 安装期配置文件 → 包内/工作区/cwd。
- **不抛栈**：任何异常都折成 `{ok:false, errors:[…]}`，并带上「怎么修」的提示（`node tools/doctor.mjs`）。
- **数值唯一事实源**约定：正文/图/摘要里的每个数字都应能落到 `outputs/<project>/results/*.json`；图的数据先聚合为 `figures/fig_*.csv` 再画。

## 直接跑（不经 DSH）

```bash
# 请求文件 {"tool":"start","args":{"project":"2025A","topic":"…"}}
python mcm_pilot.py --request-file req.json --workdir /path/to/workspace
python tests/run_regression.py        # 业务层回归（fixture 全链路，退出码 0 即全过）
```

## 与其他插件的关系

- 出图：`dsh-plot-tools`（`plot_data_chart` / `generate_diagram`）。`mcm_fig_trace` 的 redraw 指令会点名它。
- 成文：`paper-writer`（`paper_write`）。`mcm_start` 的 `next[]` 会给出可直接复制的调用参数。
- 读题/评版面（可选）：`dsh-pdf-pilot`（`pdf_case_extract` / `pdf_render_review`）。

三者是**协同契约**而非硬依赖：缺了不会崩，只是对应步骤做不了。
