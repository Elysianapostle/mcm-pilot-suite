# -*- coding: utf-8 -*-
"""环境探测与子进程运行器（插件执行体专用）.

要点:
- 探测可用 Python 解释器（$PLOT_PYTHON/$MCM_PYTHON 优先，其次当前解释器与 PATH）。
- 探测依赖( matplotlib/seaborn/pandas/numpy/openpyxl )、中文字体（$PLOT_FONT → 包内 fonts → 系统字体）、drawio CLI、渲染脚本。
- run_interpreter(): 运行子进程一律使用 **文件重定向**（Windows: cmd /c ... > log 2>&1；
  POSIX: sh -c '...' > log 2>&1），规避 Windows 上 python.exe 在管道 stdio 下 0xc0000142 初始化失败的问题。
- 子进程环境注入 PYTHONUTF8=1 与 MPLCONFIGDIR(工作区内), 保证中文与字体缓存可写。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WORKSPACE = Path(os.environ.get("PLOT_WORKSPACE") or Path(__file__).resolve().parent.parent).resolve()
DIAGRAM_DIR = WORKSPACE / "diagram"
MPL_CACHE_DIR = Path(os.environ.get("PLOT_MPLCACHE") or (WORKSPACE / ".mplcache"))


def _font_candidates() -> list[Path]:
    """CJK 字体候选：$PLOT_FONT → 包内 fonts/ → 系统字体。

    开源版不内置 simhei.ttf（专有字体不可分发），改为探测用户机器上的字体；
    都没有时 font_ok() 会报缺失，绘图退化到系统字体名（中文可能显示方框）。
    """
    cands: list[Path] = []
    env_font = os.environ.get("PLOT_FONT")
    if env_font:
        cands.append(Path(env_font))
    cands += [WORKSPACE / "fonts" / "simhei.ttf", WORKSPACE / "fonts" / "cjk.ttf"]
    sys_dirs = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
        Path("/usr/share/fonts/truetype/noto"),
        Path("/usr/share/fonts/opentype/noto"),
        Path("/usr/share/fonts/truetype/wqy"),
        Path.home() / ".fonts",
    ]
    names = ["simhei.ttf", "msyh.ttc", "msyhbd.ttc", "simsun.ttc",
             "SourceHanSansSC-Regular.otf", "NotoSansCJK-Regular.ttc",
             "NotoSansCJKsc-Regular.otf", "PingFang.ttc", "wqy-zenhei.ttc"]
    for d in sys_dirs:
        for n in names:
            cands.append(d / n)
    return cands


def resolve_font() -> Path:
    for c in _font_candidates():
        try:
            if c.is_file() and c.stat().st_size > 1024:
                return c
        except OSError:
            continue
    return WORKSPACE / "fonts" / "simhei.ttf"  # 兜底：返回预期路径，供 font_ok() 报「字体缺失」


FONT_FILE = resolve_font()

RENDER_SCRIPTS = {
    "roadmap-5band": DIAGRAM_DIR / "roadmap_5band.py",
    "stageflow-3col": DIAGRAM_DIR / "stageflow_3col.py",
    "taskflow-land": DIAGRAM_DIR / "taskflow_land.py",
    "framework-3col": DIAGRAM_DIR / "framework_3col.py",
}
EXPORT_SCRIPT = DIAGRAM_DIR / "export_figure.py"
CHECK_SCRIPT = DIAGRAM_DIR / "check_layout.py"

PIP_PACKAGES = ["matplotlib", "seaborn", "pandas", "numpy", "openpyxl"]


def _probe_version(py: Path) -> str | None:
    """探测解释器版本；失败返回 None（例如 WindowsApps 空壳）。"""
    try:
        out = run_command([str(py), "--version"], timeout=60)
        if out is None:
            return None
        line = (out.get("stdout") or "").strip() or (out.get("stderr") or "").strip()
        return line if line else None
    except Exception:
        return None


# ---------------------------------------------------------------- 解释器探测
def candidate_pythons() -> list[Path]:
    cands: list[Path] = []
    for key in ("PLOT_PYTHON", "MCM_PYTHON"):
        env_override = os.environ.get(key)
        if env_override:
            cands.append(Path(env_override))
    # 正在运行本 CLI 的解释器就是最可靠候选（宿主已按 PLOT_PYTHON/PATH 选中它）
    try:
        cands.append(Path(sys.executable))
    except Exception:  # noqa: BLE001
        pass
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            cands.append(Path(found))
    return cands


def find_python() -> dict:
    """返回 {exe, version}；找不到返回 exe=None。"""
    seen: set[str] = set()
    for py in candidate_pythons():
        try:
            resolved = py.resolve()
        except Exception:
            resolved = py
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        ver = _probe_version(resolved)
        if ver:
            return {"exe": str(resolved), "version": ver}
    return {"exe": None, "version": None}


# ---------------------------------------------------------------- 子进程执行
def _shrink_path(arg: str) -> str:
    """命令行参数若指向工作区内（含输出目标），转相对路径，规避 cmd 传参中文/空格路径问题。"""
    if not arg:
        return arg
    try:
        ap = str(Path(arg).resolve())
    except Exception:  # noqa: BLE001
        return arg
    try:
        ws = str(WORKSPACE.resolve())
    except Exception:  # noqa: BLE001
        ws = str(WORKSPACE)
    if ap.startswith(ws + os.sep) and len(ap) > len(ws) + 1:
        return os.path.relpath(ap, ws)
    return arg


def _conda_env_paths() -> list[str]:
    """当前解释器位于 conda 环境时，返回其 Library\\bin / DLLs / 根的 PATH 前缀。

    conda 环境未激活时，子进程 delay-load（numpy.linalg/OpenBLAS 等）找不到
    Library\\bin 会以 Windows 0xC06D007F 硬崩，必须把环境 bin 目录带上。
    注意：env 解释器 `E:\\Miniforge\\envs\\<name>\\python.exe` 的 parent 即环境根
    （base 时是 `E:\\Miniforge`），凭 conda-meta 目录判定，勿用 parent.parent。
    """
    try:
        env_root = Path(sys.executable).resolve().parent
    except Exception:  # noqa: BLE001
        return []
    if not (env_root / "conda-meta").is_dir():
        return []
    return [str(env_root / sub) for sub in ("Library\\bin", "DLLs", "")]


def run_command(argv, timeout: int = 600, cwd=None, env_extra=None) -> dict | None:
    """以文件重定向 + cmd /c 方式执行命令, 返回 {ok, rc, stdout, stderr}。

    cwd 必须提供（无 cwd 时 cmd 的解析基准会飘）。
    env_extra: 追加到子进程环境的变量。
    """
    cwd = str(cwd) if cwd else str(WORKSPACE)
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))
    if env_extra:
        env.update(env_extra)
    _conda_bins = _conda_env_paths()
    if _conda_bins:
        _cur = env.get("PATH", "")
        env["PATH"] = ";".join(_conda_bins + ([_cur] if _cur else ""))
    fd_out, path_out = tempfile.mkstemp(suffix=".out.log", prefix="_dsh_", dir=str(WORKSPACE))
    os.close(fd_out)
    try:
        # cmd /c 把子进程 stdout/stderr 重定向到工作区文件，完全回避管道 stdio
        args = [_shrink_path(a) for a in argv]
        if os.name == "nt":
            cmdline = " ".join('"' + str(a).replace('"', '\\"') + '"' for a in args)
            quoted_log = _shrink_path(path_out).replace('"', '\\"')
            wrap = f'cmd /c "{cmdline} > "{quoted_log}" 2>&1"'
        else:
            # POSIX：shlex 引用，同样的「文件重定向」思路（不用管道）
            import shlex
            wrap = " ".join(shlex.quote(str(a)) for a in args) + f" > {shlex.quote(path_out)} 2>&1"
        p = subprocess.run(wrap, cwd=cwd, env=env, timeout=timeout, shell=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        text = Path(path_out).read_text(encoding="utf-8", errors="replace")
        return {"ok": p.returncode == 0, "rc": p.returncode, "stdout": text, "stderr": ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "rc": -1, "stdout": "", "stderr": f"timeout after {timeout}s"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "rc": -1, "stdout": "", "stderr": f"spawn failed: {e}"}
    finally:
        try:
            Path(path_out).unlink(missing_ok=True)
        except OSError:
            pass


def run_py(py: str, args, timeout: int = 600, cwd=None, env_extra=None) -> dict:
    """运行 python <args>, 返回 run_command 结构。"""
    return run_command([py, *args], timeout=timeout, cwd=cwd, env_extra=env_extra)


def run_py_script(py: str, script: str | os.PathLike, timeout: int = 600, cwd=None,
                  env_extra=None) -> dict:
    return run_py(py, [str(script)], timeout=timeout, cwd=cwd, env_extra=env_extra)


# ---------------------------------------------------------------- 依赖与资产
def imports_ok(py: str) -> list[dict]:
    """逐个 import 检查依赖, 返回 [{name, ok, version}]。"""
    probe = (
        "import importlib\n"
        "mods = ['matplotlib','seaborn','pandas','numpy','openpyxl']\n"
        "for m in mods:\n"
        "    try:\n"
        "        mod = importlib.import_module(m)\n"
        "        print(m, '=', getattr(mod, '__version__', 'ok'))\n"
        "    except Exception as e:\n"
        "        print(m, '= MISSING:', type(e).__name__, str(e)[:80])\n"
    )
    probe_file = WORKSPACE / "_probe_imports.py"
    try:
        probe_file.write_text(probe, encoding="utf-8")
        res = run_py_script(py, probe_file, timeout=120)
    finally:
        try:
            probe_file.unlink(missing_ok=True)
        except OSError:
            pass
    if not res or res.get("rc") != 0:
        return [{"name": n, "ok": False, "version": None, "note": "interpreter probe failed"}
                for n in PIP_PACKAGES]
    out = []
    for line in (res.get("stdout") or "").splitlines():
        parts = line.split(" = ", 1)
        if len(parts) != 2:
            continue
        name, rest = parts[0], parts[1]
        if rest.startswith("MISSING"):
            out.append({"name": name, "ok": False, "version": None,
                        "note": rest.split(":", 1)[-1].strip()})
        else:
            out.append({"name": name, "ok": True, "version": rest.strip()})
    missing_names = [n for n in PIP_PACKAGES if n not in [o["name"] for o in out]]
    out += [{"name": n, "ok": False, "version": None, "note": "probe produced no output"}
            for n in missing_names]
    return out


def font_ok() -> dict:
    if not FONT_FILE.exists():
        return {"ok": False, "path": str(FONT_FILE),
                "note": "字体文件缺失：装一个 CJK 字体，或用 PLOT_FONT 指向 ttf/otf（如 SourceHanSansSC / Noto Sans CJK / simhei）"}
    return {"ok": True, "path": str(FONT_FILE), "size": FONT_FILE.stat().st_size}


_DRAWIO_HINTS = [
    r"C:\Program Files\draw.io\draw.io.exe",
    r"C:\Program Files (x86)\draw.io\draw.io.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\draw.io\draw.io.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\drawio\draw.io.exe"),
    "/Applications/draw.io.app/Contents/MacOS/draw.io",
    "/usr/local/bin/drawio",
]


def drawio_probe() -> dict:
    cli = shutil.which("drawio") or shutil.which("draw.io")
    if not cli:
        # Windows/macOS 常见安装位置兜底（不依赖 PATH 刷新；桌面版实际产物名为 draw.io.exe）
        for cand in _DRAWIO_HINTS:
            if os.path.isfile(cand):
                cli = cand
                break
    if not cli:
        return {"ok": False, "exe": None,
                "note": "drawio CLI 缺失；保留 .drawio 并以手动命令导出（见 export_figure.py / 网页版）"}
    out = run_command([cli, "--version"], timeout=60)
    ver = (out or {}).get("stdout", "").strip() or (out or {}).get("stderr", "").strip()
    # 沙箱策略收紧时 Electron/Chromium 会输出 mojo 崩溃噪音行（"[...FATAL...]"），仅取版本号行
    clean = [l.strip() for l in ver.splitlines() if l.strip() and not l.startswith("[")]
    ver = "\n".join(clean) or ver
    return {"ok": True, "exe": cli, "version": ver or "?"}


def scripts_ok() -> dict:
    missing = []
    for key, p in RENDER_SCRIPTS.items():
        if not p.exists():
            missing.append(f"{key}: {p}")
    for label, p in (("export_figure", EXPORT_SCRIPT), ("check_layout", CHECK_SCRIPT)):
        if not p.exists():
            missing.append(f"{label}: {p}")
    return {"ok": not missing, "missing": missing,
            "export_script": str(EXPORT_SCRIPT), "check_script": str(CHECK_SCRIPT)}


def snapshot() -> dict:
    """环境自检快照（打进每次返回的 environment 字段）。"""
    py = find_python()
    return {
        "python": py,
        "python_candidates": [str(p) for p in candidate_pythons()],
        "dependencies": imports_ok(py["exe"]) if py["exe"] else [],
        "font": font_ok(),
        "drawio": drawio_probe(),
        "render_scripts": scripts_ok(),
        "workspace": str(WORKSPACE),
    }


def dump_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")