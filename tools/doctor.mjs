#!/usr/bin/env node
/**
 * doctor.mjs —— 换机自检：一次把「能不能跑」的每一条链路都实际跑一遍。
 *
 * 用法：
 *   node tools/doctor.mjs            # 基础自检（node/python/资产/环境变量）
 *   node tools/doctor.mjs --full     # 额外跑 mcm_start 冒烟 + plot 自检（会真的起子进程）
 *   node tools/doctor.mjs --json     # 机器可读输出（给 AI 用）
 *
 * 退出码：0=全绿；1=有 FAIL。
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir, platform } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { findPython } from "./find-python.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO = dirname(__dirname);
const IS_WIN = platform() === "win32";
const argv = process.argv.slice(2);
const FULL = argv.includes("--full");
const JSON_ONLY = argv.includes("--json");

const MCM_PKG = join(REPO, "packages", "mcm-pilot");
const PLOT_PKG = join(REPO, "packages", "plot-tools");
const rows = [];
function add(name, ok, detail) {
  rows.push({ name, ok, detail: detail ?? "" });
}

// ---------------------------------------------------------------- node
const major = Number(process.versions.node.split(".")[0]);
add("node >= 18", major >= 18, `v${process.versions.node}`);

// ---------------------------------------------------------------- python
const py = findPython({ preferDeps: true });
add("python 可用", Boolean(py.python), py.python ? `${py.python} (${py.version})` : `试过 ${py.tried.length} 个候选（设 MCM_PYTHON 指向解释器）`);

function runPy(args, opts = {}) {
  if (!py.python) return null;
  return spawnSync(py.python, args, { encoding: "utf8", timeout: opts.timeout ?? 120000, cwd: opts.cwd ?? REPO });
}

// ---------------------------------------------------------------- 业务层与依赖
add("mcm_pilot.py", existsSync(join(MCM_PKG, "mcm_pilot.py")), join(MCM_PKG, "mcm_pilot.py"));
add("plot_plugin.py", existsSync(join(PLOT_PKG, "plot_plugin.py")), join(PLOT_PKG, "plot_plugin.py"));
add("diagram 模板", existsSync(join(PLOT_PKG, "diagram", "roadmap_5band.py")), join(PLOT_PKG, "diagram"));

if (py) {
  const probe = ["-c", "import importlib\nfor m in ['matplotlib','seaborn','pandas','numpy','openpyxl']:\n    try:\n        mod=importlib.import_module(m);print(m,'=',getattr(mod,'__version__','ok'))\n    except Exception as e:\n        print(m,'= MISSING')"];
  const r = runPy(probe);
  const out = (r && r.stdout) || "";
  const missing = ["matplotlib", "seaborn", "pandas", "numpy", "openpyxl"].filter((m) => out.includes(`${m} = MISSING`));
  add("plot 依赖", missing.length === 0, missing.length ? `缺：${missing.join(", ")}（pip install ${missing.join(" ")}）` : out.replace(/\s+/g, " ").trim());
}

// ---------------------------------------------------------------- 工作区
function looksLikeWorkspace(d) {
  return ["knowledge_base", "outputs", "论文插件需填充的文件"].some((m) => existsSync(join(d, m)));
}
const wsCands = [process.env.MCM_WORKSPACE, join(REPO, "workspace"), process.cwd()].filter(Boolean);
const ws = wsCands.find(looksLikeWorkspace) ?? null;
add("工作区", Boolean(ws), ws ? ws : `缺（把 workspace-template/ 复制成 workspace/，或设 MCM_WORKSPACE）；候选：${wsCands.join(" | ")}`);
if (ws) {
  add("  └ knowledge_base/", existsSync(join(ws, "knowledge_base")), "");
  add("  └ 论文插件需填充的文件/", existsSync(join(ws, "论文插件需填充的文件")), "缺则 mcm_start 只建目录、不填章节骨架");
  add("  └ templates/", existsSync(join(ws, "templates")), "缺则 mcm_start 不问模板、paper_write 回退内置模板");
}

// ---------------------------------------------------------------- 环境变量
for (const k of ["MCM_PYTHON", "PLOT_PYTHON", "MCM_WORKSPACE", "PLOT_WORKSPACE", "PLOT_FONT", "DSH_HOME"]) {
  const v = process.env[k];
  add(`env ${k}`, true, v ? v : "(未设，用默认解析)");
}

// ---------------------------------------------------------------- DSH 安装位
if (process.env.DSH_HOME || existsSync(join(process.env.HOME ?? process.env.USERPROFILE ?? "", ".dsh"))) {
  const home = process.env.DSH_HOME || join(process.env.HOME ?? process.env.USERPROFILE, ".dsh");
  add("DSH 安装位 mcm-pilot", existsSync(join(home, "profiles", "node_modules", "mcm-pilot")), join(home, "profiles", "node_modules", "mcm-pilot"));
  add("DSH 安装位 plot-tools", existsSync(join(home, "profiles", "node_modules", "dsh-plot-tools")), join(home, "profiles", "node_modules", "dsh-plot-tools"));
  const patch = join(home, "cordis.patch.yml");
  let txt = "";
  try { txt = readFileSync(patch, "utf8"); } catch { /* 未安装 */ }
  add("cordis.patch.yml 已接线", /mcm-pilot/.test(txt) && /dsh-plot-tools|plot-tools/.test(txt), patch);
  if (/mcm-pilot/.test(txt)) {
    const disabled = /id:\s*mcm-pilot[\s\S]{0,80}?disabled:\s*true/.test(txt);
    add("mcm-pilot 状态", true, disabled ? "已接线但 disabled: true（灰度/停用中，删掉该行即启用）" : "已接线且启用");
  }
}

// ---------------------------------------------------------------- 冒烟
if (FULL && py.python) {
  // mcm：在临时工作区跑一次 mcm_start，验证「python + JSON + 骨架」全链路
  const tmp = mkdtempSync(join(tmpdir(), "mcm-doctor-"));
  const reqFile = join(tmp, "req.json");
  try {
    const { writeFileSync, copyFileSync, mkdirSync } = await import("node:fs");
    mkdirSync(join(tmp, "workspace", "knowledge_base"), { recursive: true });
    copyFileSync(join(REPO, "workspace-template", "knowledge_base", "_README.md"), join(tmp, "workspace", "knowledge_base", "_README.md"));
    writeFileSync(reqFile, JSON.stringify({ tool: "start", args: { project: "doctor", topic: "doctor 冒烟：C题 数据统计", language: "zh" } }), "utf8");
    const r = runPy([join(MCM_PKG, "mcm_pilot.py"), "--request-file", reqFile, "--workdir", join(tmp, "workspace")]);
    let ok = false;
    let detail = (r?.stderr || "").slice(-200);
    try {
      const obj = JSON.parse(r.stdout);
      ok = obj.ok === true;
      detail = ok ? `骨架已生成：${(obj.result?.created || []).slice(0, 3).join(", ")}…` : JSON.stringify(obj.errors);
    } catch { /* 保持 ok=false */ }
    add("冒烟 mcm_start", ok, detail);
  } finally {
    try { rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
  }
  // plot：官方 --self-check
  const r2 = runPy([join(PLOT_PKG, "plot_plugin.py"), "--self-check"]);
  let ok2 = false;
  let d2 = (r2?.stderr || "").slice(-300);
  try {
    const snap = JSON.parse(r2.stdout);
    ok2 = Boolean(snap?.python?.exe) && Boolean(snap?.font?.ok);
    d2 = `python=${snap?.python?.exe} font=${snap?.font?.ok ? snap.font.path : "缺失"} drawio=${snap?.drawio?.ok}`;
  } catch { /* keep */ }
  add("冒烟 plot --self-check", ok2, d2);
}

// ---------------------------------------------------------------- 输出
const bad = rows.filter((r) => !r.ok);
if (JSON_ONLY) {
  console.log(JSON.stringify({ ok: bad.length === 0, repo: REPO, rows }, null, 2));
} else {
  console.log(`\nmcm-pilot-suite doctor  (repo: ${REPO})\n${"-".repeat(64)}`);
  for (const r of rows) console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.name}${r.detail ? "  —  " + r.detail : ""}`);
  console.log("-".repeat(64));
  console.log(bad.length ? `FAIL ${bad.length} 项：${bad.map((b) => b.name).join(", ")}` : "全绿：可以直接 mcm_start");
  console.log("提示：改环境变量后重跑本脚本；插件内看到的报错也带同样提示。\n");
}
process.exit(bad.length ? 1 : 0);
