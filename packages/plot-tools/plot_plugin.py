# -*- coding: utf-8 -*-
"""独立论文绘图插件 · CLI 入口（要求文件 §6）。

用法:
    python plot_plugin.py --request '<json>'          # 直接传请求 JSON
    python plot_plugin.py --request-file req.json     # 从文件读请求
    python plot_plugin.py --self-check                # 环境自检

输出: 统一为 §5 输出契约的 JSON（打印到 stdout，ok=false 时退出码 1）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    # 无论调用方环境如何，stdout/stderr 一律 UTF-8（cmd 重定向、DSH 宿主读取都依赖它）
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="独立论文绘图插件：数据图 / 流程图")
    ap.add_argument("--request", "-r", default=None, help="请求 JSON 字符串")
    ap.add_argument("--request-file", "-f", default=None, help="请求 JSON 文件路径")
    ap.add_argument("--self-check", action="store_true", help="环境自检")
    args = ap.parse_args()

    if args.self_check:
        from plotcore import selfcheck
        snap = selfcheck.report()
        print(json.dumps(snap, ensure_ascii=False, indent=2))
        print(selfcheck.render_text(snap), file=sys.stderr)
        return 0

    if args.request is not None:
        try:
            req = json.loads(args.request)
        except json.JSONDecodeError as e:
            _print_fail("request", f"请求 JSON 解析失败: {e}")
            return 1
    elif args.request_file is not None:
        p = Path(args.request_file)
        if not p.exists():
            _print_fail("request_file", f"文件不存在: {p}")
            return 1
        try:
            req = json.loads(p.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            _print_fail("request_file", f"请求 JSON 解析失败: {e}")
            return 1
    else:
        ap.print_help(sys.stderr)
        return 2

    from plotcore import handle_request
    out = handle_request(req)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


def _print_fail(field: str, reason: str) -> None:
    out = {"ok": False, "generated_files": [], "drawio_sources": [],
           "data_features": "", "errors": [{"field": field, "reason": reason}],
           "environment": {}}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())