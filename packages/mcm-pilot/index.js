/**
 * mcm-pilot 适配层（DSH 宿主插件入口）。
 *
 * 薄壳：把业务层 mcm_pilot.py（独立 CLI，纯标准库）注册为 4 个宿主工具。
 * 请求经临时文件传递（规避 Windows 管道 stdio 限制），业务层 JSON 原样透传。
 *
 * 可移植性约定（换机不炸的关键）——所有路径按下列顺序解析，本文件不写死任何本机绝对路径：
 *   业务层 CLI : $MCM_PILOT_CLI → 包内 mcm_pilot.py → <工作区>/plugin/mcm_pilot.py（旧布局）
 *   Python     : $MCM_PYTHON → PATH 上的 python/python3（Windows 再试 py -3）
 *   工作区     : $MCM_WORKSPACE → 仓库内 workspace/ → 会话 cwd（含 knowledge_base/ 等契约目录者优先）
 * 要自定义只设环境变量，不要改本文件。
 */
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir, tmpdir, platform } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const name = "mcm-pilot";
export const inject = ["tools", "systemPrompt", "subprocess"];

const __dirname = dirname(fileURLToPath(import.meta.url));
const IS_WIN = platform() === "win32";
const PKG_ROOT = __dirname; // <repo>/packages/mcm-pilot
const REPO_ROOT = dirname(dirname(PKG_ROOT)); // <repo>

/**
 * 安装期探测结果（安装器写入，适配层只读）——这是「换机不炸」的主接口：
 * $MCM_CONFIG 或 $DSH_HOME/mcm-pilot.config.json 或 <repo>/mcm-pilot.config.json
 * 形如 {"python": "<abs>", "plotPython": "<abs>", "workspace": "<abs>"}
 */
function readConfig() {
  const home = process.env.DSH_HOME || join(homedir(), ".dsh");
  const cands = [
    process.env.MCM_CONFIG,
    join(home, "mcm-pilot.config.json"),
    join(REPO_ROOT, "mcm-pilot.config.json"),
    join(homedir(), ".mcm-pilot.config.json"),
  ].filter(Boolean);
  for (const p of cands) {
    try {
      if (existsSync(p)) return JSON.parse(readFileSync(p, "utf8"));
    } catch {
      /* 坏配置按未配置处理 */
    }
  }
  return {};
}

// ---------------------------------------------------------------- 解析：业务层 CLI
function resolveCli(workspace) {
  const cands = [
    process.env.MCM_PILOT_CLI,
    join(PKG_ROOT, "mcm_pilot.py"),
    workspace && join(workspace, "plugin", "mcm_pilot.py"),
    workspace && join(workspace, "mcm_pilot", "mcm_pilot.py"),
  ].filter(Boolean);
  return cands.find((p) => existsSync(p)) ?? null;
}

// ---------------------------------------------------------------- 解析：Python 解释器
/** 返回 {exe, args[]}；exe=null 表示没探到（由调用方给出可操作报错）。 */
function resolvePython() {
  const cfg = readConfig();
  const explicit = process.env.MCM_PYTHON || cfg.mcmPython || cfg.python;
  if (explicit) return { exe: explicit, args: /py(\.exe)?$/i.test(explicit) ? ["-3"] : [] };
  const names = IS_WIN ? ["python", "python3", "py"] : ["python3", "python"];
  for (const n of names) {
    // 绝对路径要判存在；裸名字交给 PATH（existsSync 对裸名字无意义，不能用来过滤）
    if (n.includes("/") || n.includes("\\")) {
      if (existsSync(n)) return { exe: n, args: n.endsWith("py") ? ["-3"] : [] };
      continue;
    }
    return { exe: n, args: n === "py" ? ["-3"] : [] };
  }
  return { exe: null, args: [] };
}

// ---------------------------------------------------------------- 解析：工作区
const WS_MARKERS = ["knowledge_base", "outputs", "论文插件需填充的文件"];
function looksLikeWorkspace(dir) {
  try {
    return WS_MARKERS.some((m) => existsSync(join(dir, m)));
  } catch {
    return false;
  }
}
function resolveWorkspace(exec) {
  const cfg = readConfig();
  const sessionCwd = exec?.agent?.session?.header?.cwd || process.cwd();
  const cands = [
    process.env.MCM_WORKSPACE,
    cfg.workspace,
    join(REPO_ROOT, "workspace"),
    join(PKG_ROOT, "workspace"),
    sessionCwd,
  ].filter(Boolean);
  for (const c of cands) if (looksLikeWorkspace(c)) return c;
  return sessionCwd;
}

function diagnoseHint(workspace) {
  return [
    "自检：node tools/doctor.mjs（或手工确认下列三项）",
    "- 业务层 mcm_pilot.py：$MCM_PILOT_CLI 或包内/工作区内存在",
    "- Python：$MCM_PYTHON 指向 python 可执行文件（业务层只用标准库，3.8+ 即可）",
    `- 工作区：$MCM_WORKSPACE 指向含 knowledge_base/ 与 论文插件需填充的文件/ 的目录（当前解析：${workspace}）`,
  ].join("；");
}

/** 业务层调用：请求写临时文件 → spawn → 收集 stdout → JSON.parse。永不抛错。 */
function runBusiness(ctx, tool, args, cwd) {
  const cli = resolveCli(cwd);
  const py = resolvePython();
  if (!cli || !py.exe) {
    const msg = !cli
      ? `mcm-pilot 业务层未找到（mcm_pilot.py）。可设 MCM_PILOT_CLI 指向该文件。${diagnoseHint(cwd)}`
      : `未找到可用的 Python 解释器。请设 MCM_PYTHON 指向 python 可执行文件。${diagnoseHint(cwd)}`;
    return Promise.resolve({ status: "failed", needs_input: msg, result: { ok: false, errors: [msg] } });
  }
  const tmpDir = mkdtempSync(join(tmpdir(), "mcm-pilot-"));
  const reqFile = join(tmpDir, "request.json");
  writeFileSync(reqFile, JSON.stringify({ tool, args }), "utf-8");
  return new Promise((resolvePromise) => {
    const proc = ctx.subprocess.spawn({
      argv: [py.exe, ...py.args, cli, "--request-file", reqFile, "--workdir", cwd],
      cwd,
      stdio: {
        stdin: "ignore",
        stdout: { maxBytes: 8388608, spill: { maxBytes: 33554432 } },
        stderr: { maxBytes: 1048576, spill: { maxBytes: 8388608 } },
      },
      graceMs: 15000,
      env: {
        PYTHONUTF8: "1",
        MCM_PILOT_HOME: process.env.MCM_PILOT_HOME ?? dirname(cli),
        MCM_WORKSPACE: cwd,
      },
    });
    proc.done
      .then(() => {
        let parsed = null;
        try {
          parsed = JSON.parse(proc.collected.stdout.readFrom(0).text);
        } catch {
          const head = (proc.collected?.stdout?.readFrom(0).text ?? "").slice(0, 400);
          const tail = (proc.collected?.stderr?.readFrom(0).text ?? "").slice(-400);
          parsed = {
            ok: false,
            errors: [
              `业务层 stdout 非 JSON 或为空（python=${py.exe}${py.args.length ? " " + py.args.join(" ") : ""}）`,
              `stdout头: ${head}`,
              `stderr尾: ${tail}`,
            ],
          };
        }
        resolvePromise(adapterFormat(parsed));
      })
      .catch((err) => {
        const m = err?.message ?? String(err);
        const hint = /ENOENT/.test(m)
          ? `（解释器/脚本不存在：python=${py.exe}，cli=${cli}；设 MCM_PYTHON / MCM_PILOT_CLI 覆盖）`
          : "";
        resolvePromise({
          status: "failed",
          needs_input: `子进程错误: ${m}${hint}`,
          result: { ok: false, errors: [String(err)] },
        });
      })
      .finally(() => {
        try {
          rmSync(tmpDir, { recursive: true, force: true });
        } catch {
          /* ignore */
        }
      });
  });
}

/** 业务层 {ok,result}/{ok:false,errors} → 宿主工具输出形态。 */
function adapterFormat(biz) {
  if (biz && biz.ok === true && biz.result) {
    const r = biz.result;
    return {
      status: r.needs_input ? "needs_input" : "ok",
      needs_input: r.needs_input ? JSON.stringify(r.questions ?? []) : "",
      result: r,
    };
  }
  const errors = biz && Array.isArray(biz.errors) ? biz.errors : ["未知业务错误"];
  return { status: "failed", needs_input: errors.join("; "), result: { ok: false, errors } };
}

function renderText(value) {
  const r = value?.result ?? value ?? {};
  const lines = [];
  const push = (k, v) => {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)) return;
    lines.push(`${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`);
  };
  push("status", value?.status);
  push("decided", r.decided);
  if (r.questions?.length) {
    push("questions", r.questions.map((q) => `${q.id}: ${q.question}（默认 ${q.default ?? "-"}）`).join(" | "));
  }
  if (r.needs_input === true) push("needs_input", "true —— 请用 ask_user_question 按 questions 向用户确认");
  push("created", r.created);
  push("existing", r.existing);
  push("project_json", r.project_json);
  if (r.loaded?.length) push("loaded", r.loaded.map((it) => `${it.file}[${it.matched}]`).join(" | "));
  push("totals", r.totals);
  push("injected_paths", r.injected_paths);
  if (r.traces?.length) {
    push("traces", r.traces.map((t) => `${t.figure} traced=${t.traced} data=[${(t.data_files ?? []).join(";")}] script=${t.script} results=[${(t.results ?? []).join(";")}]`).join(" | "));
  }
  push("summary", r.summary);
  push("redraw_commands", r.redraw_commands);
  push("redraw_figure", r.redraw_figure);
  push("counts", r.counts);
  push("missing", r.missing);
  push("next", r.next);
  push("note", r.note);
  if (value?.needs_input && r.needs_input !== true) push("needs_input", value.needs_input);
  return lines.length ? lines.join("\n") : "(no content)";
}

function registerTool(ctx, spec) {
  ctx.tools.register({
    name: spec.name,
    description: spec.description,
    parameters: {
      type: "object",
      additionalProperties: false,
      properties: spec.properties,
      required: spec.required,
    },
    output: {
      // 宿主 dsh-tools 只接受标准 JSON Schema 类型（object/array/string/number/integer/boolean/null）。
      // 写成 {type:'json'}（defineTool 方言）会让插件树加载失败 → DSH 完全无法启动。
      schema: {
        type: "object",
        additionalProperties: true,
        properties: {
          status: { type: "string", enum: ["ok", "needs_input", "failed"] },
          needs_input: { type: "string" },
          result: { type: "object", additionalProperties: true },
        },
      },
      render: (_args, value) => [{ type: "text", text: renderText(value) }],
    },
    timeoutMs: spec.timeoutMs ?? 30000,
    async execute(args, exec) {
      return runBusiness(ctx, spec.tool, args ?? {}, resolveWorkspace(exec));
    },
    presentCall: (args) => ({
      card: "generic",
      title: `${spec.name}: ${spec.title}`,
      kind: "execute",
      rawInput: Object.entries(args ?? {}).map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join(" "),
      content: [{ type: "text", text: `${spec.title}: ${JSON.stringify(args ?? {})}` }],
    }),
    presentResult: (_args, result) => {
      const block = result.content?.[0];
      const text = block && block.type === "text" ? block.text : JSON.stringify(result);
      return { card: "generic", content: [{ type: "text", text: `\`\`\`console\n${text}\n\`\`\`` }] };
    },
  });
}

function optStr(description) {
  return { type: "string", description };
}

export function apply(ctx) {
  ctx.systemPrompt.section({ name: "plugin:mcm-pilot", order: 214, text: PROMPT_SECTION });
  registerTool(ctx, {
    name: "mcm_start",
    tool: "start",
    title: "题目启动与缺口问卷",
    description:
      "mcm-pilot：接收数学建模题目（project+topic），自动检索缺失信息（协作模式 human/auto、语言 zh/en、LaTeX 模板、题号 A/B/C、交付文件），信息不足返回 needs_input+questions[]（请用 ask_user_question 向用户确认），足够则生成项目骨架 outputs/<project>/{content,figures,diagram,out,results,solver,scripts}+project.json。",
    properties: {
      project: { type: "string", description: "任务名（如 2025A），必填。" },
      topic: { type: "string", description: "题目简述（含题号/要求更佳），必填。" },
      problem_no: { type: "string", enum: ["A", "B", "C"], description: "题号（默认从题目文本识别）。" },
      language: { type: "string", enum: ["zh", "en"], description: "论文语言（默认按题目文本检测）。" },
      template: { type: "string", description: "LaTeX 模板名（如 zh_cumcm_1；唯一候选自动选定）。" },
      mode: { type: "string", enum: ["human", "auto"], description: "human=人机协同（默认）；auto=大部分自主决策。" },
      deliverables: { type: "string", description: "题目要求的交付结果文件（如 result1.xlsx / json / 图）。" },
      attachments: { type: "array", items: { type: "string" }, description: "题面/附件资料路径列表。" },
    },
    required: ["project", "topic"],
  });
  registerTool(ctx, {
    name: "mcm_kb_load",
    tool: "kb",
    title: "知识库约束注入",
    description:
      "mcm-pilot：扫描 knowledge_base/（或 kb_dir）的 md（只扫该目录根级、不递归子目录），按题型 types[]/关键词 keywords[] 命中后，把约束注入 outputs/<project>/content/hook.md（追加【KB】验收建议）并写 content/kb_hook.md（溯源清单）。知识库新增 md（建议 front-matter: types/keywords/name）后重跑本工具即自动生效。",
    properties: {
      project: { type: "string", description: "任务名（mcm_start 已创建），必填。" },
      types: { type: "array", items: { type: "string" }, description: "题型过滤（如 ['A'] / ['C']）。" },
      keywords: { type: "array", items: { type: "string" }, description: "关键词过滤（文件名/内容/front-matter keywords）。" },
      kb_dir: optStr("知识库目录（默认 <工作区>/knowledge_base）。"),
      force: { type: "boolean", description: "true=强制重新注入（默认幂等跳过）。" },
    },
    required: ["project"],
  });
  registerTool(ctx, {
    name: "mcm_fig_trace",
    tool: "figtrace",
    title: "图表溯源与重绘",
    description:
      "mcm-pilot：巡检 outputs/<project>/figures/ 每张图的溯源（figure ← data_files ← script ← results，manifest=figures/figure_manifest.json）。action=inspect 只读；action=register 按推导补登记；action=redraw 需传 fig=，返回重绘指令（重跑脚本 / plot_data_chart 规格与数据路径）。",
    properties: {
      project: { type: "string", description: "任务名，必填。" },
      fig: optStr("图名过滤（子串匹配，如 fig_q2）。"),
      action: { type: "string", enum: ["inspect", "register", "redraw"], description: "inspect（默认）/ register / redraw。" },
    },
    required: ["project"],
  });
  registerTool(ctx, {
    name: "mcm_status",
    tool: "status",
    title: "项目进度看板",
    description:
      "mcm-pilot：检查 outputs/<project>/ 进度——results/figures/manifest/diagram/content 填充度/out/main.pdf，返回 missing[] 缺口与 next[] 建议步骤。",
    properties: {
      project: { type: "string", description: "任务名，必填。" },
    },
    required: ["project"],
  });
}

const PROMPT_SECTION = `mcm-pilot 插件已启用（国赛数学建模「解题—绘图—论文」一体化编排）。标准工作流：1) mcm_start(project, topic) 接收题目：信息不足返回 needs_input+questions[]（协作方式 human/auto、语言 zh/en、模板、题号、交付文件），按需用 ask_user_question 向用户确认；2) mcm_kb_load(project, types=[题号]) 把 knowledge_base/ 命中文档注入 content/hook.md 的验收建议（新增知识库 md 后重跑即生效）；3) 求解落盘 outputs/<project>/results/*.json（数值唯一事实源），逐模块增量填充 content/；4) 出图：先聚合 figures/fig_*.csv 再 plot_data_chart 成 PDF，用 mcm_fig_trace 保证图←数据←脚本←结果可溯源（改数后按 redraw 指令重绘）；5) paper_write(content=[...], hook=content/hook.md, template=?, language, scenario="a") 产出 out/main.pdf；6) mcm_status 盯缺口。硬约束：参考文献 [^n]: 条目逐条空行分隔；正文每个数字必须可溯源到 results/；图后 ≥3 行解读；不编造数值/文献。`;
