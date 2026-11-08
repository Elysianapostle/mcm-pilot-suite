#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcm-pilot 业务层 CLI（纯标准库，不依赖任何第三方包，不触碰 DSH）。

子命令：start / kb / figtrace / status
用法：  python mcm_pilot.py --request-file <req.json> [--workdir <会话工作区>]
请求：  {"tool": "start", "args": {...}}
输出：  {"ok": true, "result": {...}} 或 {"ok": false, "errors": [...]}
约定：  路径默认相对 --workdir（会话工作区）；knowledge_base / templates / 论文插件需填充的文件 为工作区内契约目录。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def read_text(p):
    return Path(p).read_text(encoding="utf-8")


def write_text(p, s):
    Path(p).write_text(s, encoding="utf-8")


def read_json(p):
    try:
        return json.loads(read_text(p))
    except Exception:
        return None


def write_json(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def rel(p, base):
    """把路径转成相对 base 的正斜杠路径；base 之外返回绝对路径。"""
    try:
        return Path(p).resolve().relative_to(Path(base).resolve()).as_posix()
    except ValueError:
        return Path(p).resolve().as_posix()


def normalize(s):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", str(s).lower())


def parse_front_matter(text):
    """简单 front-matter：--- 开头两段；支持 key: value / key: [a, b]。"""
    meta, body = {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
            else:
                v = v.strip("'\"")
            meta[k.strip()] = v
    return meta, body


def has_cjk(s):
    return bool(re.search(r"[\u4e00-\u9fff]", s))


def detect_language(topic):
    return "zh" if has_cjk(topic) else "en"


def first_heading(text):
    for line in text.splitlines():
        if line.startswith("#") and line.strip() != "#":
            return line.lstrip("#").strip()
    return ""


def shorten(s, n=120):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


# ---------------------------------------------------------------------------
# 类型/模板/知识库探测
# ---------------------------------------------------------------------------

GUESS_RULES = [
    (("A",), ("物理", "机理", "力学", "几何", "光学", "弹道", "圆柱", "无人机", "烟幕", "轨道", "仿真")),
    (("B",), ("资源", "调度", "分配", "路径", "规划", "网络", "优化", "仓储", "物流")),
    (("C",), ("数据", "统计", "预测", "回归", "分类", "时间序列", "样本", "指标", "因子")),
]


def guess_types(text, filename):
    hit = set()
    for types, kws in GUESS_RULES:
        if any(k in text for k in kws) or any(k in filename for k in kws):
            hit.update(types)
    return sorted(hit)


def list_templates(ws):
    """扫描 templates/LaTeX/<folder>，返回 [{folder, type, language, prefix}]。"""
    out = []
    root = Path(ws) / "templates" / "LaTeX"
    if not root.is_dir():
        return out
    for folder in sorted(p.name for p in root.iterdir() if p.is_dir()):
        name = folder
        lang, typ = None, name
        for prefix in ("en_zh_", "zh_", "en_"):
            if name.startswith(prefix):
                lang = prefix[:-1]
                typ = name[len(prefix):]
                break
        out.append({"folder": folder, "type": typ, "language": lang or "?", "prefix": prefix if lang else ""})
    return out


def load_readme_usage(kb_dir):
    """解析 knowledge_base/_README.md 的「文件|用途」表 → {文件名: 用途}。"""
    usage = {}
    rd = Path(kb_dir) / "_README.md"
    if not rd.is_file():
        return usage
    lines = read_text(rd).splitlines()
    for ln in lines:
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0].endswith(".md"):
            usage[cells[0]] = cells[1]
    return usage


def find_script_candidates(ws, project, stem):
    """在 outputs/<project>/{solver,scripts} 找含 stem 的 .py。"""
    found = []
    for sub in ("solver", "scripts"):
        d = Path(ws) / "outputs" / project / sub
        if d.is_dir():
            for f in sorted(d.glob("*.py")):
                if stem in f.name or (stem and stem in read_text(f)[:4000]):
                    found.append(rel(f, ws))
    return found[:3]


# ---------------------------------------------------------------------------
# start：题目启动 + 缺口问卷 + 骨架生成
# ---------------------------------------------------------------------------

# 契约模板清单：与「论文插件需填充的文件/content/」目录保持对齐（start/status 实际按该目录 glob，
# 清单仅作声明与校验参考）。13_ai_declaration.md 为 2025 新规必填（AI 使用声明），缺则论文缺 AI 声明。
REQ_TEMPLATES = ["00_key_materials.md", "01_restatement.md", "02_analysis.md", "03_assumptions.md",
                 "04_symbols.md", "05_data.md", "06_problemN.md", "09_sensitivity.md",
                 "10_evaluation.md", "11_references.md", "12_appendix.md", "13_ai_declaration.md"]

START_QUESTIONS = [
    {"id": "mode",
     "question": "本题采用哪种协作方式：人机协同（关键决策先问）还是大部分自主决策（只在分歧时问一次）？",
     "options": [{"label": "human", "description": "人机协同：每题关键决策（如验收基准、分派方案）先确认"}, {"label": "auto", "description": "自主决策：仅在大方向分歧时问一次"}],
     "default": "human"},
    {"id": "language",
     "question": "论文语言用中文还是英文？（默认按题目文本自动检测）",
     "options": [{"label": "zh", "description": "中文（CUMCM/国赛）"}, {"label": "en", "description": "英文（MCM/ICM）"}],
     "default": None},
    {"id": "template",
     "question": "选用哪个 LaTeX 模板？",
     "options": None,
     "default": None},
    {"id": "problem_no",
     "question": "这是哪道题（A/B/C）？",
     "options": [{"label": "A", "description": "机理/物理类"}, {"label": "B", "description": "运筹/调度类"}, {"label": "C", "description": "数据/统计类"}],
     "default": None},
    {"id": "deliverables",
     "question": "题目要求交付什么结果文件（如 result1.xlsx / json / 图）？",
     "options": None,
     "default": None},
]


def start(args, ws):
    project = str(args.get("project", "")).strip()
    topic = str(args.get("topic", "")).strip()
    errors = []
    if not project:
        errors.append("project 不能为空（任务名，如 2025A）。")
    if not topic:
        errors.append("topic 不能为空（题目简述，如：2025国赛A题 烟幕干扰弹投放策略）。")
    if errors:
        return {"ok": False, "errors": errors}

    tpls = list_templates(ws)
    lang_auto = detect_language(topic)
    decided = {
        "mode": args.get("mode") or "human",
        "language": args.get("language") or lang_auto,
        "template": args.get("template"),
        "problem_no": str(args.get("problem_no", "")).upper() or None,
        "deliverables": args.get("deliverables"),
        "attachments": args.get("attachments") or [],
    }
    # 从题目文本启发补充
    m = re.search(r"(?<![A-Za-z])([ABC])[题号]", topic)
    if not decided["problem_no"] and m:
        decided["problem_no"] = m.group(1)
    dm = re.search(r"(result\s*\d+\.(?:xlsx|xls|json|csv))", topic, re.I)
    if not decided["deliverables"] and dm:
        decided["deliverables"] = dm.group(1).lower()

    questions = []
    for q in START_QUESTIONS:
        qid = q["id"]
        if qid == "language" and decided["language"]:
            continue
        if qid == "template":
            if decided["template"]:
                continue
            if not tpls:
                continue  # 无模板资产，默认内置模板
            lang = decided["language"]
            ok = [t for t in tpls if t["language"] in ("?", lang)]
            if len(ok) == 1:
                decided["template"] = ok[0]["folder"]
                continue
            qq = dict(q)
            qq["options"] = [{"label": t["folder"], "description": t["type"]} for t in ok] or None
            questions.append(qq)
            continue
        if qid == "problem_no" and decided["problem_no"]:
            continue
        if qid == "deliverables" and decided["deliverables"]:
            continue
        if qid == "mode" and args.get("mode"):
            continue
        qq = dict(q)
        if qid == "language":
            qq["default"] = lang_auto
        questions.append(qq)

    # 骨架生成（存在则跳过并记录）
    base = Path(ws) / "outputs" / project
    created, existing = [], []
    tpl_dir = Path(ws) / "论文插件需填充的文件"
    for sub in ("content", "figures", "diagram", "out", "results", "solver", "scripts"):
        d = base / sub
        if d.exists():
            existing.append(rel(d, ws))
        else:
            d.mkdir(parents=True, exist_ok=True)
            created.append(rel(d, ws))
    if (tpl_dir / "content").is_dir():
        for name in sorted((tpl_dir / "content").glob("*.md")):
            dst = base / "content" / name.name
            if dst.exists():
                existing.append(rel(dst, ws))
            else:
                shutil_copy(name, dst)
                created.append(rel(dst, ws))
    for name in ("hook.md",):
        src = tpl_dir / name
        if src.is_file():
            dst = base / "content" / name
            if dst.exists():
                existing.append(rel(dst, ws))
            else:
                shutil_copy(src, dst)
                created.append(rel(dst, ws))

    project_info = {
        "project": project,
        "topic": topic,
        "decided": decided,
        "questions": questions,
        "assets": {
            "templates": tpls,
            "knowledge_base": (Path(ws) / "knowledge_base").is_dir(),
        },
        "next": ["mcm_kb_load 注入知识库约束（可先答完问卷）",
                 "求解并落盘 results/*.json（数值唯一事实源）",
                 "出图 + figure_manifest 登记（mcm_fig_trace）",
                 "逐模块填充 content/（增量，不攒到最后）",
                 f"paper_write(content=[...], hook=content/hook.md, template=\"{decided.get('template') or 'cumcm_1'}\", language=\"{decided.get('language') or 'zh'}\") 产出 out/main.pdf —— template 必须与 project.json 一致，否则静默回退内置模板（见 knowledge_base/论文排版.md #1）"],
    }
    write_json(base / "project.json", project_info)
    created.append(rel(base / "project.json", ws))
    return {
        "ok": True,
        "result": {
            "status": "needs_input" if questions else "ready",
            "needs_input": len(questions) > 0,
            "questions": questions,
            "decided": decided,
            "created": created,
            "existing": existing,
            "project_json": rel(base / "project.json", ws),
            "next": project_info["next"],
        },
    }


def shutil_copy(src, dst):
    import shutil
    shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# kb：知识库约束注入
# ---------------------------------------------------------------------------

def kb(args, ws):
    project = str(args.get("project", "")).strip()
    kb_dir = Path(str(args.get("kb_dir") or (Path(ws) / "knowledge_base")))
    types = [str(t).upper() for t in (args.get("types") or [])]
    keywords = [str(k) for k in (args.get("keywords") or [])]
    force = bool(args.get("force", False))

    errors = []
    if not project:
        errors.append("project 不能为空。")
    if not kb_dir.is_dir():
        errors.append(f"知识库目录不存在: {kb_dir}")
    if errors:
        return {"ok": False, "errors": errors}

    usage = load_readme_usage(kb_dir)
    loaded = []
    for f in sorted(kb_dir.glob("*.md")):
        if f.name.startswith("_"):
            continue
        text = read_text(f)
        meta, body = parse_front_matter(text)
        name = meta.get("name") or f.stem
        f_types = meta.get("types") or guess_types(text, f.name)
        if isinstance(f_types, str):
            f_types = [f_types]
        f_kw = meta.get("keywords") or []
        if isinstance(f_kw, str):
            f_kw = [f_kw]

        matched = None
        if types:
            hit = [t for t in types if t in f_types]
            if hit:
                matched = "types:" + ",".join(hit)
            else:
                continue
        if not matched and keywords:
            for kw in keywords:
                nk = normalize(kw)
                if nk and (nk in normalize(f.name) or nk in normalize(text[:2000]) or any(nk == normalize(k) for k in f_kw)):
                    matched = f"keywords:{kw}"
                    break
            if not matched:
                continue
        if not matched and not types and not keywords:
            matched = "all"
        if not matched:
            continue

        summary = usage.get(f.name) or first_heading(body) or name
        loaded.append({
            "file": f.name,
            "name": name,
            "types": sorted(f_types),
            "keywords": f_kw,
            "matched": matched,
            "summary": shorten(summary, 120),
        })

    # 注入目标
    proj = Path(ws) / "outputs" / project
    hook_path = proj / "content" / "hook.md"
    kb_hook_path = proj / "content" / "kb_hook.md"
    if not hook_path.is_file():
        return {"ok": False, "errors": [f"项目骨架缺失 content/hook.md，请先运行 mcm_start(project={project})"]}

    pj = read_json(proj / "project.json") or {}
    decided = pj.get("decided", {})
    title = decided.get("title") or f"{project} 论文"
    lang = decided.get("language") or "zh"
    tpl = decided.get("template") or "cumcm"

    # 1) 重写 kb_hook.md（溯源清单）
    lines = [f"---", f"title: {title}", f"language: {lang}", f"template: {tpl}", "---", "",
             "# 知识库约束", "", "> 由 mcm-pilot 自动生成；改约束请修改 knowledge_base/*.md 后重跑 mcm_kb_load。", "",
             "| 文件 | 匹配依据 | 约束摘要 |", "|---|---|---|"]
    sug = []
    for i, it in enumerate(loaded):
        lines.append(f"| {it['file']} | {it['matched']} | {it['summary']} |")
        sug.append(f"- 【KB】[{it['file']}] {it['summary']}")
    lines.append("")
    lines.append("## 注入到 hook.md 的验收建议")
    lines.extend(sug)
    kb_hook_new = "\n".join(lines) + "\n"

    hook_text = read_text(hook_path)
    # 2) 在「强调的贡献点」节追加（逐条 bullet 行，paper-writer 会解析为 S 建议）
    marker = "## 强调的贡献点"

    def strip_injected_kb(text):
        """移除上次注入的 KB 段（# 知识库约束（mcm_pilot 注入…）+ 随后的 - 【KB】 行），
        供 force 重注入 / 约束变更时避免重复累积。"""
        lines, out, skipping = text.splitlines(), [], False
        for ln in lines:
            s = ln.strip()
            if s.startswith("# 知识库约束（mcm_pilot 注入"):
                skipping = True
                continue
            if skipping:
                if s.startswith("- 【KB】"):
                    continue
                skipping = False
            out.append(ln)
        cleaned, prev_blank = [], False
        for ln in out:
            blank = ln.strip() == ""
            if blank and prev_blank:
                continue
            cleaned.append(ln)
            prev_blank = blank
        while cleaned and cleaned[0].strip() == "":
            cleaned.pop(0)
        return "\n".join(cleaned).rstrip() + "\n"

    # 幂等：未强制 且 kb_hook 已存在且内容一致 → 跳过（删除既往 `all(... for f in [])` 恒真死代码）
    unchanged = (not force) and kb_hook_path.is_file() and read_text(kb_hook_path) == kb_hook_new
    if unchanged:
        injected = []
    else:
        write_text(kb_hook_path, kb_hook_new)
        hook_base = strip_injected_kb(hook_text)
        if marker in hook_base:
            head, tail = hook_base.split(marker, 1)
            tail_lines = tail.splitlines()
            insert_at = 1
            while insert_at < len(tail_lines) and (tail_lines[insert_at].strip().startswith("-") or tail_lines[insert_at].strip() == ""):
                if tail_lines[insert_at].strip() == "":
                    break
                insert_at += 1
            new_lines = ["", "# 知识库约束（mcm_pilot 注入，勿手改；改约束见 knowledge_base/*.md）"] + sug + [""]
            tail_lines[insert_at:insert_at] = new_lines
            new_hook = head + marker + "\n" + "\n".join(tail_lines)
        else:
            new_hook = hook_base.rstrip() + "\n\n## 强调的贡献点\n" + "\n".join(sug) + "\n"
        write_text(hook_path, new_hook)
        injected = [rel(kb_hook_path, ws), rel(hook_path, ws)]

    return {
        "ok": True,
        "result": {
            "status": "unchanged" if unchanged else "injected",
            "loaded": loaded,
            "totals": {"scanned": len([f for f in kb_dir.glob('*.md') if not f.name.startswith('_')]),
                       "loaded": len(loaded),
                       "injected": len(injected)},
            "injected_paths": injected,
            "note": "知识库新增约束：在 knowledge_base/ 添加 md（建议 front-matter: types/keywords），重跑本工具即生效。" if loaded else
                    "未命中任何知识库文档：请检查 types/keywords 参数或 knowledge_base 内容。",
        },
    }


# ---------------------------------------------------------------------------
# figtrace：图表溯源
# ---------------------------------------------------------------------------

def figtrace(args, ws):
    project = str(args.get("project", "")).strip()
    fig = str(args.get("fig", "")).strip() or None
    action = str(args.get("action", "inspect")).strip() or "inspect"
    errors = []
    figdir = Path(ws) / "outputs" / project / "figures"
    if not project:
        errors.append("project 不能为空。")
    if not figdir.is_dir():
        errors.append(f"项目 figures 目录不存在: {figdir}")
    if errors:
        return {"ok": False, "errors": errors}

    manifest_path = figdir / "figure_manifest.json"
    manifest = read_json(manifest_path) or []
    figures = sorted(list(figdir.glob("*.pdf")) + list(figdir.glob("*.png")))
    traces = []
    for fp in figures:
        name = fp.name
        if fig and fig not in name:
            continue
        entry = next((m for m in manifest if m.get("figure") == name), None)
        if entry:
            traces.append({
                "figure": name,
                "caption": entry.get("caption", ""),
                "data_files": entry.get("data_files", []),
                "script": entry.get("script", ""),
                "results": entry.get("results", []),
                "tool": entry.get("tool", ""),
                "notes": entry.get("notes", ""),
                "traced": True,
            })
            continue
        stem = fp.stem
        data_files = [rel(p, ws) for p in figdir.glob(f"{stem}.*") if p.suffix in (".csv", ".json")]
        results = [rel(p, ws) for p in (Path(ws) / "outputs" / project / "results").glob(f"{stem}.*")]
        if not results:
            results = [rel(p, ws) for p in (Path(ws) / "outputs" / project / "results").glob("*.json")
                       if stem in p.name]
        script = find_script_candidates(ws, project, stem)
        # 增强溯源：脚本内容中引用的 results/*.json|csv 也算结果依赖（改数重绘的关键链路）
        if script:
            try:
                stxt = read_text(Path(ws) / script[0])
                for m in re.finditer(r"(?:['\"]|results[/\\])?((?:q\d+|result\d+)[\w.-]*\.(?:json|csv))", stxt):
                    cand = (Path(ws) / "outputs" / project / "results" / m.group(1))
                    if cand.is_file():
                        rp = rel(cand, ws)
                        if rp not in results:
                            results.append(rp)
            except Exception:
                pass
        traces.append({
            "figure": name,
            "caption": "",
            "data_files": data_files,
            "script": script[0] if script else "",
            "results": results,
            "tool": "",
            "notes": "未登记（traced=false）：建议 mcm_fig_trace(action=register) 补登，或让生成脚本写 figure_manifest.json",
            "traced": False,
        })

    result = {"traces": traces, "manifest": rel(manifest_path, ws) if manifest_path.is_file() else None,
              "summary": {"figures": len(figures), "traced": sum(1 for t in traces if t["traced"]),
                          "untraced": sum(1 for t in traces if not t["traced"])}}

    if action == "register":
        by_name = {m["figure"]: m for m in manifest}
        for t in traces:
            if t["traced"]:
                continue
            by_name[t["figure"]] = {"figure": t["figure"], "caption": "",
                                    "data_files": t["data_files"], "script": t["script"],
                                    "results": t["results"], "tool": "", "notes": "由 mcm_fig_trace 推导登记"}
        write_json(manifest_path, sorted(by_name.values(), key=lambda x: x["figure"]))
        result["status"] = "registered"
        result["manifest_written"] = rel(manifest_path, ws)
    elif action == "redraw":
        if fig and traces and (traces[0]["script"] or traces[0]["data_files"]):
            t = traces[0]
            cmd = []
            if t["script"]:
                cmd.append(f"重跑数据聚合/生成脚本：python {t['script']}（先确认脚本可独立运行）")
            if t["data_files"]:
                cmd.append("重绘数据图：plot_data_chart(data_ref=绝对路径 " +
                           "、".join(t["data_files"]) +
                           ", figure_dir=<工作区内的目录>, output_name=<ASCII 名>)；或按 manifest.notes 的脚本重跑")
            result["redraw_commands"] = cmd
            result["redraw_figure"] = traces[0]["figure"]
        else:
            result["redraw_commands"] = []
            result["note"] = "未找到可重绘目标：请传 fig=（图名片段）且该图已有脚本或数据。"
    return {"ok": True, "result": result}


# ---------------------------------------------------------------------------
# status：进度看板
# ---------------------------------------------------------------------------

def status(args, ws):
    project = str(args.get("project", "")).strip()
    proj = Path(ws) / "outputs" / project
    if not project or not proj.is_dir():
        return {"ok": False, "errors": [f"项目不存在: outputs/{project}"]}

    results_dir = proj / "results"
    counts = {
        "results": len(list(results_dir.glob("*.json"))) if results_dir.is_dir() else 0,
        "csv": len(list(results_dir.glob("*.csv"))) if results_dir.is_dir() else 0,
        "xlsx": len(list(results_dir.glob("*.xlsx"))) if results_dir.is_dir() else 0,
        "figures": len(list((proj / "figures").glob("*.pdf"))) + len(list((proj / "figures").glob("*.png"))),
        "manifest": len(list((proj / "figures").glob("figure_manifest.json"))),
        "diagram": len(list((proj / "diagram").glob("*.pdf"))) + len(list((proj / "diagram").glob("*.png"))),
        "content": len([f for f in (proj / "content").glob("*.md") if f.name not in ("hook.md", "kb_hook.md")]),
    }
    counts["pdf"] = 1 if (proj / "out" / "main.pdf").is_file() else 0

    missing = []
    tpl_dir = Path(ws) / "论文插件需填充的文件" / "content"
    if tpl_dir.is_dir():
        for t in sorted(tpl_dir.glob("*.md")):
            dst = proj / "content" / t.name
            if not dst.is_file():
                missing.append(f"content/{t.name}（模板未复制）")
            elif len(read_text(dst)) < 200:
                missing.append(f"content/{t.name}（几乎为空，待填充）")
    if counts["results"] == 0:
        missing.append("results/ 无 json 结果（数值唯一事实源缺失）")
    if counts["figures"] == 0:
        missing.append("figures/ 无图")
    if counts["manifest"] == 0 and counts["figures"] > 0:
        missing.append("figures/figure_manifest.json 未登记（可 mcm_fig_trace(action=register)）")
    if counts["pdf"] == 0:
        missing.append("out/main.pdf 未生成（最后一步 paper_write）")

    next = []
    if "results/ 无 json 结果（数值唯一事实源缺失）" in missing:
        next.append("先求解并落盘 results/*.json")
    if counts["results"] > 0 and counts["figures"] == 0:
        next.append("聚合结果 → figures/fig_*.csv → plot_data_chart 出图，并登记 manifest")
    if any(m.startswith("content/") for m in missing):
        next.append("按 content 模板逐模块填充（增量）")
    if counts["pdf"] == 0 and counts["figures"] > 0 and not any(m.startswith("content/") for m in missing):
        next.append("调用 paper_write(content=[outputs/<project>/content/*.md], hook=content/hook.md) 出 PDF")
    if counts["pdf"] == 1:
        next.append("定稿核查：mcm_fig_trace 溯源核对 + 图文数字一致性 + 参考文献格式")

    return {"ok": True, "result": {"project": project, "counts": counts, "missing": missing, "next": next}}


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

TOOLS = {"start": start, "kb": kb, "figtrace": figtrace, "status": status}


def main(argv=None):
    ap = argparse.ArgumentParser(description="mcm-pilot 业务层")
    ap.add_argument("--request-file", required=True, help="请求 JSON 文件路径")
    ap.add_argument("--workdir", default=".", help="会话工作区（相对路径基准）")
    a = ap.parse_args(argv)
    req = read_json(a.request_file)
    if not isinstance(req, dict) or "tool" not in req:
        print(json.dumps({"ok": False, "errors": ["请求必须是 {tool, args} JSON"]}, ensure_ascii=False))
        return 2
    tool = req["tool"]
    fn = TOOLS.get(tool)
    if fn is None:
        print(json.dumps({"ok": False, "errors": [f"未知工具: {tool}（可用: {', '.join(TOOLS)}）"]}, ensure_ascii=False))
        return 2
    try:
        out = fn(req.get("args") or {}, a.workdir)
    except Exception as e:  # noqa: BLE001 —— 业务层不抛栈，一律结构化返回
        out = {"ok": False, "errors": [f"{type(e).__name__}: {e}"]}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())