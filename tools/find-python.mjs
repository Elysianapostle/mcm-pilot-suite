#!/usr/bin/env node
/**
 * find-python.mjs —— 找到「真的能用」的 Python 解释器（跳过 WindowsApps 空壳）。
 *
 * 为什么需要它：Windows 上 `python` 常指向 Microsoft Store 的空壳（
 * %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe），命令存在但什么也不干、
 * 退出码非 0 —— 插件因此报「CLI 无输出 / stdout 非 JSON」。这里按顺序探测并**实测**。
 *
 * 用法：
 *   node tools/find-python.mjs            # 打印可用解释器路径（找不到则退出码 1）
 *   node tools/find-python.mjs --json     # {"python": "...", "source": "..."}
 *   node tools/find-python.mjs --check X  # 只验证 X 是否可用
 *
 * 探测顺序：$MCM_PYTHON/$PLOT_PYTHON → 配置文件 → py -0p 列出的全部解释器 →
 *           conda/miniforge/anaconda 常见位置 → 系统 Python 安装目录 → PATH。
 */
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir, platform } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = dirname(__dirname);
const IS_WIN = platform() === "win32";

export function readConfig() {
  const home = process.env.DSH_HOME || join(homedir(), ".dsh");
  const cands = [
    process.env.MCM_CONFIG,
    join(home, "mcm-pilot.config.json"),
    join(REPO, "mcm-pilot.config.json"),
    join(homedir(), ".mcm-pilot.config.json"),
  ].filter(Boolean);
  for (const p of cands) {
    try {
      if (existsSync(p)) return { __path: p, ...JSON.parse(readFileSync(p, "utf8")) };
    } catch {
      /* 坏配置当作没配 */
    }
  }
  return {};
}

function isStub(p) {
  return /WindowsApps/i.test(p);
}

/** 实测：能不能 import sys 并打印出非空路径。 */
export function verify(p) {
  if (!p || isStub(p)) return null;
  try {
    if (existsSync(p) === false && p.includes("/")) return null;
  } catch {
    /* ignore */
  }
  const r = spawnSync(p, ["-c", "import sys;print(sys.executable)"], { encoding: "utf8", timeout: 20000 });
  if (r.error || r.status !== 0) return null;
  const out = (r.stdout || "").trim().split(/\r?\n/).pop() || "";
  if (!out || isStub(out)) return null;
  const v = spawnSync(p, ["-c", "import sys;print(sys.version.split()[0])"], { encoding: "utf8", timeout: 20000 });
  return { python: out, version: (v.stdout || "").trim(), source: p };
}

function whichAll(names) {
  const out = [];
  for (const n of names) {
    const r = spawnSync(IS_WIN ? "where" : "which", [n], { encoding: "utf8", timeout: 10000 });
    if (r.status === 0) out.push(...(r.stdout || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean));
  }
  return out;
}

function pyLauncherPythons() {
  // `py -0p` 例： -V:3.12 *        C:\Users\me\AppData\Local\Programs\Python\Python312\python.exe
  const r = spawnSync("py", ["-0p"], { encoding: "utf8", timeout: 15000 });
  if (r.status !== 0) return [];
  return (r.stdout || "")
    .split(/\r?\n/)
    .map((line) => (line.match(/([A-Za-z]:\\.*python\.exe)$/i) || [])[1])
    .filter(Boolean);
}

function globDirs(dir, prefix) {
  try {
    return readdirSync(dir, { withFileTypes: true })
      .filter((d) => d.isDirectory() && d.name.startsWith(prefix))
      .map((d) => join(dir, d.name));
  } catch {
    return [];
  }
}

export function candidates() {
  const cfg = readConfig();
  const home = homedir();
  const list = [];
  const push = (...p) => list.push(...p.filter(Boolean));

  push(process.env.MCM_PYTHON, process.env.PLOT_PYTHON, cfg.python, cfg.plotPython, cfg.mcmPython);

  if (IS_WIN) {
    push(...pyLauncherPythons());
    for (const base of [
      process.env.CONDA_PREFIX,
      join(process.env.USERPROFILE || home, "miniforge3"),
      join(process.env.USERPROFILE || home, "miniconda3"),
      join(process.env.USERPROFILE || home, "anaconda3"),
      join(process.env.PROGRAMDATA || "C:\\ProgramData", "miniforge3"),
      join(process.env.PROGRAMDATA || "C:\\ProgramData", "anaconda3"),
      join(process.env.LOCALAPPDATA || "", "miniforge3"),
      join(process.env.LOCALAPPDATA || "", "miniconda3"),
    ]) {
      if (base) push(join(base, "python.exe"), join(base, "envs", "mathmodel", "python.exe"));
    }
    for (const root of [join(process.env.LOCALAPPDATA || "", "Programs", "Python"), process.env.PROGRAMFILES, process.env["PROGRAMFILES(X86)"]]) {
      if (!root) continue;
      for (const d of globDirs(root, "Python3")) push(join(d, "python.exe"));
    }
    push(...whichAll(["python", "python3"]));
  } else {
    push("/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3", ...whichAll(["python3", "python"]));
  }
  // 去重保序
  const seen = new Set();
  return list.filter((p) => {
    const k = String(p).toLowerCase();
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

function hasDeps(p) {
  const r = spawnSync(p, ["-c", "import matplotlib,seaborn,pandas,numpy,openpyxl;print('ok')"], { encoding: "utf8", timeout: 60000 });
  return r.status === 0;
}

/**
 * @param {{preferDeps?: boolean}} opts  preferDeps=true 时优先返回「已装好绘图依赖」的解释器
 */
export function findPython({ preferDeps = false } = {}) {
  const tried = [];
  const working = [];
  for (const c of candidates()) {
    const v = verify(c);
    if (v) working.push(v);
    else tried.push(c);
  }
  if (working.length === 0) return { python: null, version: null, source: null, tried, deps: false };
  if (preferDeps) {
    for (const w of working) if (hasDeps(w.python)) return { ...w, tried, deps: true };
  }
  return { ...working[0], tried, deps: hasDeps(working[0].python) };
}

// CLI
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const argv = process.argv.slice(2);
  if (argv[0] === "--check") {
    const v = verify(argv[1]);
    if (v) console.log(JSON.stringify(v));
    process.exit(v ? 0 : 1);
  }
  const v = findPython();
  if (argv.includes("--json")) console.log(JSON.stringify(v, null, 2));
  else if (v.python) console.log(v.python);
  else {
    console.error(`找不到可用的 Python（试过 ${v.tried.length} 个候选）。请安装 Python 3.8+ 或设 MCM_PYTHON。`);
    for (const t of v.tried) console.error(`  - ${t}`);
  }
  process.exit(v.python ? 0 : 1);
}
