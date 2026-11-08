/**
 * mcm-pilot 适配层增强桩测（安全规范 §3.2 + §6）：
 * 1) apply 冒烟：注册 4 工具无异常；
 * 2) schema lint：required 键要么 true 要么省略；required 数组元素都在 properties 中；
 *    output.schema = {type:'json'}；name/description 非空。
 * 隔离运行，不触碰 DSH。
 */
import { registerLint } from "./lint.mjs";
import * as mod from "./index.js";

const tools = [];
const ctx = {
  tools: { register: (d) => tools.push(d) },
  systemPrompt: { section: () => {} },
  get: () => undefined,
  on: () => () => {},
};
mod.apply(ctx);
if (tools.length !== 4) {
  console.error(`LINT_FAIL tool count=${tools.length}`);
  process.exit(1);
}
const errors = registerLint(tools);
if (errors.length) {
  console.error("LINT_FAIL\n" + errors.join("\n"));
  process.exit(1);
}
console.log(`APPLY_OK registered=${tools.map((t) => t.name).join(",")} LINT_OK`);