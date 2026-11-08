#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcm-pilot 业务层回归：fixture 全链路（start → kb(A/C) → figtrace → status）。

用法：python tests/run_regression.py
通过标准：全部断言 PASS，退出码 0；失败打印 FAIL 明细并以非 0 退出。
说明：进程内直接调用 mcm_pilot 纯函数（不走 subprocess/管道，规避 Windows 沙箱管道限制），
符合插件制作安全规范 §3.1（业务层 fixture 回归，全程不触碰 DSH）。"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import mcm_pilot  # noqa: E402

WS = ROOT / "fixtures" / "ws"
fails = []
passes = []


def check(name, cond, detail=""):
    if cond:
        passes.append(name)
        print(f"  PASS  {name}")
    else:
        fails.append(name)
        print(f"  FAIL  {name}  {detail}")


def reset_ws():
    out_dir = WS / "outputs"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)


def main():
    reset_ws()
    ws = str(WS)

    print("== 1. mcm_start（minimal：应生成骨架 + 问卷含 mode/language/template）")
    r = mcm_pilot.start({"project": "proj_demo",
                         "topic": "2025国赛A题 烟幕干扰弹投放策略，结果保存到result1.xlsx"}, ws)
    check("start_minimal.ok", r["ok"] is True, json.dumps(r)[:300])
    res = r["result"]
    check("start_minimal.created", len(res["created"]) >= 8, str(res["created"]))
    check("start_minimal.needs_input", res["needs_input"] is True)
    qids = [q["id"] for q in res["questions"]]
    check("start_minimal.questions.mode", "mode" in qids, str(qids))
    # 仅一个 zh 模板 → 自动选定不追问（合理默认）；language 由题目文本自动检测为 zh
    check("start_minimal.decided.template", res["decided"]["template"] == "zh_cumcm_1", str(res["decided"]))
    check("start_minimal.no_language_q", "language" not in qids, str(qids))
    check("start_minimal.decided.problem_no", res["decided"]["problem_no"] == "A", str(res["decided"]))
    check("start_minimal.decided.language", res["decided"]["language"] == "zh")
    check("start_minimal.project_json", bool(res["project_json"]))

    print("== 2. mcm_start（full：全部字段给定 → 无问卷）")
    r = mcm_pilot.start({"project": "proj_demo",
                         "topic": "2025国赛A题 烟幕干扰弹投放策略，结果保存到result1.xlsx",
                         "mode": "auto", "language": "zh", "template": "zh_cumcm_1"}, ws)
    check("start_full.ok", r["ok"] is True)
    res = r["result"]
    check("start_full.no_questions", res["questions"] == [], json.dumps(res["questions"], ensure_ascii=False))
    check("start_full.decided.template", res["decided"]["template"] == "zh_cumcm_1")
    check("start_full.assets.templates", (WS / "templates" / "LaTeX" / "zh_cumcm_1" / "main.tex").is_file())

    print("== 3. mcm_kb_load(types=['A'])：命中 11_物理建模方法论（启发），不命 C 题专项")
    r = mcm_pilot.kb({"project": "proj_demo", "types": ["A"]}, ws)
    check("kb_a.ok", r["ok"] is True, json.dumps(r, ensure_ascii=False)[:300])
    res = r["result"]
    files = [it["file"] for it in res["loaded"]]
    check("kb_a.loaded", "11_物理建模方法论.md" in files, str(files))
    check("kb_a.not_c", "12_C题数据统计专项约束.md" not in files, str(files))
    check("kb_a.injected", len(res["injected_paths"]) == 2, str(res["injected_paths"]))
    hook = (WS / "outputs" / "proj_demo" / "content" / "hook.md").read_text(encoding="utf-8")
    check("kb_a.hook_has_kb", "【KB】" in hook and "知识库约束" in hook)
    kb_hook = (WS / "outputs" / "proj_demo" / "content" / "kb_hook.md").read_text(encoding="utf-8")
    check("kb_a.kb_hook_trace", "11_物理建模方法论.md" in kb_hook)

    print("== 4. mcm_kb_load(types=['C'])：命中 C 题专项（front-matter types）")
    r = mcm_pilot.kb({"project": "proj_demo", "types": ["C"]}, ws)
    res = r["result"]
    files = [it["file"] for it in res["loaded"]]
    check("kb_c.loaded", "12_C题数据统计专项约束.md" in files, str(files))
    check("kb_c.matched_by_types", bool(files) and res["loaded"][0]["matched"].startswith("types:"),
          str(res.get("loaded")))

    print("== 5. 注入 solver/results/figures 造数据 → mcm_fig_trace inspect")
    proj = WS / "outputs" / "proj_demo"
    (proj / "results" / "q1_result.json").write_text(json.dumps({"duration": 1.36}), encoding="utf-8")
    (proj / "solver" / "prep_figs.py").write_text(
        "# 从 results/q1_result.json 聚合为 fig_demo 数据\n"
        "import json, os\n"
        "d = json.load(open(os.path.join('..', 'results', 'q1_result.json')))\n"
        "print(d['duration'])\n", encoding="utf-8")
    (proj / "figures" / "fig_demo.csv").write_text("t,occluded\n0,0\n1,1\n", encoding="utf-8")
    (proj / "figures" / "fig_demo.pdf").write_bytes(b"%PDF-1.4 fixture")
    r = mcm_pilot.figtrace({"project": "proj_demo", "action": "inspect"}, ws)
    check("figtrace.ok", r["ok"] is True)
    traces = r["result"]["traces"]
    check("figtrace.sees_fig", len(traces) == 1 and traces[0]["figure"] == "fig_demo.pdf", str(traces))
    check("figtrace.derives_data", any(x.endswith("figures/fig_demo.csv") for x in traces[0]["data_files"]),
          str(traces[0]["data_files"]))
    check("figtrace.derives_script", "prep_figs.py" in traces[0]["script"], str(traces[0]["script"]))
    check("figtrace.derives_result", any("q1_result.json" in x for x in traces[0]["results"]),
          str(traces[0]["results"]))
    check("figtrace.untraced_flag", traces[0]["traced"] is False)

    print("== 6. mcm_fig_trace(action=register)：写出 figure_manifest.json")
    r = mcm_pilot.figtrace({"project": "proj_demo", "action": "register"}, ws)
    check("figtrace_register.ok", r["ok"] is True)
    check("figtrace_register.written", (proj / "figures" / "figure_manifest.json").is_file())
    manifest = json.loads((proj / "figures" / "figure_manifest.json").read_text(encoding="utf-8"))
    check("figtrace_register.entry", len(manifest) == 1 and manifest[0]["figure"] == "fig_demo.pdf", str(manifest))

    print("== 7. mcm_status：缺口看板")
    r = mcm_pilot.status({"project": "proj_demo"}, ws)
    check("status.ok", r["ok"] is True)
    res = r["result"]
    check("status.counts", res["counts"]["results"] == 1 and res["counts"]["figures"] == 1,
          json.dumps(res["counts"], ensure_ascii=False))
    check("status.missing_pdf", "out/main.pdf 未生成" in " | ".join(res["missing"]), str(res["missing"]))
    check("status.next", len(res["next"]) >= 1)

    print(f"\n== 汇总：PASS {len(passes)} / FAIL {len(fails)}")
    if fails:
        print("FAILED:", ", ".join(fails))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())