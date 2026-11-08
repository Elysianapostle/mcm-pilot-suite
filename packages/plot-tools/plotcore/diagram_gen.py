# -*- coding: utf-8 -*-
"""流程图流程：模板判定 → content JSON → 渲染脚本（超字数/超框错误原样透传）→ 版式自检 → drawio 导出（降级）。"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from . import env

TEMPLATE_SCRIPTS = env.RENDER_SCRIPTS
TEMPLATES = set(TEMPLATE_SCRIPTS)

# 每个模板的字段规范文档（报错时附引用路径，降低调用方试错成本）
TEMPLATE_REFDOCS = {t: f"diagram/references/{t}.md" for t in sorted(TEMPLATES)}


def _template_help() -> str:
    return "；".join(f"{t}（详见 {TEMPLATE_REFDOCS[t]}）" for t in sorted(TEMPLATES))


def _attach_suggestions(errors: list, template: str, code: str) -> list:
    """每条错误附带调试建议（P2-7）。"""
    if code == "OVERFLOW":
        s = (f"文案按 {TEMPLATE_REFDOCS.get(template, 'reference')} 的字数预算精简；"
             f"超长文本可用 \\n 手动断行")
    elif code == "SCHEMA":
        s = f"按 {TEMPLATE_REFDOCS.get(template, 'reference')} 的字段表补齐缺失字段、修正数量/格式后重试"
    else:
        return errors
    for e in errors:
        e.setdefault("suggestion", s)
    return errors

# description → template 关键词（§2.2.1）
_DESC_KEYWORDS = {
    "roadmap-5band": ["全文", "路线", "技术路线", "研究路线", "整体", "全流程", "破题", "跨阶段"],
    "stageflow-3col": ["执行流程", "阶段推进", "决策", "流程", "执行", "推进"],
    "taskflow-land": ["任务", "流水线", "依赖", "递进", "分解为任务"],
    "framework-3col": ["框架", "全景", "三栏", "视角", "结构", "栏目"],
}


def infer_template_from_content(content: dict) -> str | None:
    if not isinstance(content, dict):
        return None
    if "rails" in content or "band1" in content or "band5" in content:
        return "roadmap-5band"
    if "methods" in content and "stages" in content:
        return "framework-3col"
    if "headers" in content and "stages" in content and "rights" in content:
        return "stageflow-3col"
    if "headers" in content and "blocks" in content and "stages" not in content:
        return "stageflow-3col"
    if "blocks" in content and "headers" not in content:
        return "taskflow-land"
    return None


def infer_template_from_description(desc: str) -> str:
    scores = {}
    for t, kws in _DESC_KEYWORDS.items():
        scores[t] = sum(desc.count(k) for k in kws)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "roadmap-5band"


# ---------------------------------------------------------------- 结构摘要
def structure_summary(content: dict, template: str) -> str:
    def cnt(keys):
        return sum(1 for k in keys if k in content)

    try:
        if template == "roadmap-5band":
            p = []
            rails = content.get("rails", [])
            b1 = content.get("band1", {})
            b2 = content.get("band2", {})
            b3 = content.get("band3", {})
            b4 = content.get("band4", {})
            b5 = content.get("band5", {})
            p.append(f"roadmap-5band 五带路线图（{len(rails)} 旗标）")
            p.append(f"①破题 {len(b1.get('items', []))} 子问题")
            p.append(f"②准备 {len(b2.get('sources', []))} 数据源 / {len(b2.get('metrics', []))} 指标")
            p.append(f"③方法 {len(b3.get('left', []))}+{len(b3.get('right', []))} 要素")
            p.append(f"④结果 {len(b4.get('left_items', []))} vs {len(b4.get('right_items', []))} 项对比")
            p.append(f"⑤评价 {len(b5.get('cases', []))} 推广场景")
            return "；".join(p)
        if template == "stageflow-3col":
            blocks = content.get("blocks", [])
            return (f"stageflow-3col 分阶段流程（{len(content.get('stages', []))} 方法，"
                    f"{len(content.get('rights', []))} 阶段说明，{len(blocks)} 内容块，"
                    f"{sum(len(b.get('sections', [])) for b in blocks)} 段）")
        if template == "taskflow-land":
            blocks = content.get("blocks", [])
            return (f"taskflow-land 任务流水线（{len(blocks)} 任务块，"
                    f"{sum(len(b.get('sections', [])) for b in blocks)} 段）")
        if template == "framework-3col":
            blocks = content.get("blocks", [])
            return (f"framework-3col 研究框架（{len(content.get('stages', []))} 阶段，"
                    f"{len(content.get('methods', []))} 方法组，{len(blocks)} 内容块，"
                    f"{sum(len(b.get('sections', [])) for b in blocks)} 段）")
    except Exception:  # noqa: BLE001
        pass
    return f"{template} 结构图"


# ---------------------------------------------------------------- 渲染与导出
_CAP_RE = re.compile(r"^([A-Za-z0-9_\-\.]+)(?:[:(].*)?$")
_PROB_FIELD_RE = re.compile(r"^[A-Za-z0-9_\-\. ]{1,40}[：:]")


def _parse_problem_lines(lines: list[str]) -> list[dict]:
    """仅把真正的逐槽问题行解析为 errors[]（bullet 项或 ASCII 字段前缀+冒号）；
    汇总行 / 建议行不属于字段错误，留在 render_stdout 原样透传。"""
    out = []
    for ln in lines:
        tok = ln.strip()
        bullet = False
        if tok.startswith("- "):
            tok = tok[2:]
            bullet = True
        if not tok:
            continue
        if not (bullet or _PROB_FIELD_RE.match(tok)):
            continue
        field = tok.split(":", 1)[0].split("：", 1)[0].split(" 需 ", 1)[0].strip()
        if len(field) <= 40 and field:
            out.append({"field": field, "reason": ln.strip()})
    return out


def render_diagram(py: dict, template: str, content: dict, output_name: str,
                   fig_dir: Path) -> dict:
    script = TEMPLATE_SCRIPTS.get(template)
    if script is None or not script.exists():
        return {"ok": False,
                "errors": [{"field": "template",
                            "reason": f"模板 '{template}' 无对应渲染脚本；可用: {_template_help()}",
                            "suggestion": "从上述模板中选择一个（字段规范见对应 references 文档）"}]}

    gen_dir = fig_dir / "_gen" / output_name
    gen_dir.mkdir(parents=True, exist_ok=True)
    content_json = gen_dir / "content.json"
    content_json.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    out_drawio = fig_dir / f"{output_name}.drawio"

    res = env.run_py(py["exe"], [str(script), str(content_json), "-o", str(out_drawio)],
                     timeout=300, cwd=env.WORKSPACE)
    stdout = res.get("stdout") or ""
    rc = res.get("rc")
    if rc == 0:
        return {"ok": True, "drawio": out_drawio, "stdout": stdout, "errors": [],
                "content_json": content_json}
    if rc == 2:  # 容量/超框
        lines = [l for l in stdout.splitlines() if l.strip()]
        problems = _parse_problem_lines(lines)
        return {"ok": False, "drawio": None, "stdout": stdout, "code": "OVERFLOW",
                "errors": _attach_suggestions(
                    problems or [{"field": "content", "reason": "\n".join(lines)}],
                    template, "OVERFLOW")}
    if rc == 1:  # schema / 数量/字段
        lines = [l for l in stdout.splitlines() if l.strip()]
        problems = _parse_problem_lines(lines)
        return {"ok": False, "drawio": None, "stdout": stdout, "code": "SCHEMA",
                "errors": _attach_suggestions(
                    problems or [{"field": "content", "reason": "\n".join(lines)}],
                    template, "SCHEMA")}
    return {"ok": False, "drawio": None, "stdout": stdout, "code": "RENDER_RC",
            "errors": [{"field": "template",
                        "reason": f"渲染脚本异常退出(rc={rc}):\n{stdout[-600:]}"}]}


def lint_diagram(py: dict, template: str, content: dict, fig_dir: Path) -> dict:
    """lint_only：只做字段 + 容量校验，不渲染、不导出（复用模板脚本 --check 通道）。
    rc=0 全过；rc=1 字段类问题（聚合）；rc=2 容量类问题（聚合）。"""
    script = TEMPLATE_SCRIPTS.get(template)
    if script is None or not script.exists():
        return {"ok": False, "errors": [
            {"field": "template",
             "reason": f"模板 '{template}' 无对应渲染脚本；可用: {_template_help()}",
             "suggestion": "从上述模板中选择一个（字段规范见对应 references 文档）"}]}
    gen_dir = fig_dir / "_gen"
    gen_dir.mkdir(parents=True, exist_ok=True)
    content_json = gen_dir / f"_lint_{int(time.time() * 1000)}.json"
    content_json.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        res = env.run_py(py["exe"], [str(script), str(content_json), "--check"],
                         timeout=300, cwd=env.WORKSPACE)
    finally:
        try:
            content_json.unlink(missing_ok=True)
        except OSError:
            pass
    stdout = res.get("stdout") or ""
    rc = res.get("rc")
    if rc == 0:
        return {"ok": True, "code": None, "errors": [], "stdout": stdout}
    if rc in (1, 2):
        code = "SCHEMA" if rc == 1 else "OVERFLOW"
        lines = [l for l in stdout.splitlines() if l.strip()]
        problems = _parse_problem_lines(lines)
        return {"ok": False, "code": code,
                "errors": _attach_suggestions(
                    problems or [{"field": "content", "reason": "\n".join(lines)}],
                    template, code),
                "stdout": stdout}
    return {"ok": False, "code": "RENDER_RC",
            "errors": [{"field": "template",
                        "reason": f"校验脚本异常退出(rc={rc}):\n{stdout[-600:]}"}]}


def layout_check(drawio: Path, py: dict) -> dict:
    res = env.run_py(py["exe"], [str(env.CHECK_SCRIPT), str(drawio)], timeout=120,
                     cwd=env.WORKSPACE)
    lines = [l for l in (res.get("stdout") or "").splitlines() if l.strip()]
    fails = [l for l in lines if l.startswith("  FAIL")]
    warns = [l for l in lines if l.startswith("  WARN")]
    return {"ok": res.get("rc") == 0, "rc": res.get("rc"),
            "lines": lines[:60], "fails": fails, "warns": warns}


def _export_direct(exe: str, drawio: Path) -> dict:
    """Windows 桌面版产物名为 draw.io.exe、与资产脚本期望的命令名 `drawio` 不匹配时，
    用解析出的 exe 路径按 export_figure.py 相同参数直连导出（不改动冻结资产）。"""
    png = drawio.with_suffix(".png")
    pdf = drawio.with_suffix(".pdf")
    try:
        src_txt = drawio.read_text(encoding="utf-8")
    except OSError:
        src_txt = ""
    m = re.search(r'pageWidth="([\d.]+)"', src_txt)
    width = ["--width", str(int(float(m.group(1))))] if m else []
    cmds = [
        [exe, "-x", "-f", "png", "-s", "1", "-b", "0", *width, "-o", str(png), str(drawio)],
        [exe, "-x", "-f", "pdf", "--crop", "-o", str(pdf), str(drawio)],
    ]
    lines: list[str] = []
    for cmd in cmds:
        r = env.run_command(cmd, timeout=600, cwd=env.WORKSPACE, env_extra={})
        lines += [l for l in (r or {}).get("stdout", "").splitlines() if l.strip()]
        lines += [l for l in (r or {}).get("stderr", "").splitlines() if l.strip()]
    done = png.exists() or pdf.exists()
    return {"ok": done, "skipped": False, "png": png.exists(), "pdf": pdf.exists(),
            "lines": lines[:30], "error_tail": "" if done else "\n".join(lines[-8:])}


def export_drawio(py: dict, drawio: Path) -> dict:
    probe = env.drawio_probe()
    if not probe["ok"]:
        return {"ok": False, "skipped": True,
                "reason": "drawio CLI 缺失；已保留 .drawio 源文件。手动导出建议："
                          f"drawio --export --format png {drawio.name}（或 diagrams.net 网页版导出）"}
    exe = probe["exe"]
    exe_dir = str(Path(exe).parent)
    aug = {"PATH": exe_dir + os.pathsep + (os.environ.get("PATH") or "")} if exe_dir else {}
    res = env.run_py(py["exe"], [str(env.EXPORT_SCRIPT), str(drawio)], timeout=600,
                     cwd=env.WORKSPACE, env_extra=aug)
    lines = [l for l in (res.get("stdout") or "").splitlines() if l.strip()]
    png = drawio.with_suffix(".png")
    pdf = drawio.with_suffix(".pdf")
    if res.get("rc") == 0 and (png.exists() or pdf.exists()):
        return {"ok": True, "skipped": False, "png": png.exists(), "pdf": pdf.exists(),
                "lines": lines[:30], "error_tail": ""}
    # 资产脚本期望命令名 `drawio`；Windows 桌面版产物名为 draw.io.exe 时 which 必失配 → 直连兜底
    return _export_direct(exe, drawio)


# ---------------------------------------------------------------- 主流程
def handle_generate_diagram(req: dict, py: dict | None = None) -> dict:
    errors: list[dict] = []
    language = req.get("language") or "zh"
    if language not in ("zh", "en"):
        errors.append({"field": "language", "reason": f"language 仅支持 zh/en，实际 '{language}'"})
        language = "zh"
    figure_dir = str(req.get("figure_dir") or "figures")
    fig_dir = Path(figure_dir)
    if not fig_dir.is_absolute():
        # 相对 figure_dir 按 PLOT_WORKSPACE 解析（避免 CLI 从别处启动时产物散落到进程 cwd）
        fig_dir = env.WORKSPACE / fig_dir
    try:
        fig_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        errors.append({"field": "figure_dir", "reason": f"无法创建输出目录: {e}"})

    output_name = req.get("output_name")
    lint_only = bool(req.get("lint_only"))
    if not output_name or not isinstance(output_name, str):
        if not lint_only:
            errors.append({"field": "output_name", "reason": "output_name 必填（ASCII 文件名，不含扩展名）"})
        output_name = ""
    elif not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$", output_name):
        errors.append({"field": "output_name",
                       "reason": f"output_name 必须为 ASCII 文件名（不含扩展名），实际 '{output_name}'"})

    content = req.get("content")
    description = req.get("description")
    template = req.get("template")

    if template is not None and template not in TEMPLATES:
        errors.append({"field": "template",
                       "reason": f"未知模板 '{template}'；可用: {_template_help()}",
                       "suggestion": "从上述模板中选择一个（字段规范见对应 references 文档），"
                                     "或省略 template 由 content/description 自动判定"})

    if content is None and (description is None or not str(description).strip()):
        errors.append({"field": "content",
                       "reason": "必须提供 content（结构化）或 description（文本）二者之一"})

    if errors:
        return _assemble_diag(False, [], [], "", errors, fig_dir, req)

    # ---- 方式A：结构化 content ----
    if content is not None:
        if not isinstance(content, dict):
            return _assemble_diag(False, [], [], "", 
                                  [{"field": "content", "reason": "content 必须是 JSON 对象",
                                    "suggestion": "改为按模板字段表提供结构化对象（见 references 文档）"}],
                                  fig_dir, req)
        tpl = template or infer_template_from_content(content)
        if tpl is None:
            return _assemble_diag(
                False, [], [], "",
                [{"field": "template",
                  "reason": f"无法从 content 结构判定模板，请显式指定 template；可用: {_template_help()}",
                  "suggestion": "显式传入 template 字段，或在 content 中加入该模板的标志字段"}],
                fig_dir, req)
        if req.get("lint_only"):
            return _lint_and_assemble(py, tpl, content, fig_dir, req, language)
        return _render_and_export(py, tpl, content, output_name, fig_dir, req, language)

    # ---- 方式B：description（需 LLM 转换，CLI 默认无 LLM → 跳过并记录）----
    desc = str(description).strip()
    tpl = template or infer_template_from_description(desc)
    if not desc:
        return _assemble_diag(False, [], [], "", 
                              [{"field": "description", "reason": "description 为空"}], fig_dir, req)
    if len(desc) < 20:
        missing = "主题/目标；阶段或任务划分；方法或模型；结果与评价"
        return _assemble_diag(
            False, [], [], "",
            [{"field": "description",
              "reason": f"文本过短（{len(desc)} 字），不足以结构化转换；缺少内容至少包括: {missing}。请补充或改用 content 模式"}],
            fig_dir, req)

    converter = os.environ.get("PLOT_LLM_CONVERT_CMD")
    if converter:
        converted = _run_llm_converter(converter, desc, tpl, language)
        if converted is None:
            return _assemble_diag(
                False, [], [], "",
                [{"field": "description", "reason": "LLM 转换子进程失败，请改用 content 模式"}],
                fig_dir, req, extra={"conversion_skipped": False})
        return _render_and_export(py, tpl, converted, output_name, fig_dir, req, language,
                                  extra={"converted_from": "description"})

    # 无 LLM：跳过转换并记录（验收 #4）
    return _assemble_diag(
        False, [], [], "",
        [{"field": "description",
          "reason": "description→content 转换需要 LLM 服务，本 CLI 环境未配置（PLOT_LLM_CONVERT_CMD 未设置）；"
                    "已跳过转换。请提供结构化 content，或在 DSH 宿主中使用 generate_diagram 工具（由宿主子代理完成转换）"}],
        fig_dir, req, extra={"conversion_skipped": True, "template_auto": tpl,
                             "auto_template_reason": "关键词判定"})


def _run_llm_converter(cmdline: str, desc: str, tpl: str, language: str) -> dict | None:
    """PLOT_LLM_CONVERT_CMD: 命令行（argv 形式），唯一参数为输入 JSON 文件路径
    {"description","template","language"}；stdout 输出 content JSON。"""
    import subprocess
    job = {"description": desc, "template": tpl, "language": language}
    path = Path(env.WORKSPACE) / "figures" / "_gen" / f"_convert_{int(time.time() * 1000)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    env.dump_json(str(path), job)
    try:
        p = subprocess.run([cmdline, str(path)], capture_output=True, text=True,
                           timeout=300, cwd=env.WORKSPACE, env={**os.environ, "PYTHONUTF8": "1"},
                           encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    if p.returncode != 0:
        return None
    try:
        obj = json.loads(p.stdout)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _lint_and_assemble(py, tpl, content, fig_dir, req, language) -> dict:
    """lint_only 模式：只校验，不渲染/导出。一次性返回全部字段与容量问题。"""
    r = lint_diagram(py, tpl, content, fig_dir)
    if r["ok"]:
        return _assemble_diag(
            True, [], [], f"lint 通过：{structure_summary(content, tpl)}", [], fig_dir, req,
            extra={"lint": True, "lint_ok": True, "template_used": tpl})
    out = _assemble_diag(
        False, [], [], "", r["errors"], fig_dir, req,
        extra={"lint": True, "lint_ok": False, "template_used": tpl,
               "lint_code": r.get("code")})
    out["errors"] = r["errors"]
    out["render_stdout"] = (r.get("stdout") or "")[-2000:]
    return out


def _render_and_export(py, tpl, content, output_name, fig_dir, req, language, extra=None) -> dict:
    r = render_diagram(py, tpl, content, output_name, fig_dir)
    if not r["ok"]:
        out = _assemble_diag(False, [], [], "", r["errors"], fig_dir, req,
                             extra={"overflow_code": r.get("code")})
        out["errors"] = r["errors"]
        out["render_stdout"] = r["stdout"][-2000:]
        return out

    drawio = r["drawio"]

    def _rel(p: Path) -> str:
        s = str(p) if not p.is_absolute() else str(p.relative_to(env.WORKSPACE))
        return s.replace("\\", "/")

    drawio_rel = _rel(drawio)
    # 版式自检（§4.6）
    lc = layout_check(drawio, py)
    # 导出
    ex = export_drawio(py, drawio)

    files = [{"path": drawio_rel, "kind": "diagram"}]
    if ex.get("png"):
        files.append({"path": _rel(drawio.with_suffix(".png")), "kind": "diagram"})
    if ex.get("pdf"):
        files.append({"path": _rel(drawio.with_suffix(".pdf")), "kind": "diagram"})
    summary = structure_summary(content, tpl)
    extra_out = dict(extra or {})
    extra_out["template_used"] = tpl
    extra_out["layout_check"] = lc
    if ex.get("skipped"):
        extra_out["export_skipped"] = {"reason": ex["reason"]}
    elif not ex["ok"]:
        extra_out["export_failed"] = {"reason": ex.get("error_tail") or "drawio 导出失败"}
    if drawio.exists() and drawio.stat().st_size == 0:
        extra_out["drawio_empty"] = True
    return _assemble_diag(True, files, [drawio_rel], summary, [], fig_dir, req,
                          extra=extra_out)


def _assemble_diag(ok: bool, generated: list, drawio_sources: list, data_features: str,
                   errors: list, fig_dir: Path, req: dict, extra: dict | None = None) -> dict:
    out = {
        "ok": ok,
        "generated_files": generated,
        "drawio_sources": drawio_sources,
        "data_features": data_features,
        "errors": errors,
        "environment": _env_snapshot(),
        "figure_dir": str(fig_dir),
    }
    if extra:
        out.update(extra)
    return out


_env_cache: dict = {}


def _env_snapshot() -> dict:
    now = time.time()
    if _env_cache.get("ts") and now - _env_cache["ts"] < 60:
        return _env_cache["data"]
    snap = env.snapshot()
    _env_cache.update({"ts": now, "data": snap})
    return snap