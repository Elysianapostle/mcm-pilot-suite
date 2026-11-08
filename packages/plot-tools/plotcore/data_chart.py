# -*- coding: utf-8 -*-
"""数据图流程：请求解析/校验 → 数据装载 → 解析绘图项 → 生成脚本 → 子进程渲染 → 特征 → 组装输出契约。"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import env, features, plotgen

CHART_TYPES = {"line", "scatter", "box", "violin", "hist", "kde", "barh",
               "grouped_bar", "heatmap", "errorbar"}
COLOR_KEYS = {"primary", "secondary", "tertiary", "neutral", "light"}
FIG_SIZES = {"single": (5, 4), "double": (10, 4), "wide": (8, 3), "square": (6, 6)}
OUTPUT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")

_CT_ZH = {
    "line": "折线图", "scatter": "散点图", "box": "箱线图", "violin": "小提琴图",
    "hist": "直方图", "kde": "密度图", "barh": "水平条形图", "grouped_bar": "分组柱状图",
    "heatmap": "热力图", "errorbar": "误差棒图",
}


def _fmt_gb(value):
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return str(value)


def _notna(v):
    try:
        return not pd.isna(v)
    except (TypeError, ValueError):
        return True


# ---------------------------------------------------------------- 数据装载
def _read_csv_multi(p: Path) -> pd.DataFrame:
    last = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            for sep in (",", ";", "\t"):
                try:
                    return pd.read_csv(p, encoding=enc, sep=sep)
                except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as e:
                    last = e
        except UnicodeDecodeError as e:
            last = e
    raise ValueError(f"无法解析 CSV 文件 {p.name}（编码/分隔符）: {last}")


def _inline_to_df(value):
    if not isinstance(value, list) or not value:
        raise ValueError("内联数据 value 必须是非空二维数组")
    if all(isinstance(r, dict) for r in value):
        return pd.DataFrame(value)
    if all(isinstance(r, (list, tuple)) for r in value):
        head = value[0]
        if all(isinstance(c, str) for c in head):
            return pd.DataFrame(value[1:], columns=[str(c) for c in head])
        ncols = len(head)
        return pd.DataFrame(value, columns=[f"列{i + 1}" for i in range(ncols)])
    if all(not isinstance(r, (list, tuple, dict)) for r in value):
        return pd.DataFrame({0: value})
    raise ValueError("内联数据 value 结构无法识别")


def _looks_numeric_frame(df: pd.DataFrame) -> bool:
    if df.shape[1] < 2:
        return False
    for col in df.columns:
        for v in df[col].dropna().head(60):
            if not isinstance(v, (int, float, np.number, np.bool_)):
                return False
    return True


def load_source(entry: dict, base: Path) -> dict:
    """返回 {df, desc, is_matrix}。"""
    if "path" in entry:
        fmt = (entry.get("format") or "csv").lower()
        p = Path(str(entry["path"]))
        if not p.is_absolute():
            p = base / p
        if not p.exists():
            raise ValueError(f"数据文件不存在: {entry['path']}")
        if fmt in ("csv", "tsv", "txt"):
            return {"df": _read_csv_multi(p), "desc": str(p), "is_matrix": False}
        if fmt in ("xlsx", "xls", "excel"):
            try:
                return {"df": pd.read_excel(p), "desc": str(p), "is_matrix": False}
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"读取 Excel 失败（需 openpyxl）: {e}") from e
        if fmt == "json":
            obj = json.loads(p.read_text(encoding="utf-8-sig"))
            if isinstance(obj, list) and obj and all(isinstance(r, dict) for r in obj):
                return {"df": pd.DataFrame(obj), "desc": str(p), "is_matrix": False}
            if isinstance(obj, dict) and "columns" in obj and "data" in obj:
                return {"df": pd.DataFrame(obj["data"], columns=obj["columns"]),
                        "desc": str(p), "is_matrix": False}
            if isinstance(obj, list) and obj and \
                    all(isinstance(r, (list, tuple)) for r in obj):
                head = obj[0]
                if all(isinstance(c, str) for c in head):
                    return {"df": pd.DataFrame(obj[1:], columns=[str(c) for c in head]),
                            "desc": str(p), "is_matrix": False}
                return {"df": pd.DataFrame(np.asarray(obj, dtype=float)),
                        "desc": str(p), "is_matrix": True}
            raise ValueError(f"JSON 结构无法识别为表格: {entry['path']}")
        if fmt == "npy":
            arr = np.load(p)
            if arr.ndim == 1:
                return {"df": pd.DataFrame({0: arr}), "desc": str(p), "is_matrix": False}
            if arr.ndim == 2:
                return {"df": pd.DataFrame(arr), "desc": str(p), "is_matrix": True}
            raise ValueError("npy 仅支持 1D/2D 数组")
        raise ValueError(f"未知 format '{fmt}'（csv|xlsx|json|npy）")
    if "value" in entry:
        df = _inline_to_df(entry["value"])
        return {"df": df, "desc": f"内联数据 {entry.get('name', '')}".strip(),
                "is_matrix": _looks_numeric_frame(df)}
    raise ValueError("data[] 项必须含 path 或 name+value")


def _to_numeric_series(s, label, ctx):
    try:
        return pd.to_numeric(s, errors="raise")
    except (TypeError, ValueError):
        bad = [str(v) for v in s.dropna().unique()[:3]]
        raise ValueError(f"{ctx}: 列 '{label}' 含非数值内容（如 {bad}），无法绘图") from None


# ---------------------------------------------------------------- 轴解析
def resolve_axis(df: pd.DataFrame, spec_val, n: int, kind: str, ctx: str,
                 language: str) -> dict:
    idx_label = "序号" if language != "en" else "row index"
    if spec_val is None:
        raise ValueError(f"{ctx}: {kind} 必填")
    if isinstance(spec_val, str) and spec_val == "index":
        return {"values": np.arange(n, dtype=float), "name": "__dsh_idx__",
                "label": idx_label, "is_num": True}
    if isinstance(spec_val, (int, float)) and not isinstance(spec_val, bool):
        i = int(spec_val)
        if not (0 <= i < len(df.columns)):
            raise ValueError(f"{ctx}: {kind} 列索引 {i} 超出范围（共 {len(df.columns)} 列）")
        col = df.columns[i]
        if kind == "y":
            num = _to_numeric_series(df[col], col, ctx)
            return {"values": num.to_numpy(dtype=float), "name": f"__dsh_coly__",
                    "label": str(col), "is_num": True}
        if kind == "hue":
            return {"values": df[col], "name": f"__dsh_colh__",
                    "label": str(col), "is_num": False}
        return {"values": df[col], "name": f"__dsh_colx__",
                "label": str(col), "is_num": False}
    if isinstance(spec_val, str) and spec_val in df.columns:
        s = df[spec_val]
        label = spec_val
        if kind == "y":
            num = _to_numeric_series(s, label, ctx)
            return {"values": num.to_numpy(dtype=float), "name": label, "label": label,
                    "is_num": True}
        if kind == "hue":
            return {"values": s, "name": label, "label": label, "is_num": False}
        try:
            num = pd.to_numeric(s, errors="raise")
            return {"values": num.to_numpy(dtype=float), "name": label, "label": label,
                    "is_num": True}
        except (TypeError, ValueError):
            return {"values": s, "name": label, "label": label, "is_num": False}
    if isinstance(spec_val, str):
        raise ValueError(
            f"{ctx}.{kind}: 列 '{spec_val}' 不存在于 data_ref；可用列: {list(df.columns)}")
    if isinstance(spec_val, (list, tuple)):
        if len(spec_val) != n:
            raise ValueError(f"{ctx}: 内联 {kind} 长度 {len(spec_val)} ≠ 数据行数 {n}")
        if kind == "y":
            try:
                vals = np.asarray([float(x) for x in spec_val])
            except (TypeError, ValueError):
                raise ValueError(f"{ctx}: 内联 y 含非数值内容") from None
            return {"values": vals, "name": "__dsh_iny__", "label": "", "is_num": True}
        if kind == "hue":
            return {"values": np.asarray(spec_val, dtype=object), "name": "__dsh_inh__",
                    "label": "", "is_num": False}
        try:
            return {"values": np.asarray([float(x) for x in spec_val]),
                    "name": "__dsh_inx__", "label": "", "is_num": True}
        except (TypeError, ValueError):
            return {"values": np.asarray(spec_val, dtype=object),
                    "name": "__dsh_inx__", "label": "", "is_num": False}
    raise ValueError(f"{ctx}: {kind} 需为列名/索引/内联数组")


# ---------------------------------------------------------------- 热力图解析
def resolve_heatmap(df: pd.DataFrame, spec: dict, ctx: str, language: str) -> dict:
    if spec.get("matrix") is not None:
        m = spec["matrix"]
        if not (isinstance(m, list) and m and all(isinstance(r, list) for r in m)):
            raise ValueError(f"{ctx}: matrix 必须是二维数组")
        rl = spec.get("row_labels")
        cl = spec.get("col_labels") or [str(i + 1) for i in range(len(m[0]))]
        if isinstance(cl, list) and len(cl) != len(m[0]):
            cl = [str(i + 1) for i in range(len(m[0]))]
        return {"matrix": [[_fmt_gb(v) for v in row] for row in m],
                "row_labels": rl, "col_labels": cl, "corr_mode": False}
    y = spec.get("y")
    if isinstance(y, list) and y and all(isinstance(r, list) for r in y):
        return {"matrix": [[_fmt_gb(v) for v in row] for row in y],
                "row_labels": None, "col_labels": None, "corr_mode": False}
    if spec.get("_src_is_matrix"):
        return {"matrix": df.values.tolist(), "row_labels": None,
                "col_labels": [str(c) for c in df.columns], "corr_mode": False}
    x = spec.get("x")
    if isinstance(x, str) and x in df.columns:
        rl = [str(v) for v in df[x]]
        num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and c != x]
        if not num_cols:
            raise ValueError(f"{ctx}: 除行标签列 '{x}' 外没有数值列，无法画热力图")
        return {"matrix": [[_fmt_gb(v) for v in row] for row in df[num_cols].values.tolist()],
                "row_labels": rl, "col_labels": [str(c) for c in num_cols],
                "corr_mode": False}
    num_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if len(num_cols) >= 2:
        return {"corr_mode": True, "frame_cols": num_cols[:30]}
    raise ValueError(
        f"{ctx}: 无法确定热力图数据——请提供二维 matrix/json 矩阵，或 ≥2 个数值列")


# ---------------------------------------------------------------- 规格解析
def parse_plot(plot: dict, idx: int, language: str) -> dict:
    """仅做规格级校验；列解析在绑定数据源后(_resolve_items)进行。"""
    ctx = f"plots[{idx}]"
    out_name = plot.get("output_name")
    if not out_name or not isinstance(out_name, str) or not OUTPUT_NAME_RE.match(out_name):
        raise ValueError(f"{ctx}.output_name: 必须为 ASCII 文件名（不含扩展名），实际 '{out_name}'")
    ct = plot.get("chart_type")
    if ct not in CHART_TYPES:
        raise ValueError(f"{ctx}.chart_type: '{ct}' 非法；可用: {'|'.join(sorted(CHART_TYPES))}")
    color = plot.get("color") or "primary"
    if color not in COLOR_KEYS:
        raise ValueError(f"{ctx}.color: 未知 '{color}'；可用: {'|'.join(sorted(COLOR_KEYS))}")
    figsize = plot.get("figsize") or "single"
    if figsize not in FIG_SIZES:
        raise ValueError(f"{ctx}.figsize: 未知 '{figsize}'；可用: {'|'.join(FIG_SIZES)}")
    return {
        "out_name": out_name, "chart_type": ct, "color": color,
        "figsize_key": figsize, "notes": plot.get("notes"),
        "data_ref": plot.get("data_ref"), "ctx": ctx,
        "_x_raw": plot.get("x"), "_y_raw": plot.get("y"),
        "_hue_raw": plot.get("hue"),
        "_ci": bool(plot.get("ci", False)),
        "_annotations": plot.get("annotations") or [],
        "_matrix": plot.get("matrix"),
        "_row_labels": plot.get("row_labels"),
        "_col_labels": plot.get("col_labels"),
        "_subs": [dict(s) for s in (plot.get("subplots") or [])],
    }


# ---------------------------------------------------------------- 列解析与 frame 组装
def resolve_items(p: dict, src: dict, language: str) -> tuple[pd.DataFrame, list[dict]]:
    """绑定数据源后：解析每项 x/y/hue → (frame, clean_items)。"""
    df_all = src["df"]
    n = len(df_all)
    if n == 0:
        raise ValueError(f"{p['ctx']}: data_ref 数据为空（0 行）")
    main = {"x": p["_x_raw"], "y": p["_y_raw"], "hue": p["_hue_raw"],
            "ci": p["_ci"], "matrix": p["_matrix"],
            "_src_is_matrix": src.get("is_matrix", False)}
    subs = p["_subs"]
    items_raw = []
    for k, base in enumerate([main] + subs):
        ictx = f"{p['ctx']}.subplots[{k - 1}]" if k else p["ctx"]
        if p["chart_type"] == "heatmap":
            hm = resolve_heatmap(df_all, base, ictx, language)
            it = {"chart_type": "heatmap", "color": p["color"],
                  "corr_mode": hm.get("corr_mode", False),
                  "annotations": [], "xlabel": "", "ylabel": ""}
            if hm.get("corr_mode"):
                it["frame_cols"] = hm["frame_cols"]
                it["matrix"] = None
            else:
                it["matrix"] = hm["matrix"]
                it["row_labels"] = hm.get("row_labels")
                it["col_labels"] = hm.get("col_labels")
            items_raw.append(it)
            continue
        # box/violin/hist/kde 可无 x（只画 y 分布）；其余类型 x 必填
        x_optional = p["chart_type"] in ("box", "violin", "hist", "kde")
        if base.get("x") is None:
            if not x_optional:
                raise ValueError(f"{ictx}: x 必填")
            xa = {"values": None, "name": None, "label": "", "is_num": False}
        else:
            xa = resolve_axis(df_all, base.get("x"), n, "x", ictx, language)
        if base.get("y") is None:
            raise ValueError(f"{ictx}: y 必填")
        ya = resolve_axis(df_all, base.get("y"), n, "y", ictx, language)
        ha = None
        if base.get("hue") is not None:
            ha = resolve_axis(df_all, base.get("hue"), n, "hue", ictx, language)
        hue_order = None
        if ha is not None:
            hue_order = list(dict.fromkeys(str(v) for v in ha["values"] if _notna(v)))
        x_order = (list(dict.fromkeys(str(v) for v in xa["values"] if _notna(v)))
                   if xa and xa["name"] and not xa["is_num"] else None)
        items_raw.append({
            "chart_type": p["chart_type"], "color": p["color"],
            "x": None if xa is None else xa["name"],
            "y": None if ya is None else ya["name"],
            "hue": None if ha is None else ha["name"],
            "x_is_num": bool(xa["is_num"]) if xa else False,
            "hue_order": hue_order, "x_order": x_order,
            "ci": bool(base.get("ci", False)),
            "annotations": p["_annotations"],
            "xlabel": xa["label"] if xa else "", "ylabel": ya["label"] if ya else "",
            "_values": ([] if xa is None or xa["name"] is None else [(xa["name"], xa["values"])])
                       + ([((ya["name"], ya["values"]))])
                       + ([(ha["name"], ha["values"])] if ha else []),
        })
    # frame: 各列同长（都源自同一 df 或同长内联）
    col_data: dict[str, list] = {}
    clean: list[dict] = []
    for it in items_raw:
        if it["chart_type"] == "heatmap":
            if it.get("corr_mode"):
                for c in it.get("frame_cols", []):
                    col_data.setdefault(c, [])           # 占位，实际值在下方填充
            clean.append({k: v for k, v in it.items() if not k.startswith("_")
                          and k != "frame_cols"})
            continue
        for name, values in it.pop("_values"):
            if name is None:
                continue
            col_data.setdefault(name, list(values))
        clean.append(it)
    # 填充 heatmap corr_mode 需要的数值列
    for it in items_raw:
        if it["chart_type"] == "heatmap" and it.get("corr_mode"):
            for c in it["frame_cols"]:
                col_data[c] = [ _fmt_gb(v) for v in df_all[c].tolist() ]
    frame = pd.DataFrame(col_data) if col_data else pd.DataFrame()
    return frame, clean


# ---------------------------------------------------------------- 主流程
def handle_data_chart(req: dict, py: dict | None = None) -> dict:
    errors: list[dict] = []
    language = req.get("language") or "zh"
    if language not in ("zh", "en"):
        errors.append({"field": "language", "reason": f"language 仅支持 zh/en，实际 '{language}'"})
        language = "zh"
    figure_dir = str(req.get("figure_dir") or "figures")
    fig_dir = Path(figure_dir)
    if not fig_dir.is_absolute():
        # 相对 figure_dir 一律按 PLOT_WORKSPACE 解析（与「figure_dir 必须在工作区内」的约定一致，
        # 也避免 CLI 从别处启动时产物散落到进程 cwd）
        fig_dir = env.WORKSPACE / fig_dir
    try:
        fig_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        errors.append({"field": "figure_dir", "reason": f"无法创建输出目录: {e}"})

    data = req.get("data") or []
    plots = req.get("plots") or []
    if not data:
        errors.append({"field": "data", "reason": "data 必填（数据来源数组，当前为空）"})
    if not plots:
        errors.append({"field": "plots", "reason": "plots 必填（图表规格数组，当前为空）"})
    if errors:
        return _assemble(False, [], "", errors, req, fig_dir)

    sources: dict[str, dict] = {}
    seen: set[str] = set()
    for i, ent in enumerate(data):
        try:
            loaded = load_source(ent, env.WORKSPACE)
        except ValueError as e:
            errors.append({"field": f"data[{i}]", "reason": str(e)})
            continue
        key = (str(ent.get("path")) if "path" in ent
               else str(ent.get("name", f"__inline{i}__")))
        if key in seen:
            errors.append({"field": f"data[{i}]", "reason": f"data_ref 键重复: {key}"})
        seen.add(key)
        sources[key] = loaded

    parsed: list[dict] = []
    used_names: list[str] = []
    for i, plot in enumerate(plots):
        try:
            p = parse_plot(plot, i, language)
            ref = plot.get("data_ref")
            auto = False
            if ref is None:
                if len(sources) == 1:
                    ref = next(iter(sources))
                    auto = True
                else:
                    raise ValueError(
                        f"plots[{i}].data_ref: 缺失，必须指向 data[] 中某个名字（可用: {list(sources)}）；"
                        "省略 data_ref 仅在 data[] 只有一个数据源时自动回填")
            elif ref not in sources:
                raise ValueError(
                    f"plots[{i}].data_ref: '{ref}' 不存在于 data[]；可用: {list(sources)}")
            if p["out_name"] in used_names:
                raise ValueError(
                    f"output_name '{p['out_name']}' 与 requests 中 plots[{used_names.index(p['out_name'])}] 冲突，请改名")
            used_names.append(p["out_name"])
            parsed.append({"p": p, "ref": ref, "auto": auto})
        except ValueError as e:
            errors.append({"field": f"plots[{i}]", "reason": str(e)})

    if errors:
        return _assemble(False, [], "", errors, req, fig_dir)

    generated: list[dict] = []
    feature_lines: list[str] = []

    for pi, entry in enumerate(parsed, 1):
        p, ref, auto = entry["p"], entry["ref"], entry["auto"]
        try:
            frame, items = resolve_items(p, sources[ref], language)
        except ValueError as e:
            errors.append({"field": p["ctx"], "reason": str(e)})
            continue
        gen_dir = fig_dir / "_gen" / p["out_name"]
        gen_dir.mkdir(parents=True, exist_ok=True)
        data_json = gen_dir / "data.json"
        feat_json = gen_dir / "features.json"
        script = gen_dir / "render.py"
        png_out = fig_dir / f"{p['out_name']}.png"
        pdf_out = fig_dir / f"{p['out_name']}.pdf"

        ncols = min(len(items), 4)
        nrows = (len(items) + ncols - 1) // ncols
        base_fig = FIG_SIZES[p["figsize_key"]]
        env.dump_json(str(data_json), {"frame": frame.to_dict(orient="records")})
        try:
            code = plotgen.build_script(
                font_path=str(env.FONT_FILE), data_path=str(data_json),
                feat_path=str(feat_json), png_path=str(png_out), pdf_path=str(pdf_out),
                items=items, base_figsize=base_fig, nrows=nrows, ncols=ncols)
        except Exception as e:  # noqa: BLE001
            errors.append({"field": p["ctx"], "reason": f"生成绘图代码失败: {e}"})
            continue
        script.write_text(code, encoding="utf-8")
        script_txt = str(script) if not script.is_absolute() else str(script.relative_to(env.WORKSPACE))
        res = env.run_py_script(py["exe"], script, timeout=300, cwd=env.WORKSPACE)
        if not res["ok"]:
            errs_file = gen_dir / "features.errors.json"
            tail = "\n".join((res.get("stdout") or "").splitlines()[-6:])
            if res.get("rc") == 3 and errs_file.exists():
                item_errs = json.loads(errs_file.read_text(encoding="utf-8"))
                for ie in item_errs:
                    errors.append({"field": f"{p['ctx']}.items[{ie.get('index')}]",
                                   "reason": f"{ie.get('type')}: {ie.get('message')}"})
            else:
                errors.append({"field": p["ctx"],
                               "reason": f"渲染子进程失败(rc={res.get('rc')}): {tail}"})
            continue

        feats: list[dict] = []
        if feat_json.exists():
            try:
                feats = json.loads(feat_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                errors.append({"field": p["ctx"], "reason": "特征文件损坏"})
                feats = []
        if not png_out.exists():
            errors.append({"field": p["ctx"], "reason": "PNG 未生成（渲染可能失败）"})
            continue

        files = []
        if png_out.exists():
            files.append({"path": f"{fig_dir / p['out_name']}.png".replace("\\", "/"),
                          "kind": "data_chart", "data_ref": ref})
        if pdf_out.exists():
            files.append({"path": f"{fig_dir / p['out_name']}.pdf".replace("\\", "/"),
                          "kind": "data_chart", "data_ref": ref})
        if auto and files:
            files[0]["data_ref_note"] = "已自动回填（data[] 仅一个数据源）"
        caption = p["notes"] or (
            f"{_CT_ZH.get(p['chart_type'], p['chart_type'])}："
            f"{(items[0].get('xlabel') or '')}{(items[0].get('ylabel') or '')}")
        if files:
            files[0]["suggested_caption"] = caption
            files[0]["script"] = script_txt
        generated.extend(files)

        for k, f in enumerate(feats):
            tag = f"图{pi}" if len(feats) == 1 else f"图{pi}({chr(97 + k)})"
            try:
                txt = features.format_any(p["chart_type"], f, language)
            except Exception:  # noqa: BLE001
                txt = ""
            if txt:
                feature_lines.append(f"【{tag}数据特征】{txt}")

    ok = not errors
    return _assemble(ok, generated, "\n".join(feature_lines), errors, req, fig_dir)


# ---------------------------------------------------------------- 组装
_env_cache: dict = {}


def _env_snapshot() -> dict:
    now = time.time()
    if _env_cache.get("ts") and now - _env_cache["ts"] < 60:
        return _env_cache["data"]
    snap = env.snapshot()
    _env_cache.update({"ts": now, "data": snap})
    return snap


def _assemble(ok: bool, generated: list, data_features: str, errors: list,
              req: dict, fig_dir: Path | None = None) -> dict:
    out = {
        "ok": ok,
        "generated_files": generated,
        "drawio_sources": [],
        "data_features": data_features,
        "errors": errors,
        "environment": _env_snapshot(),
    }
    if fig_dir is not None:
        out["figure_dir"] = str(fig_dir)
    return out