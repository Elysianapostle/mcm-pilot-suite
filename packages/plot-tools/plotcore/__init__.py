# -*- coding: utf-8 -*-
"""独立论文绘图插件核心包：
  - handle_request(): 请求分发（数据图 / 流程图），统一 §5 输出契约与结构化错误。
  - env: 环境探测与子进程运行
  - data_chart / diagram_gen: 两流程执行体
  - features / plotgen: 数据特征 + 绘图代码生成
"""
from __future__ import annotations

import traceback

from . import data_chart, diagram_gen, env

__all__ = ["handle_request", "env", "data_chart", "diagram_gen"]

_py_cache: dict = {}


def resolve_python() -> dict:
    if not _py_cache:
        _py_cache.update(env.find_python())
    return _py_cache


def handle_request(req) -> dict:
    """请求分发。失败一律转结构化错误（ok:false + errors），不抛异常。"""
    if not isinstance(req, dict):
        return _fail("request", "请求必须是 JSON 对象")

    has_plots = "plots" in req or "data" in req
    has_diag = any(k in req for k in ("template", "content", "description"))
    if has_plots and has_diag:
        return _fail("request", "请求同时包含 data/plots 与 template/content/description，无法判定流程；"
                                "请只保留其中一个流程的字段")
    try:
        py = resolve_python()
        if not py.get("exe"):
            return {"ok": False, "generated_files": [], "drawio_sources": [],
                    "data_features": "", "errors": [
                        {"field": "environment",
                         "reason": "未找到可用的 Python 解释器（已探测 PLOT_PYTHON、Anaconda mathmodel/基础、PATH python3/python）"}],
                    "environment": env.snapshot()}
        if has_plots:
            return data_chart.handle_data_chart(req, py)
        if has_diag:
            return diagram_gen.handle_generate_diagram(req, py)
        return _fail("request", "无法识别请求类型：数据图请给 data+plots，流程图请给 "
                                "template/content/description")
    except Exception as e:  # noqa: BLE001
        tb = traceback.format_exc(limit=8)
        return _fail("runtime", f"{type(e).__name__}: {e}", detail=tb[-1500:])


def _fail(field: str, reason: str, detail: str = "") -> dict:
    out = {"ok": False, "generated_files": [], "drawio_sources": [],
           "data_features": "", "errors": [{"field": field, "reason": reason}],
           "environment": env.snapshot()}
    if detail:
        out["diagnostics"] = detail
    return out