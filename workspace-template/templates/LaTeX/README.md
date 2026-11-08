# templates/LaTeX/<模板名>/ —— 论文模板（不放本仓库，自己准备）

> **为什么模板不放在这个仓库？** 模板是 `paper-writer`（论文写作插件）的资产：`paper_write` 按
> `<工作区>/templates/LaTeX/<目录名>` 解析类型与语言，本仓库的 mcm-pilot 只负责"检查这个目录在不在、问一句用哪个模板"。
> 因此**模板库（含你那个大模板库）建议跟 paper-writer 一起发一个仓库**：
> ① LaTeX 模板多为 LPPL/自有许可且体积大（cls+字体+规范 PDF），混进 MIT 的插件仓库会有许可与体积问题；
> ② 模板与排版修订强耦合（表超宽、浮动错位、符号表跨页都是模板侧的事），跟写作插件同版发布最顺；
> ③ 运行时两边读的是同一个 `<工作区>/templates/`，写作插件发模板即可，mcm-pilot 无需跟着改。
>
> 搬运方式：把上游模板仓库 clone 进 paper-writer 仓库的 `templates/LaTeX/<类型名>/`，**保留其原始 LICENSE**；
> 工作区里只放一份拷贝（`<工作区>/templates/LaTeX/`），别在两个仓库里各存一份不同步的副本。

`paper-writer` 的 `paper_write(template=…)` 会在这里找模板：按**目录名**解析「类型名」与语言，
例如目录 `zh_cumcm_1/` → 类型 `cumcm_1`、语言 `zh`。所以调用时写 **类型名**（`template="cumcm_1"`），
写目录名（`zh_cumcm_1`）会匹配失败并静默回退内置模板。

一个模板目录至少要有 `main.tex`（正文注入点约定见 paper-writer 文档，通常是 `% <<<BODY>>>` 标记）。

## 去哪拿模板

- 本仓库**不含**任何 LaTeX 模板（避免版权与体积问题）。
- 可与 `paper-writer` 插件一起分发；或从公开的 CUMCM LaTeX 模板（如 `latexstudio/CUMCMThesis`、
  `jayxin/cumcm`）自行复制，并**保留其原始 LICENSE**（这些仓库多为 LPPL 或自定义许可，不是 MIT）。

## 目录示例

```
templates/LaTeX/
├─ zh_cumcm_1/           # 类型 cumcm_1，中文
│  ├─ main.tex
│  ├─ cumcmthesis.cls
│  └─ sections/*.tex
└─ en_mcm/               # 类型 mcm，英文
   └─ main.tex
```
