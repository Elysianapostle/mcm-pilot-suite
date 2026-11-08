# -*- coding: utf-8 -*-
"""数据特征：为每种 chart_type 生成计算片段（注入绘图子脚本，与图同一份数据）,
并提供语言化文本。硬约束：数值必须实际计算，禁止编造。
"""
from __future__ import annotations

import json

# 计算片段针对脚本内已就绪的变量:
#   df            — 已 dropna 的绘图 DataFrame（仅含绘图用列）
#   x_col / y_col / hue_col — 列名(可能为 None)
#   x_is_num, y_is_num      — 数值性
# 片段将 dict 写入 FEAT_OUT 路径 (json)。

_NP_HELPERS = r"""
def _feat_arr(s):
    return np.asarray(list(s), dtype=float)

def _fmt(v):
    if v is None:
        return None
    if isinstance(v, float):
        return round(float(v), 4)
    return v

def _trend_label(slope):
    if slope is None:
        return None
    if slope > 1e-6:
        return "up"
    if slope < -1e-6:
        return "down"
    return "flat"
"""

_LINE_SRC = r"""
def compute_features():
    import numpy as np
    n_raw = len(df)
    if n_raw == 0:
        return {"n": 0}
    g = df.groupby(x_col, sort=False)[y_col].agg(["mean", "std", "count"])
    xs = list(g.index)
    ys = np.asarray(g["mean"].values, dtype=float)
    n = len(ys)
    if x_col and x_is_num:
        try:
            order = np.argsort(np.asarray(xs, dtype=float))
        except (TypeError, ValueError):
            order = np.arange(n)
    else:
        order = np.arange(n)
    xo = [xs[i] for i in order]
    yo = ys[order]
    sl = None
    if n >= 2:
        try:
            k = np.polyfit(np.arange(n), np.asarray(yo), 1)[0]
            sl = float(k)
        except Exception:
            sl = None
    fi = int(np.nanargmax(yo)); vi = int(np.nanargmin(yo))
    feat = {
        "n": n, "n_raw": n_raw,
        "x_first": _fmt(xo[0]), "x_last": _fmt(xo[-1]),
        "y_first": _fmt(yo[0]), "y_last": _fmt(yo[-1]),
        "trend": _trend_label(sl),
        "peak": _fmt(yo[fi]), "peak_x": _fmt(xo[fi]),
        "valley": _fmt(yo[vi]), "valley_x": _fmt(xo[vi]),
        "y_mean": _fmt(float(np.nanmean(yo))),
    }
    if hue_col is not None:
        g2 = df.groupby(hue_col, sort=False)[y_col].agg(["mean", "max"])
        top = g2["mean"].idxmax()
        feat["group_top_mean"] = str(top)
    return feat
"""

_BARH_SRC = r"""
def compute_features():
    import numpy as np
    g = df.groupby(x_col, sort=False)[y_col].mean()
    cats = [str(v) for v in g.index]
    vals = np.asarray(g.values, dtype=float)
    order = np.argsort(vals)[::-1]
    sorted_cats = [cats[i] for i in order]
    sorted_vals = [float(vals[i]) for i in order]
    tot = float(np.nansum(vals))
    top1 = sorted_cats[0] if sorted_cats else None
    top1_share = (sorted_vals[0] / tot * 100.0) if tot and sorted_vals else None
    cum = 0.0; k = 0
    for v in sorted_vals:
        cum += v; k += 1
        if tot and cum / tot >= 0.8:
            break
    feat = {
        "n": len(sorted_vals), "total": round(tot, 4),
        "top": top1, "top_value": _fmt(sorted_vals[0]) if sorted_vals else None,
        "top_share_pct": round(top1_share, 1) if top1_share is not None else None,
        "bottom": sorted_cats[-1] if sorted_cats else None,
        "bottom_value": _fmt(sorted_vals[-1]) if sorted_vals else None,
        "top80_count": k,
        "is_share_like": bool(tot and 0.9 <= tot <= 1.1),
    }
    return feat
"""

_GROUPED_SRC = r"""
def compute_features():
    import numpy as np
    g = df.groupby(x_col, sort=False)[y_col].agg(["mean", "count"])
    means = {str(k): float(v) for k, v in g["mean"].items()}
    tot = sum(means.values()) or 1.0
    feat = {"n": len(df), "groups": means,
            "group_count": len(means),
            "top_group": max(means, key=means.get),
            "top_group_mean": round(max(means.values()), 4),
            "bottom_group": min(means, key=means.get),
            "bottom_group_mean": round(min(means.values()), 4),
            "overall_mean": round(float(np.nanmean(_feat_arr(df[y_col]))), 4)}
    if hue_col is not None:
        pt = df.pivot_table(index=x_col, columns=hue_col, values=y_col, aggfunc="mean")
        ptv = pt.values
        if ptv.shape[0] > 0 and ptv.shape[1] > 0 and not np.all(np.isnan(ptv)):
            r_, c_ = divmod(int(np.nanargmax(ptv)), ptv.shape[1])
            feat["max_cell"] = [str(pt.index[r_]), str(pt.columns[c_])]
            feat["max_cell_value"] = round(float(ptv[r_, c_]), 4)
    return feat
"""

_BOX_SRC = r"""
def compute_features():
    import numpy as np
    v = _feat_arr(df[y_col])
    q1, q3 = np.nanpercentile(v, 25), np.nanpercentile(v, 75)
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = int(np.sum((v < lo) | (v > hi)))
    feat = {"n": len(v), "median": _fmt(float(np.nanmedian(v))),
            "mean": _fmt(float(np.nanmean(v))),
            "q1": _fmt(float(q1)), "q3": _fmt(float(q3)),
            "min": _fmt(float(np.nanmin(v))), "max": _fmt(float(np.nanmax(v))),
            "outliers": outliers}
    if globals().get("_group_col") is not None:
        g = df.groupby(globals()["_group_col"], sort=False)[y_col].median()
        feat["group_medians"] = {str(k): _fmt(float(v)) for k, v in g.items()}
    return feat
"""

_VIOLIN_SRC = r"""
def compute_features():
    import numpy as np
    v = _feat_arr(df[y_col])
    feat = {"n": len(v), "median": _fmt(float(np.nanmedian(v))),
            "mean": _fmt(float(np.nanmean(v))),
            "std": _fmt(float(np.nanstd(v, ddof=1))) if len(v) > 1 else None,
            "min": _fmt(float(np.nanmin(v))), "max": _fmt(float(np.nanmax(v)))}
    if globals().get("_group_col") is not None:
        g = df.groupby(globals()["_group_col"], sort=False)[y_col].median()
        feat["group_medians"] = {str(k): _fmt(float(v)) for k, v in g.items()}
    return feat
"""

_HIST_SRC = r"""
def compute_features():
    import numpy as np
    v = _feat_arr(df[y_col])
    from pandas import Series
    sk = float(Series(v).skew()) if len(v) >= 3 else None
    feat = {"n": len(v), "mean": _fmt(float(np.nanmean(v))),
            "std": _fmt(float(np.nanstd(v, ddof=1))) if len(v) > 1 else None,
            "min": _fmt(float(np.nanmin(v))), "max": _fmt(float(np.nanmax(v))),
            "skew": round(sk, 4) if sk is not None else None}
    return feat
"""

_KDE_SRC = r"""
def compute_features():
    import numpy as np
    v = _feat_arr(df[y_col]); n = len(v)
    if n == 0:
        return {"n": 0}
    sd = float(np.nanstd(v, ddof=1)) if n > 1 else 1.0
    mean = float(np.nanmean(v))
    h = 0.9 * sd / (n ** 0.2) if sd > 0 else (float(np.nanmax(v) - np.nanmin(v)) / 8 or 1.0)
    lo, hi = np.nanmin(v) - 3 * h, np.nanmax(v) + 3 * h
    grid = np.linspace(lo, hi, 256)
    dens = np.mean(np.exp(-0.5 * ((grid[:, None] - v[None, :]) / h) ** 2) / (h * np.sqrt(2 * np.pi)), axis=1)
    peak = float(grid[int(np.argmax(dens))])
    feat = {"n": n, "mean": _fmt(mean), "std": _fmt(sd),
            "min": _fmt(float(np.nanmin(v))), "max": _fmt(float(np.nanmax(v))),
            "peak_x": _fmt(peak), "peak_density": round(float(dens.max()), 4)}
    return feat
"""

_HEAT_SRC = r"""
def compute_features():
    import numpy as np
    if globals().get("CORR_MODE"):
        num = df.select_dtypes(include=[np.number]).dropna(axis=1)
        if num.shape[1] < 2:
            return {"shape": [0, 0], "n_cells": 0, "corr_mode": True}
        c = num.corr().values
        labs = list(num.columns)
        n = len(labs)
        best_p, best_n = None, None
        for i in range(n):
            for j in range(i + 1, n):
                v = c[i, j]
                if np.isnan(v):
                    continue
                if best_p is None or v > best_p[2]:
                    best_p = [str(labs[i]), str(labs[j]), round(float(v), 4)]
                if best_n is None or v < best_n[2]:
                    best_n = [str(labs[i]), str(labs[j]), round(float(v), 4)]
        feat = {"shape": [n, n], "n_cells": n * n, "corr_mode": True,
                "best_positive": best_p, "best_negative": best_n,
                "range": [round(float(np.nanmin(c)), 4), round(float(np.nanmax(c)), 4)]}
        return feat
    mat = MATRIX
    arr = np.asarray(mat, dtype=float)
    if arr.size == 0:
        return {"shape": [0, 0]}
    flat = arr[~np.isnan(arr)]
    r_, c_ = divmod(int(np.nanargmax(arr)), arr.shape[1])
    r2, c2 = divmod(int(np.nanargmin(arr)), arr.shape[1])
    rl = ROW_LABELS if ROW_LABELS is not None else []
    cl = COL_LABELS if COL_LABELS is not None else []
    def nm(i, labels):
        return str(labels[i]) if labels and i < len(labels) else str(i + 1)
    feat = {"shape": list(arr.shape), "n_cells": int(arr.size),
            "min": _fmt(float(np.nanmin(flat))), "max": _fmt(float(np.nanmax(flat))),
            "mean": _fmt(float(np.nanmean(flat))),
            "std": _fmt(float(np.nanstd(flat, ddof=1))) if len(flat) > 1 else None,
            "max_cell": [nm(r_, rl), nm(c_, cl)], "max_cell_value": _fmt(float(arr[r_, c_])),
            "min_cell": [nm(r2, rl), nm(c2, cl)], "min_cell_value": _fmt(float(arr[r2, c2]))}
    return feat
"""

_ERR_SRC = r"""
def compute_features():
    import numpy as np
    g = df.groupby(x_col, sort=False)[y_col].agg(["mean", "std", "count"])
    rows = {}
    for k, row in g.iterrows():
        v = float(row["mean"]); s = float(row["std"]) if row["count"] > 1 else None
        rows[str(k)] = {"mean": round(v, 4), "std": round(s, 4) if s is not None else None,
                        "n": int(row["count"])}
    vals = [r["mean"] for r in rows.values()]
    feat = {"groups": rows, "group_count": len(rows),
            "top_mean": max(rows, key=lambda k: rows[k]["mean"]) if rows else None,
            "bottom_mean": min(rows, key=lambda k: rows[k]["mean"]) if rows else None,
            "mean_range": [round(min(vals), 4), round(max(vals), 4)] if vals else None}
    return feat
"""

_SRC = {
    "line": _LINE_SRC, "barh": _BARH_SRC, "grouped_bar": _GROUPED_SRC,
    "box": _BOX_SRC, "violin": _VIOLIN_SRC, "hist": _HIST_SRC, "kde": _KDE_SRC,
    "heatmap": _HEAT_SRC, "errorbar": _ERR_SRC,
}


def snippet_for(chart_type: str) -> str:
    return _NP_HELPERS + "\n" + _SRC[chart_type]


# ---------------------------------------------------------------- 文本化
_ZH = {
    "up": "整体上升", "down": "整体下降", "flat": "整体平稳",
    "n": "样本量", "range": "范围", "x_range": "X 范围", "time_range": "时间范围",
    "start": "起点", "end": "终点", "peak": "峰值", "valley": "谷值",
    "mean": "均值", "median": "中位数", "std": "标准差", "iqr": "四分位距",
    "q1": "Q1", "q3": "Q3", "min": "最小值", "max": "最大值", "outliers": "异常值",
    "corr": "相关系数", "r2": "R²", "slope": "斜率", "intercept": "截距",
    "top": "最大项", "bottom": "最小项", "total": "合计", "share": "占比",
    "skew": "偏度", "peak_x": "峰值位置", "group_count": "分组数",
}
_EN = {
    "up": "overall rising", "down": "overall falling", "flat": "roughly flat",
    "n": "n", "range": "range", "x_range": "X range", "time_range": "time range",
    "start": "start", "end": "end", "peak": "peak", "valley": "valley",
    "mean": "mean", "median": "median", "std": "std", "iqr": "IQR",
    "q1": "Q1", "q3": "Q3", "min": "min", "max": "max", "outliers": "outliers",
    "corr": "correlation", "r2": "R²", "slope": "slope", "intercept": "intercept",
    "top": "top", "bottom": "bottom", "total": "total", "share": "share",
    "skew": "skewness", "peak_x": "peak at", "group_count": "groups",
}


def _fmt_num(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)          # 非数值（如时间标签）原样返回
    if abs(f) >= 1e5 or (abs(f) < 1e-3 and f != 0):
        return f"{f:.3g}"
    return f"{f:g}"


def _line_text(f, L) -> str:
    parts = []
    if f.get("x_first") is not None and f.get("x_last") is not None:
        parts.append(f"{L['time_range']}: {f['x_first']} 至 {f['x_last']}")
    if f.get("y_first") is not None:
        parts.append(f"{L['start']} {_fmt_num(f['y_first'])}，{L['end']} {_fmt_num(f['y_last'])}")
    if f.get("trend"):
        parts.append(L.get(f["trend"], f["trend"]))
    if f.get("peak") is not None:
        parts.append(f"{L['peak']} {_fmt_num(f['peak'])}"
                     + (f"，{L['peak_x']} {_fmt_num(f['peak_x'])}" if f.get("peak_x") is not None else ""))
    if f.get("valley") is not None:
        parts.append(f"{L['valley']} {_fmt_num(f['valley'])}")
    parts.append(f"{L['n']} {f.get('n')}")
    if f.get("group_top_mean") is not None:
        parts.append(f"{'分组中均值最大' if L is _ZH else 'top group by mean'}: {f['group_top_mean']}")
    return "；".join(parts)


def _barh_text(f, L) -> str:
    parts = [f"{L['n']} {f.get('n')}，{L['total']} {_fmt_num(f.get('total'))}"]
    if f.get("top") is not None:
        share = f"（{L['share']} {f.get('top_share_pct')}%）" if f.get("top_share_pct") is not None else ""
        parts.append(f"{L['top']}: {f['top']} = {_fmt_num(f['top_value'])}{share}")
    if f.get("bottom") is not None:
        parts.append(f"{L['bottom']}: {f['bottom']} = {_fmt_num(f['bottom_value'])}")
    if f.get("top80_count"):
        parts.append(f"Top{f['top80_count']} 累计 ≥80%")
    return "；".join(parts)


def _grouped_text(f, L) -> str:
    parts = [f"{L['n']} {f.get('n')}，{L['group_count']} {f.get('group_count')} 组"]
    if f.get("top_group") is not None:
        parts.append(f"均值最高: {f['top_group']}={_fmt_num(f['top_group_mean'])}")
        parts.append(f"均值最低: {f['bottom_group']}={_fmt_num(f['bottom_group_mean'])}")
    parts.append(f"总体{L['mean']} {_fmt_num(f.get('overall_mean'))}")
    if f.get("max_cell"):
        parts.append(f"最大组合: {f['max_cell'][0]}×{f['max_cell'][1]}={_fmt_num(f['max_cell_value'])}")
    return "；".join(parts)


def _box_text(f, L) -> str:
    parts = [f"{L['n']} {f.get('n')}，{L['median']} {_fmt_num(f.get('median'))}",
             f"{L['mean']} {_fmt_num(f.get('mean'))}",
             f"{L['q1']} {_fmt_num(f.get('q1'))}，{L['q3']} {_fmt_num(f.get('q3'))}",
             f"{L['min']} {_fmt_num(f.get('min'))}，{L['max']} {_fmt_num(f.get('max'))}"]
    if f.get("outliers") is not None:
        parts.append(f"{L['outliers']} {f['outliers']}")
    if f.get("group_medians"):
        parts.append("组中位数 " + "、".join(f"{k}={_fmt_num(v)}" for k, v in f["group_medians"].items()))
    return "；".join(parts)


def _violin_text(f, L) -> str:
    parts = [f"{L['n']} {f.get('n')}，{L['median']} {_fmt_num(f.get('median'))}",
             f"{L['mean']} {_fmt_num(f.get('mean'))}",
             f"{L['std']} {_fmt_num(f.get('std'))}",
             f"{L['min']} {_fmt_num(f.get('min'))}，{L['max']} {_fmt_num(f.get('max'))}"]
    if f.get("group_medians"):
        parts.append("组中位数 " + "、".join(f"{k}={_fmt_num(v)}" for k, v in f["group_medians"].items()))
    return "；".join(parts)


def _hist_text(f, L) -> str:
    parts = [f"{L['n']} {f.get('n')}，{L['mean']} {_fmt_num(f.get('mean'))}",
             f"{L['std']} {_fmt_num(f.get('std'))}",
             f"{L['min']} {_fmt_num(f.get('min'))}，{L['max']} {_fmt_num(f.get('max'))}"]
    if f.get("skew") is not None:
        parts.append(f"{L['skew']} {f['skew']}")
    return "；".join(parts)


def _kde_text(f, L) -> str:
    parts = [f"{L['n']} {f.get('n')}，{L['mean']} {_fmt_num(f.get('mean'))}",
             f"{L['std']} {_fmt_num(f.get('std'))}"]
    if f.get("peak_x") is not None:
        parts.append(f"{L['peak_x']}: {_fmt_num(f['peak_x'])}")
    return "；".join(parts)


def _heat_text(f, L) -> str:
    if f.get("corr_mode"):
        parts = [f"相关系数矩阵 {f.get('shape')[0]}×{f.get('shape')[0]}"]
        if f.get("best_positive"):
            parts.append(f"{L['corr']} 最强正相关: {f['best_positive'][0]} vs {f['best_positive'][1]}"
                         f" (r={f['best_positive'][2]})")
        if f.get("best_negative"):
            parts.append(f"最强负相关: {f['best_negative'][0]} vs {f['best_negative'][1]}"
                         f" (r={f['best_negative'][2]})")
        if f.get("range"):
            parts.append(f"r {L['range']} {f['range'][0]}–{f['range'][1]}")
        return "；".join(parts)
    parts = [f"矩阵 {f.get('shape')[0]}×{f.get('shape')[1]}（{f.get('n_cells')} 格）",
             f"{L['min']} {_fmt_num(f.get('min'))}，{L['max']} {_fmt_num(f.get('max'))}"]
    if f.get("max_cell"):
        parts.append(f"最大格 [{f['max_cell'][0]}, {f['max_cell'][1]}] = {_fmt_num(f['max_cell_value'])}")
        parts.append(f"最小格 [{f['min_cell'][0]}, {f['min_cell'][1]}] = {_fmt_num(f['min_cell_value'])}")
    return "；".join(parts)


def _err_text(f, L) -> str:
    parts = [f"{L['group_count']} {f.get('group_count')} 组"]
    if f.get("mean_range"):
        parts.append(f"均值 {L['range']} {_fmt_num(f['mean_range'][0])}–{_fmt_num(f['mean_range'][1])}")
    if f.get("top_mean") is not None:
        parts.append(f"最高 {f['top_mean']}={_fmt_num(f['groups'][f['top_mean']]['mean'])}"
                     f"±{_fmt_num(f['groups'][f['top_mean']]['std'])} (SD)")
        parts.append(f"最低 {f['bottom_mean']}={_fmt_num(f['groups'][f['bottom_mean']]['mean'])}")
    return "；".join(parts)


def format_features(chart_type: str, f: dict, language: str = "zh") -> str:
    L = _ZH if language != "en" else _EN
    if not f:
        return ""
    if f.get("n") == 0:
        return _L_EMPTY[language]
    if chart_type == "heatmap" and f.get("shape") in ([0, 0], [0, 1]):
        return _L_EMPTY[language]
    fn = {
        "line": _line_text, "barh": _barh_text, "grouped_bar": _grouped_text,
        "box": _box_text, "violin": _violin_text, "hist": _hist_text,
        "kde": _kde_text, "heatmap": _heat_text, "errorbar": _err_text,
    }[chart_type]
    return fn(f, L)


_L_EMPTY = {"zh": "空数据（无有效行）", "en": "empty data (no valid rows)"}


def scatter_features_src() -> str:
    """scatter 的片段单独给（带回归）。"""
    return _NP_HELPERS + r"""
def compute_features():
    import numpy as np
    vx = _feat_arr(df[x_col]); vy = _feat_arr(df[y_col])
    n = len(vx)
    if n < 2:
        return {"n": n}
    mx, my = np.nanmean(vx), np.nanmean(vy)
    sxx = np.nansum((vx - mx) ** 2); syy = np.nansum((vy - my) ** 2)
    sxy = np.nansum((vx - mx) * (vy - my))
    r = float(sxy / np.sqrt(sxx * syy)) if sxx * syy > 0 else None
    slope = float(sxy / sxx) if sxx > 0 else None
    intercept = float(my - (slope or 0) * mx)
    feat = {"n": n, "r": round(r, 4) if r is not None else None,
            "r2": round(r * r, 4) if r is not None else None,
            "slope": round(slope, 4) if slope is not None else None,
            "intercept": round(intercept, 4),
            "x_mean": _fmt(float(mx)), "y_mean": _fmt(float(my))}
    if hue_col is not None:
        rows = {}
        for name, sub in df.groupby(hue_col, sort=False):
            a = _feat_arr(sub[x_col]); b = _feat_arr(sub[y_col])
            if len(a) >= 2:
                ma, mb = np.nanmean(a), np.nanmean(b)
                rr = float(np.nansum((a - ma) * (b - mb)) /
                           np.sqrt(max(np.nansum((a - ma) ** 2) * np.nansum((b - mb) ** 2), 1e-12)))
                rows[str(name)] = round(rr, 4)
        feat["group_r"] = rows
    return feat
"""


def scatter_text(f: dict, language: str = "zh") -> str:
    L = _ZH if language != "en" else _EN
    parts = [f"{L['n']} {f.get('n')}", f"r = {f.get('r')}",
             f"{L['r2']} = {f.get('r2')}"]
    if f.get("slope") is not None:
        parts.append(f"{L['slope']} {f['slope']}，{L['intercept']} {f['intercept']}")
    if f.get("group_r"):
        parts.append("分组 r: " + "、".join(f"{k}={v}" for k, v in f["group_r"].items()))
    return "；".join(parts)


def format_any(chart_type: str, f: dict, language: str = "zh") -> str:
    if chart_type == "scatter":
        return scatter_text(f, language)
    return format_features(chart_type, f, language)