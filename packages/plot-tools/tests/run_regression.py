# -*- coding: utf-8 -*-
"""回归驱动：进程内顺序执行 tests/fixtures/req_accept*.json 并输出结论表。

用法：
    python tests/run_regression.py [fixture 前缀白名单...]

不依赖命令行拼接（规避 Windows cmd 引号/空格问题）；环境缓存共享、一次进程跑完。
输出：结论表（stdout）+ 全量 JSON 落盘 _regress_all.json。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

WS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WS))

from plotcore import handle_request  # noqa: E402

FIXTURES = sorted((WS / "tests" / "fixtures").glob("req_accept*.json"))


def main() -> int:
    include = sys.argv[1:]
    rows = []
    results = {}
    for fx in FIXTURES:
        if include and not any(tok in fx.name for tok in include):
            continue
        try:
            req = json.loads(fx.read_text(encoding="utf-8-sig"))
            out = handle_request(req)
        except Exception as e:  # noqa: BLE001
            out = {"ok": False, "errors": [{"field": "driver", "reason": f"{type(e).__name__}: {e}"}]}
        note = []
        if out.get("lint") is not None:
            note.append(f"lint={out.get('lint_ok')}")
        if out.get("conversion_skipped"):
            note.append("conversion_skipped")
        if out.get("overflow_code"):
            note.append(f"code={out['overflow_code']}")
        if out.get("lint_code"):
            note.append(f"lint_code={out['lint_code']}")
        if out.get("template_used"):
            note.append(f"tpl={out['template_used']}")
        lc = out.get("layout_check") or {}
        if lc:
            note.append(f"layout_fail={len(lc.get('fails', []))}")
        errs = out.get("errors") or []
        fields = [e.get("field") for e in errs][:6]
        gen = [f.get("path") for f in (out.get("generated_files") or [])][:8]
        rows.append({
            "fixture": fx.name,
            "ok": bool(out.get("ok")),
            "n_errors": len(errs),
            "fields": fields,
            "note": " ".join(note),
            "files": gen,
        })
        results[fx.name] = {"ok": out.get("ok"), "errors": errs,
                            "generated_files": out.get("generated_files"),
                            "extra": {k: out[k] for k in
                                      ("lint", "lint_ok", "lint_code", "overflow_code",
                                       "conversion_skipped", "template_used", "layout_check")
                                      if k in out}}
    print(f"{'fixture':<20} {'ok':<5} {'errs':<5} fields/note")
    for r in rows:
        extra = " ".join([",".join(r["fields"]), r["note"]])
        print(f"{r['fixture']:<20} {str(r['ok']):<5} {r['n_errors']:<5} {extra}")
    (WS / "_regress_all.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())