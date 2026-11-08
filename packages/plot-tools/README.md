# dsh-plot-tools（包内说明）

两个宿主工具，业务层是同目录的 `plot_plugin.py`：

| 工具 | 输入 | 输出 |
|---|---|---|
| `plot_data_chart` | `data[]`（`{path}` 文件 或 `{name,value}` 内联二维数组）+ `plots[]`（`output_name`/`chart_type` 等） | `figures/<output_name>.pdf`（矢量）+ `.png`（预览）+ `data_features` 文本；中间产物在 `figures/_gen/<output_name>/`（`data.json`/`render.py`/`features.json`，可审计） |
| `generate_diagram` | `template`（`roadmap-5band` / `stageflow-3col` / `taskflow-land` / `framework-3col`）+ `content` 或 `description`；`lint_only=true` 只校验 | `.drawio` 源文件 + PNG（需 draw.io CLI；缺则只出 `.drawio`） |

## 约定

- `figure_dir` 必须在 `PLOT_WORKSPACE`（默认包目录）内；`data[].path` 用**绝对路径**。
- 图表类型：`line` / `scatter` / `box` / `violin` / `hist` / `kde` / `barh` / `grouped_bar` / `heatmap` / `errorbar`。
- 输出文件名约束 ASCII（LaTeX 友好）。
- 一次请求 JSON ≤ 15000 字符；大数据务必走文件。

## 字体（本包不内置字体文件）

`plotcore/env.py` 解析顺序：`$PLOT_FONT` → 本目录 `fonts/` → 系统字体（雅黑 / 苹方 / 思源 / Noto / 文泉驿…）。
找不到时**不会崩**，会退化成系统字体名（中文可能显示方框），并在 `--self-check` 里报 `font.ok=false`。

## 依赖与自检

```bash
python plot_plugin.py --self-check      # 快照：解释器/依赖/字体/drawio/渲染脚本
python plot_plugin.py --request '{"data":[{"name":"d","value":[["x","y"],[0,1],[1,2]]}],"plots":[{"output_name":"fig_demo","chart_type":"line","x":"x","y":"y"}]}'
```

依赖：`pip install -r requirements.txt`（matplotlib seaborn pandas numpy openpyxl）。
流程图 PNG 另需 draw.io 桌面版（`drawio --version` 可用即可）。

## 流程图模板

四套模板的字段规范在 `diagram/references/*.md`（`roadmap-5band.md`、`stageflow-3col.md`、`taskflow-land.md`、`framework-3col.md`）。写 `content` 前先读对应 md；`lint_only=true` 可以先只校验字段与容量，再渲染。
