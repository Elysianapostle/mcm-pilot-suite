# -*- coding: utf-8 -*-
"""绘图代码生成器：按图表规格生成独立的 matplotlib/seaborn 渲染子脚本。

生成脚本结构:
1. [插件注入] 预置段: 中文字体注入(CJK_FONT)、全局 rcParams、COLORS/FIG_* 常量；
   此后“绘图代码”部分不再设置字体/主题（sns.set_theme、font.rcParams 修改均禁止）。
2. 数据装载: 读 data.json（仅绘图列）→ df。
3. 特征计算片段: 每种 chart_type 独立 compute_features_<t>()，与绘图同一份 dropna 数据 → features.json。
4. 渲染循环: ITEMS 展开（subplots[] 亦然），逐项画图、写 (a)(b)(c)、存 PNG(300dpi)+PDF。
"""
from __future__ import annotations

import json
import textwrap

from . import features as _feat


def _ind(src: str, n: int) -> str:
    """dedent 到 0、去掉首尾空行，再统一缩进 n 空格（保证生成的 if/块层级正确）。"""
    body = textwrap.dedent(src).strip("\n")
    if not body:
        return ""
    return textwrap.indent(body, " " * n)

# ---------------------------------------------------------------- 预置段
def prelude(font_path: str) -> str:
    from pathlib import Path as _Path

    if font_path and _Path(font_path).is_file():
        font_block = (
            f'_FONT_PATH = r"{font_path}"\n'
            "_fp = font_manager.FontProperties(fname=_FONT_PATH)\n"
            "CJK_FONT = _fp.get_name()\n"
            "font_manager.fontManager.addfont(_FONT_PATH)\n"
            'rcParams["font.family"] = "sans-serif"\n'
            'rcParams["font.sans-serif"] = [CJK_FONT, "Microsoft YaHei", "SimHei", '
            '"Noto Sans CJK SC", "PingFang SC", "DejaVu Sans"]\n'
        )
    else:
        # 没找到字体文件时不让生成的脚本崩：退化到系统字体名（中文可能显示方框）
        font_block = (
            "# 未找到 CJK 字体文件（可设 PLOT_FONT 指向 ttf/otf 后重跑）：退化到系统字体名\n"
            'rcParams["font.family"] = "sans-serif"\n'
            'rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", '
            '"PingFang SC", "Hiragino Sans GB", "WenQuanYi Zen Hei", "DejaVu Sans"]\n'
        )
    return f'''# -*- coding: utf-8 -*-
# 本文件由 plot_data_chart 生成（生成式绘图代码，可审计）。禁止手工改动其中 rcParams/字体设置。
import os, sys, json
from pathlib import Path
os.environ.setdefault("PYTHONUTF8", "1")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager, rcParams
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import pandas as pd
import seaborn as sns

# ---- [插件注入] 环境预配置：中文字体 + 全局 rcParams（绘图代码禁止重复设置）----
{font_block}rcParams["axes.unicode_minus"] = False
rcParams["font.size"] = 11
rcParams["axes.linewidth"] = 1.2
rcParams["axes.spines.top"] = False
rcParams["axes.spines.right"] = False
rcParams["figure.dpi"] = 300
rcParams["savefig.dpi"] = 300
rcParams["savefig.bbox"] = "tight"
rcParams["legend.frameon"] = False

COLORS = {{"primary": "#2E5B88", "secondary": "#E85D4C", "tertiary": "#4A9B7F",
          "neutral": "#7F7F7F", "light": "#B8D4E8"}}
DEFAULT_COLORS = list(COLORS.values())
FIG_SINGLE = (5, 4)
FIG_DOUBLE = (10, 4)
FIG_WIDE = (8, 3)
FIG_SQUARE = (6, 6)
_CMAP = LinearSegmentedColormap.from_list("dsh_heat", [COLORS["light"], COLORS["primary"]], N=256)
'''


def data_block(data_path: str) -> str:
    return f'''
# ---- [插件注入] 数据装载（特征计算与绘图共用同一份数据）----
DATA_PATH = r"{data_path}"
raw = json.loads(Path(DATA_PATH).read_text(encoding="utf-8"))
df = pd.DataFrame(raw.get("frame", []))

def _is_num_series(s):
    if len(s) == 0:
        return True
    try:
        pd.to_numeric(s.dropna())
        return True
    except (TypeError, ValueError):
        return False
'''


# ---------------------------------------------------------------- 各类型绘图源码
_DRAWS = {}

_DRAWS["line"] = r'''
    _c = COLORS[_COLOR_KEY]
    if hue_col is None:
        g = dd.groupby(x_col, sort=bool(x_is_num))[y_col].agg(["mean", "std", "count"])
        xx = np.arange(len(g)) if not x_is_num else g.index.values.astype(float)
        yy = g["mean"].values
        if ci:
            se = g["std"].values / np.sqrt(g["count"].values)
            ax.fill_between(xx, yy - 1.96 * se, yy + 1.96 * se, color=_c, alpha=0.22, linewidth=0)
        ax.plot(xx, yy, color=_c, linewidth=1.8)
        if not x_is_num:
            ax.set_xticks(np.arange(len(g)), [str(v) for v in g.index], fontsize=9)
    else:
        H = DEFAULT_COLORS
        for i, name in enumerate(_hue_order):
            sub = dd[dd[hue_col] == name]
            gg = sub.groupby(x_col, sort=bool(x_is_num))[y_col].agg(["mean", "std", "count"])
            xx = np.arange(len(gg)) if not x_is_num else gg.index.values.astype(float)
            yy = gg["mean"].values
            if ci:
                se = gg["std"].values / np.sqrt(gg["count"].values)
                ax.fill_between(xx, yy - 1.96 * se, yy + 1.96 * se,
                                color=H[i % len(H)], alpha=0.15, linewidth=0)
            ax.plot(xx, yy, color=H[i % len(H)], linewidth=1.6, label=str(name))
        if not x_is_num:
            ax.set_xticks(np.arange(len(gg)), [str(v) for v in gg.index], fontsize=9)
        ax.legend(title=str(hue_col), loc="best", frameon=False)
'''

_DRAWS["scatter"] = r'''
    _c = COLORS[_COLOR_KEY]
    if hue_col is None:
        ax.scatter(dd[x_col], dd[y_col], s=26, color=_c, alpha=0.8,
                   edgecolor="white", linewidth=0.4)
    else:
        for i, name in enumerate(_hue_order):
            sub = dd[dd[hue_col] == name]
            ax.scatter(sub[x_col], sub[y_col], s=26,
                       color=DEFAULT_COLORS[i % len(DEFAULT_COLORS)], alpha=0.8,
                       edgecolor="white", linewidth=0.4, label=str(name))
        ax.legend(title=str(hue_col), loc="best", frameon=False)
    if feat.get("r") is not None:
        k = feat.get("slope") or 0.0
        b = feat.get("intercept") or 0.0
        xv = np.linspace(np.nanmin(dd[x_col]), np.nanmax(dd[x_col]), 50)
        ax.plot(xv, k * xv + b, color=_c, linestyle="--", linewidth=1.2)
        ax.text(0.02, 0.97, f"r = {feat['r']:g}", transform=ax.transAxes,
                va="top", fontsize=10)
'''

_DRAWS["box"] = r'''
    if hue_col is not None:
        sns.boxplot(data=dd, x=hue_col, y=y_col, ax=ax, palette=DEFAULT_COLORS,
                    order=_hue_order, fliersize=3)
    elif x_col is not None:
        sns.boxplot(data=dd, x=x_col, y=y_col, ax=ax, color=COLORS[_COLOR_KEY],
                    order=_x_order, fliersize=3)
    else:
        sns.boxplot(data=dd, y=y_col, ax=ax, color=COLORS[_COLOR_KEY],
                    width=0.45, fliersize=3)
'''

_DRAWS["violin"] = r'''
    if hue_col is not None:
        sns.violinplot(data=dd, x=hue_col, y=y_col, ax=ax, palette=DEFAULT_COLORS,
                       order=_hue_order, inner="quart", linewidth=1)
    elif x_col is not None:
        sns.violinplot(data=dd, x=x_col, y=y_col, ax=ax, color=COLORS[_COLOR_KEY],
                       order=_x_order, inner="quart", linewidth=1)
    else:
        sns.violinplot(data=dd, y=y_col, ax=ax, color=COLORS[_COLOR_KEY],
                       inner="quart", linewidth=1)
'''

_DRAWS["hist"] = r'''
    sns.histplot(data=dd, x=y_col, kde=True, ax=ax, color=COLORS[_COLOR_KEY],
                 edgecolor="white", linewidth=0.5)
'''

_DRAWS["kde"] = r'''
    sns.kdeplot(data=dd, x=y_col, ax=ax, color=COLORS[_COLOR_KEY], fill=True,
                alpha=0.25, linewidth=1.6)
'''

_DRAWS["barh"] = r'''
    _c = COLORS[_COLOR_KEY]
    g = dd.groupby(x_col, sort=False)[y_col].mean()
    cats = [str(v) for v in g.index]
    vals = g.values.astype(float)
    order = np.argsort(vals)
    ax.barh(np.array(cats)[order], vals[order], color=_c, height=0.62)
    if len(vals) <= 15:
        for j, v in enumerate(vals[order]):
            ax.text(v, j, f"  {v:g}", va="center", fontsize=9, color="#404040")
'''

_DRAWS["grouped_bar"] = r'''
    _c = COLORS[_COLOR_KEY]
    if hue_col is None:
        g = dd.groupby(x_col, sort=False)[y_col].mean()
        ax.bar(np.arange(len(g)), g.values, color=_c, width=0.6)
        ax.set_xticks(np.arange(len(g)), [str(v) for v in g.index], fontsize=9)
    else:
        sns.barplot(data=dd, x=x_col, y=y_col, hue=hue_col, errorbar=None,
                    palette=DEFAULT_COLORS, hue_order=_hue_order, ax=ax)
        ax.legend(title=str(hue_col), loc="best", frameon=False)
'''

_DRAWS["heatmap"] = r'''
    if globals().get("CORR_MODE"):
        _num = dd.select_dtypes(include=[np.number]).dropna(axis=1)
        if _num.shape[1] < 2:
            raise ValueError("相关系数热力图需要 ≥2 个数值列且无缺失")
        MATRIX = _num.corr().values
        ROW_LABELS = [str(c) for c in _num.columns]
        COL_LABELS = [str(c) for c in _num.columns]
    sns.heatmap(np.asarray(MATRIX, dtype=float), ax=ax, cmap=_CMAP,
                annot=bool(min(MATRIX_SHAPE) <= 10), fmt=".2g", linewidths=0.4,
                linecolor="#ffffff", xticklabels=COL_LABELS or True,
                yticklabels=ROW_LABELS or True, cbar=True,
                cbar_kws={"shrink": 0.85})
    ax.set_xticklabels(ax.get_xticklabels(), rotation=0, fontsize=8)
    ax.set_yticklabels(ax.get_yticklabels(), fontsize=8)
'''

_DRAWS["errorbar"] = r'''
    g = dd.groupby(x_col, sort=False)[y_col].agg(["mean", "std", "count"])
    xs = np.arange(len(g))
    yerr = np.where(g["count"] > 1, g["std"].values, 0.0)
    ax.errorbar(xs, g["mean"].values, yerr=yerr, fmt="o-", color=COLORS[_COLOR_KEY],
                capsize=3, linewidth=1.5, markersize=5)
    ax.set_xticks(xs, [str(v) for v in g.index], fontsize=9)
'''

_AX_SETUP = r'''
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    for _ann in _annotations:
        if not isinstance(_ann, dict):
            continue
        if "line" in _ann and _ann["line"] is not None:
            ax.axhline(_ann["line"], color=COLORS["neutral"], linestyle="--", linewidth=1.0)
            if _ann.get("text"):
                ax.text(0.99, 0.0, _ann["text"], transform=ax.get_yaxis_transform(),
                        ha="right", va="bottom", fontsize=9, color="#404040")
        elif "vline" in _ann and _ann["vline"] is not None:
            ax.axvline(_ann["vline"], color=COLORS["neutral"], linestyle="--", linewidth=1.0)
            if _ann.get("text"):
                ax.text(_ann["vline"], 0.99, _ann["text"], transform=ax.get_xaxis_transform(),
                        va="top", ha="left", fontsize=9, color="#404040")
        elif "at" in _ann and _ann["at"]:
            ax.annotate(_ann.get("text", ""), xy=tuple(_ann["at"]),
                        xytext=(8, 8), textcoords="offset points", fontsize=9,
                        arrowprops=dict(arrowstyle="->", color=COLORS["secondary"], lw=1.0))
'''


# ---------------------------------------------------------------- 主脚本装配
def build_script(*, font_path: str, data_path: str, feat_path: str, png_path: str,
                 pdf_path: str, items: list[dict], base_figsize: tuple,
                 nrows: int, ncols: int) -> str:
    """items: 已解析绘图项（含 chart_type/x/y/hue/ci/annotations/... 及对应的特征片段替换）。"""
    items_json = repr(items)  # repr 生成的是合法 Python 字面量（true/false/null 不适用）

    # 特征计算函数: 每种类型一个 compute_features_<t>()（片段直接内嵌, 不依赖外置包）
    helpers = _feat._NP_HELPERS
    defs = []
    used = sorted({it["chart_type"] for it in items})
    for t in used:
        if t == "scatter":
            body = _feat.scatter_features_src()
        else:
            body = _feat.snippet_for(t)
        renamed = body.replace("def compute_features():", f"def compute_features_{t}():", 1)
        # 去掉 helpers 段重复定义（snippet_for 里带了 _NP_HELPERS）
        renamed = renamed.replace(_feat._NP_HELPERS, "").strip()
        defs.append(renamed)

    draw_dispatch = "\n\n".join(
        f'if it["chart_type"] == "{t}":\n' + _ind(_DRAWS[t], 12)
        for t in used)

    fig_w, fig_h = base_figsize[0] * ncols, base_figsize[1] * nrows

    # 渲染循环的“绘制+注解”块整体在代码侧构造（模板在列 0 插入，杜绝前缀只作用于首行的问题）
    subplot_label = 'if len(axes_list) > 1:\n    ax.text(-0.08, 1.02, f"({chr(97 + idx)})", transform=ax.transAxes,\n            va="bottom", ha="right", fontsize=12)\n'
    try_body = (
        "    try:\n"
        + _ind(draw_dispatch, 8) + "\n"
        + _ind(_AX_SETUP, 8) + "\n"
        + _ind(subplot_label, 8)
        + "\n    except Exception as e:  # noqa: BLE001\n"
        + '        _item_error(idx, "draw", f"{e}")\n'
    )
    tail_item = (
        "    _hue_order = list(it.get(\"hue_order\") or [])\n"
        "    _x_order = list(it.get(\"x_order\") or [])\n"
        "    _annotations = list(it.get(\"annotations\") or [])\n"
        "    _COLOR_KEY = it.get(\"color\") or \"primary\"\n"
        "    xlabel = it.get(\"xlabel\") or \"\"\n"
        "    ylabel = it.get(\"ylabel\") or \"\"\n"
        "    ci = bool(it.get(\"ci\", False))\n"
        + try_body
    )

    return f'''{prelude(font_path)}
{data_block(data_path)}

# ---- [插件注入] 特征计算片段（与绘图同一份数据）----
{helpers}
{chr(10).join(defs)}

ITEMS = {items_json}
FEAT_OUT = r"{feat_path}"
PNG_OUT = r"{png_path}"
PDF_OUT = r"{pdf_path}"

_item_errors = []

def _item_error(idx, etype, msg):
    _item_errors.append({{"index": idx, "type": etype, "message": msg}})

n_items = len(ITEMS)
nrows, ncols = {nrows}, {ncols}
fig, axes = plt.subplots(nrows, ncols, figsize=({fig_w:.2f}, {fig_h:.2f}))
axes_list = np.atleast_1d(axes).ravel()
feats = []
for idx, it in enumerate(ITEMS):
    ax = axes_list[idx]
    _g = globals()
    chart_type = it["chart_type"]
    x_col = it.get("x")
    y_col = it.get("y")
    hue_col = it.get("hue")
    x_is_num = bool(it.get("x_is_num", False))
    _g["x_col"] = x_col
    _g["y_col"] = y_col
    _g["hue_col"] = hue_col
    _g["x_is_num"] = x_is_num
    _g["MATRIX"] = it.get("matrix") or []
    _g["MATRIX_SHAPE"] = (len(it.get("matrix") or []), len((it.get("matrix") or [None])[0] or [])) if (it.get("matrix") or []) else (0, 0)
    _g["ROW_LABELS"] = it.get("row_labels")
    _g["COL_LABELS"] = it.get("col_labels")
    try:
        if chart_type == "heatmap":
            dd = df  # heatmap 不参与 df 行过滤
        else:
            _cols = [c for c in [x_col, y_col, hue_col] if c]
            dd = df.dropna(subset=_cols).copy()
        if chart_type != "heatmap" and (not isinstance(dd, pd.DataFrame) or len(dd) == 0):
            raise ValueError("无有效数据行（在绘图列上全部缺失）")
        _g["df"] = dd
        _g["CORR_MODE"] = bool(it.get("corr_mode", False))
        _g["_group_col"] = hue_col or x_col
        feat = globals()["compute_features_" + chart_type]()
        feats.append(feat)
    except Exception as e:  # noqa: BLE001
        feats.append({{"n": 0}})
        _item_error(idx, "data", f"{{e}}")
        ax.set_visible(False)
        continue

{tail_item}
for i in range(n_items, len(axes_list)):
    axes_list[i].set_visible(False)

# ---- [插件注入] x 轴刻度防重叠：类别多时自动旋转/稀疏化（fig_dsh_sub 重叠问题修复）----
def _tune_xticks(_ax):
    try:
        import math as _math
        _ax.figure.canvas.draw()
        _labs = [t.get_text() for t in _ax.get_xticklabels()]
    except Exception:
        return
    n = len(_labs)
    if n <= 8:
        return  # 少刻度不干预
    for _t in _ax.get_xticklabels():
        _t.set_rotation(45)
        _t.set_ha("right")
        _t.set_fontsize(9)
    if n > 16:
        # 更多刻度：稀疏化（保留首末 + 均匀抽样），避免旋转后仍拥挤
        _step = max(2, int(_math.ceil(n / 12)))
        _keep = list(range(0, n, _step))
        if (n - 1) not in _keep:
            _keep.append(n - 1)
        _locs = list(_ax.get_xticks())
        _ax.set_xticks([_locs[i] for i in _keep if i < len(_locs)])
        _ax.set_xticklabels([_labs[i] for i in _keep if i < len(_labs)])
        for _t in _ax.get_xticklabels():
            _t.set_rotation(45)
            _t.set_ha("right")
            _t.set_fontsize(9)

for _ax in axes_list[:n_items]:
    _tune_xticks(_ax)

fig.tight_layout()
Path(FEAT_OUT).write_text(json.dumps(feats, ensure_ascii=False), encoding="utf-8")
fig.savefig(PNG_OUT, dpi=300, bbox_inches="tight")
fig.savefig(PDF_OUT, bbox_inches="tight")
plt.close(fig)
print("RENDER_OK items=", n_items, "errors=", len(_item_errors))
if _item_errors:
    Path(FEAT_OUT).with_suffix(".errors.json").write_text(
        json.dumps(_item_errors, ensure_ascii=False), encoding="utf-8")
    sys.exit(3)
'''