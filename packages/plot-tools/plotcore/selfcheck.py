# -*- coding: utf-8 -*-
"""环境自检：解释器/依赖/字体/drawio/渲染脚本 一次性体检（启动时与 --self-check 用）。"""
from __future__ import annotations

from . import env


def report() -> dict:
    return env.snapshot()


def render_text(snap: dict) -> str:
    lines = ["===== 论文绘图插件 · 环境自检 ====="]
    py = snap.get("python") or {}
    if py.get("exe"):
        lines.append(f"[✓] Python: {py['exe']}  ({py.get('version')})")
    else:
        lines.append(f"[✗] Python: 未找到可用解释器（候选: {snap.get('python_candidates')}）")
    for dep in snap.get("dependencies", []):
        mark = "✓" if dep.get("ok") else "✗"
        ver = f" {dep.get('version')}" if dep.get("version") else ""
        note = f"  {dep.get('note')}" if dep.get("note") else ""
        lines.append(f"[{mark}] {dep['name']}{ver}{note}")
    font = snap.get("font") or {}
    lines.append(f"[{'✓' if font.get('ok') else '✗'}] 中文字体: {font.get('path')} "
                 f"(size={font.get('size')})")
    d = snap.get("drawio") or {}
    if d.get("ok"):
        lines.append(f"[✓] drawio CLI: {d.get('exe')} ({d.get('version')})")
    else:
        lines.append(f"[✗] drawio CLI: 未安装 —— 流程图保留 .drawio 并提示手动导出，不阻塞")
    scr = snap.get("render_scripts") or {}
    if scr.get("ok"):
        lines.append("[✓] 渲染脚本: roadmap_5band / stageflow_3col / taskflow_land "
                     "/ framework_3col + check_layout + export_figure 全部就位")
    else:
        lines.append(f"[✗] 渲染脚本缺失: {scr.get('missing')}")
    lines.append("提示: 子进程统一以 cmd 文件重定向方式运行（规避 windows 管道 stdio 0xc0000142），"
                 "并注入 PYTHONUTF8=1 / MPLCONFIGDIR 于工作区内。")
    return "\n".join(lines)