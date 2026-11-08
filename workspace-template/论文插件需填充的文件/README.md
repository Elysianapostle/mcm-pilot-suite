# 论文插件需填充的文件/（章节骨架模板）

`mcm_start` 建新项目时，会把本目录的 `content/*.md` 与 `hook.md` **复制**一份到
`outputs/<project>/content/`，之后你只改项目里的副本，不动这里。

| 文件 | 内容 |
|---|---|
| `hook.md` | 约束注入点：题面要求、强调的贡献点、验收线等（`mcm_kb_load` 往里追加【KB】段） |
| `content/00_key_materials.md` | 摘要素材（结论数字/贡献点先在正文里对齐） |
| `content/01_restatement.md` | 问题重述 |
| `content/02_analysis.md` | 问题分析 |
| `content/03_assumptions.md` | 模型假设 |
| `content/04_symbols.md` | 符号说明 |
| `content/05_data.md` | 数据预处理（数据题必填） |
| `content/06_problemN.md` | 第 N 问的建立与求解（每问一份） |
| `content/09_sensitivity.md` | 灵敏度/稳健性分析 |
| `content/10_evaluation.md` | 模型评价与推广 |
| `content/11_references.md` | 参考文献（`[^n]:` 条目**逐条空行分隔**） |
| `content/12_appendix.md` | 附录（代码/数据清单） |
| `content/13_ai_declaration.md` | AI 使用声明（多数赛事现在必填） |

## 使用

1. 新项目：`mcm_start` 自动复制；
2. 逐模块增量填写（每写完一章立刻落盘）；
3. `mcm_status` 看填充度缺口；
4. 交给 `paper_write(content=[...], hook=content/hook.md, template="<模板类型名>", language="zh")` 出 `out/main.pdf`。

改模板只影响**以后新建**的项目；已建项目不受影响。
