/** schema 契约 lint（《插件制作安全规范》§2.2 / §6）。供 smoke.mjs 复用。 */

// 宿主 dsh-tools assertSupportedJsonSchema 的标准类型封闭表（实测：'json' 不在其中，
// 会在插件树加载时抛 JsonSchemaError 导致 DSH 无法启动 —— 见规范 §7 事故2）。
const SUPPORTED_SCHEMA_TYPES = new Set(["object", "array", "string", "number", "integer", "boolean", "null"]);

export function registerLint(tools) {
  const errors = [];
  for (const t of tools) {
    if (!t.name || typeof t.name !== "string") errors.push(`${t.name ?? "?"}: name 缺失`);
    if (!t.description || typeof t.description !== "string") errors.push(`${t.name}: description 缺失`);
    const p = t.parameters;
    if (!p || p.type !== "object" || !p.properties || typeof p.properties !== "object") {
      errors.push(`${t.name}: parameters 必须是 {type:'object', properties} 形态`);
      continue;
    }
    for (const [k, v] of Object.entries(p.properties)) {
      if (v && Object.prototype.hasOwnProperty.call(v, "required") && v.required !== true) {
        errors.push(`${t.name}.parameters.${k}.required 必须为 true 或省略（当前: ${JSON.stringify(v.required)}）`);
      }
    }
    const req = p.required ?? [];
    if (!Array.isArray(req)) {
      errors.push(`${t.name}: parameters.required 必须是数组`);
    } else {
      for (const r of req) {
        if (!p.properties[r]) errors.push(`${t.name}: required 项 "${r}" 不在 properties 中`);
      }
    }
    const out = t.output;
    if (!out || !out.schema) {
      errors.push(`${t.name}: output.schema 缺失`);
      continue;
    }
    const st = out.schema.type;
    if (typeof st !== "string" || !SUPPORTED_SCHEMA_TYPES.has(st)) {
      errors.push(`${t.name}: output.schema.type 必须是标准 JSON Schema 类型之一（${[...SUPPORTED_SCHEMA_TYPES].join("/")}），当前 "${st}"（type:'json' 必崩！）`);
    }
  }
  return errors;
}