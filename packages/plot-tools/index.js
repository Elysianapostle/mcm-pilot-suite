// dsh-plot-tools — 宿主常驻绘图工具插件（数据图 + 流程图）
//
// ESM 模块，导出 { name, inject, apply }；用 ctx.tools.register(defineTool(...)) 注册
// plot_data_chart / generate_diagram 两个宿主工具，业务实现是同目录下的 plot_plugin.py（+ plotcore/ diagram/）。
//
// 可移植性约定（换机不炸的关键）——不写死任何本机路径：
//   Python   : $PLOT_PYTHON → PATH 上的 python/python3（Windows 再试 py -3）
//   业务层   : 始终取「与 index.js 同目录的 plot_plugin.py」（包内自包含）
//   工作区   : $PLOT_WORKSPACE → 包目录（figure_dir / data 引用都以它为基准）
//   CJK 字体 : $PLOT_FONT → 包内 fonts/ 下的 ttf → 系统字体（见 plotcore/env.py）
import { defineTool } from "@deepseek-ai/dsh-tools";
import { existsSync, readFileSync } from "node:fs";
import { homedir, platform } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const IS_WIN = platform() === "win32";
const MAX_INLINE_JSON = 15000;
const REPO_ROOT = dirname(dirname(__dirname));

/** 安装期探测结果（安装器写入，适配层只读）：$DSH_HOME/mcm-pilot.config.json 等。 */
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

const CLI = join(__dirname, "plot_plugin.py");
const WS = process.env.PLOT_WORKSPACE || readConfig().plotWorkspace || readConfig().workspace || __dirname;

function resolvePython() {
  const cfg = readConfig();
  const explicit = process.env.PLOT_PYTHON || process.env.MCM_PYTHON || cfg.plotPython || cfg.python;
  if (explicit) return { exe: explicit, args: /py(\.exe)?$/i.test(explicit) ? ["-3"] : [] };
  return IS_WIN ? { exe: "python", args: [] } : { exe: "python3", args: [] };
}

// 解开"调用方外层包了 input"的兼容形态（历史载荷）
function normalizeArgs(input) {
  if (
    input && typeof input === "object" && !Array.isArray(input) &&
    input.input && typeof input.input === "object" && !Array.isArray(input.input) &&
    (input.input.data || input.input.plots || input.input.content || input.input.description)
  ) {
    return input.input;
  }
  return input;
}

function summarize(value) {
  if (!value || typeof value !== "object") return String(value);
  const files = Array.isArray(value.generated_files)
    ? value.generated_files.map((f) => f && f.path).filter(Boolean).join(", ") || "(无)"
    : "(无)";
  const errs = Array.isArray(value.errors) ? value.errors.length : 0;
  return "ok=" + String(value.ok) + " | errors=" + errs + " | files=" + files;
}

const name = "plot-tools";
const inject = ["tools", "subprocess"];

function apply(ctx) {
  async function execCli(argv) {
    const proc = ctx.subprocess.spawn({
      argv,
      cwd: WS,
      stdio: {
        stdin: "ignore",
        stdout: { maxBytes: 8388608, spill: { maxBytes: 33554432 } },
        stderr: { maxBytes: 1048576, spill: { maxBytes: 8388608 } },
      },
      graceMs: 15000,
      env: {
        PYTHONUTF8: "1",
        PLOT_WORKSPACE: WS,
        ...(process.env.PLOT_PYTHON ? { PLOT_PYTHON: process.env.PLOT_PYTHON } : {}),
        ...(process.env.PLOT_FONT ? { PLOT_FONT: process.env.PLOT_FONT } : {}),
      },
    });
    const outcome = await proc.done;
    const out = proc.collected && proc.collected.stdout ? proc.collected.stdout.readFrom(0).text : "";
    const err = proc.collected && proc.collected.stderr ? proc.collected.stderr.readFrom(0).text : "";
    return {
      code: outcome && outcome.exitCode !== null ? outcome.exitCode : -1,
      stdout: out,
      stderr: err,
    };
  }

  async function runRequest(args) {
    try {
      const json = JSON.stringify(args);
      if (json.length > MAX_INLINE_JSON) {
        return {
          ok: false,
          generated_files: [],
          drawio_sources: [],
          data_features: "",
          errors: [{
            field: "request",
            reason: "请求 JSON 过长（" + json.length + " 字符，上限 " + MAX_INLINE_JSON +
              "），请将大数据改为 data[].path 引用的文件，或拆分 plots 分批调用",
          }],
        };
      }
      const py = resolvePython();
      if (!existsSync(CLI)) {
        return {
          ok: false,
          generated_files: [],
          drawio_sources: [],
          data_features: "",
          errors: [{ field: "runtime", reason: "业务层缺失：未找到 " + CLI + "（应与 index.js 同目录）" }],
        };
      }
      const r = await execCli([py.exe, ...py.args, CLI, "--request", json]);
      if (!r.stdout.trim()) {
        return {
          ok: false,
          generated_files: [],
          drawio_sources: [],
          data_features: "",
          errors: [{
            field: "runtime",
            reason: "CLI 无输出（python=" + py.exe + "）。确认 Python 可用并装好依赖：" +
              "matplotlib seaborn pandas numpy openpyxl；或用 `python plot_plugin.py --self-check` 自检" +
              (r.stderr ? "；stderr: " + r.stderr.slice(-500) : ""),
          }],
          code: r.code,
        };
      }
      let obj = null;
      try {
        obj = JSON.parse(r.stdout);
      } catch (e) {
        return {
          ok: false,
          generated_files: [],
          drawio_sources: [],
          data_features: "",
          errors: [{ field: "runtime", reason: "CLI 输出非 JSON: " + r.stdout.slice(0, 400) }],
          code: r.code,
        };
      }
      if (obj && typeof obj === "object" && !Array.isArray(obj)) return obj;
      return {
        ok: false,
        generated_files: [],
        drawio_sources: [],
        data_features: "",
        errors: [{ field: "runtime", reason: "CLI 返回非对象输出" }],
        code: r.code,
      };
    } catch (e) {
      return {
        ok: false,
        generated_files: [],
        drawio_sources: [],
        data_features: "",
        errors: [{ field: "runtime", reason: (e && e.message) || String(e) }],
      };
    }
  }

  function toolDef(toolName, description, parameters, execute) {
    return defineTool({
      name: toolName,
      description,
      parameters,
      output: {
        schema: { type: "json" },
        render: (args, value) => [{ type: "text", text: summarize(value) + "\n" + JSON.stringify(value, null, 2) }],
      },
      execute,
    });
  }

  const toolDataChart = toolDef(
    "plot_data_chart",
    "数据图流程：基于调用方提供的数据/结果文件绘制学术数据图（折线/箱线/散点/热力/水平条形/密度等）。输入=数据来源+图表规格（见参数 schema）；输出=PDF矢量+PNG预览+数据特征文本。只在手头有实际数据、需要展示趋势/分布/对比/相关性时调用；没有数据时不要调用，更不要编造数据。",
    {
      data: {
        type: "array",
        required: true,
        description: "数据来源：{\"path\": 文件路径} 或 {\"name\": 名字, \"value\": 内联二维数组}",
        items: { type: "object", additionalProperties: true },
      },
      plots: {
        type: "array",
        required: true,
        description: "图表规格：output_name(必填,ASCII), chart_type(必填 line|scatter|box|violin|hist|kde|barh|grouped_bar|heatmap|errorbar), x, y, hue, ci, annotations, notes",
        items: { type: "object", additionalProperties: true },
      },
      language: { type: "string", enum: ["zh", "en"] },
      figure_dir: { type: "string" },
    },
    async (args, exec) => runRequest(normalizeArgs(args)),
  );

  const toolDiagram = toolDef(
    "generate_diagram",
    "流程图流程：基于文本描述或结构化 content 渲染流程图/技术路线图（4 模板：roadmap-5band 全文路线、stageflow-3col 阶段执行流程、taskflow-land 多任务流水线、framework-3col 研究框架）。输入=content JSON 或 description 文本；输出=.drawio 源文件+PNG。只在需要表达流程/结构/路线/框架（非数据）时调用。lint_only=true 时只做字段+容量校验、不渲染，一次返回全部问题，适合快速迭代文案。",
    {
      template: { type: "string", enum: ["roadmap-5band", "framework-3col", "stageflow-3col", "taskflow-land"] },
      output_name: { type: "string", description: "ASCII 文件名（不含扩展名）；lint_only=true 时可省略" },
      content: { type: "object", description: "符合模板 schema 的结构化内容（优先）；模板 schema 见插件文档", additionalProperties: true },
      description: { type: "string", description: "文本描述（content 缺省时必填，插件自动转结构化）" },
      language: { type: "string", enum: ["zh", "en"] },
      lint_only: { type: "boolean", description: "只做字段+容量校验，不渲染/导出（lint 模式），一次返回全部问题" },
    },
    async (args, exec) => runRequest(normalizeArgs(args)),
  );

  ctx.tools.register(toolDataChart);
  ctx.tools.register(toolDiagram);
  console.log("[dsh-plot-tools] registered plot_data_chart + generate_diagram (workspace=" + WS + ")");
}

export { apply, inject, name };
