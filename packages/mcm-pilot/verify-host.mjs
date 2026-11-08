/**
 * verify-host.mjs：宿主等价 schema 校验（不启动 DSH）。
 *
 * 用真实 `@deepseek-ai/dsh-tools` 的 `assertSupportedJsonSchema` 对 4 个工具的
 * output.schema（宿主 register 必跑的校验）做断言——与插件树加载时宿主执行的是同一函数，
 * 通过即证明重启不会再崩。
 *
 * 依赖解析：优先用 DSH profile 里已装的 dsh-tools（同进程可解析），否则退回结构自检。
 * 不再写死任何本机 npx 缓存路径（换机也能跑）。
 *
 * 用法：node verify-host.mjs            # 有 dsh-tools 就做宿主等价断言
 *       DSH_TOOLS=<abs>/lib/index.js   # 显式指定 dsh-tools 入口
 */
import * as mod from "./index.js";

const tools = [];
mod.apply({
  tools: { register: (d) => tools.push(d) },
  systemPrompt: { section: () => {} },
  get: () => undefined,
  on: () => () => {},
});

if (tools.length !== 4) {
  console.error(`HOST_FAIL tool count=${tools.length}`);
  process.exit(1);
}

/** 尝试加载宿主的 assertSupportedJsonSchema（多处兜底，全部失败则返回 null）。 */
async function loadHostAssert() {
  const cands = [
    process.env.DSH_TOOLS,
    "@deepseek-ai/dsh-tools",
    "@deepseek-ai/dsh-tools/lib/index.js",
  ].filter(Boolean);
  for (const c of cands) {
    try {
      const m = await import(c.startsWith("/") || /^[A-Za-z]:/.test(c) ? "file://" + c.replace(/\\/g, "/") : c);
      if (typeof m.assertSupportedJsonSchema === "function") return m.assertSupportedJsonSchema;
    } catch {
      /* 试下一个 */
    }
  }
  return null;
}

// 本地结构兜底：宿主只接受 object/array/string/number/integer/boolean/null，
// 且 output.schema 必须是对象（{type:'json'} 这种 defineTool 方言会让整树加载失败）。
function localCheck(schema) {
  const okTypes = new Set(["object", "array", "string", "number", "integer", "boolean", "null"]);
  if (!schema || typeof schema !== "object") throw new Error("output.schema 不是对象");
  if (!okTypes.has(schema.type)) throw new Error(`output.schema.type 非法: ${schema.type}`);
}

const hostAssert = await loadHostAssert();
for (const t of tools) {
  if (hostAssert) hostAssert(t.output.schema);
  else localCheck(t.output.schema);
  console.log(`HOST_ASSERT_OK ${t.name} (output.type=${t.output.schema.type})${hostAssert ? "" : " [local]"}`);
}
console.log(`ALL_HOST_ASSERT_OK ${tools.map((t) => t.name).join(",")}`);
if (!hostAssert) {
  console.log("NOTE: 未解析到 @deepseek-ai/dsh-tools，以上为本地结构自检；在 DSH profile 目录下运行可做宿主等价断言。");
}
