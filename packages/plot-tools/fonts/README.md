# fonts/（可选）

本目录用来放**你自己的** CJK 字体文件（如 `simhei.ttf`、`SourceHanSansSC-Regular.otf`），
`plotcore/env.py` 会按 `$PLOT_FONT` → 本目录 → 系统字体 的顺序解析。

> 本仓库**不随附任何字体文件**：`simhei.ttf`（黑体）、`msyh.ttc`（雅黑）、`PingFang.ttc`（苹方）
> 等都是厂商专有字体，**不能再分发**。请在你的机器上自备，或使用开源字体
> （思源黑体 Source Han Sans / Noto Sans CJK / 文泉驿正黑，均为可自由再分发的 SIL OFL 字体）。
>
> 放好字体后无需改名：设 `PLOT_FONT=<绝对路径>` 即可；也可以直接把 ttf 拷进本目录并命名为 `cjk.ttf`。
