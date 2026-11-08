# install.ps1 —— mcm-pilot-suite 一键安装（Windows / PowerShell 5.1+）
#
#   pwsh -File tools\install.ps1                # 安装到 $DSH_HOME（默认 ~/.dsh），灰度：disabled: true
#   pwsh -File tools\install.ps1 -Enable        # 装完直接启用（去掉 disabled）
#   pwsh -File tools\install.ps1 -NoDeps        # 跳过 pip 依赖安装
#
# 做四件事（每一步都可重复执行，幂等）：
#   1. 找可用的 Python（跳过 WindowsApps 空壳）并实测；找不到就给出安装建议后退出
#   2. 装绘图依赖 requirements.txt（可 -NoDeps 跳过）
#   3. 把两个包复制到 $DSH_HOME/profiles/node_modules/{mcm-pilot,dsh-plot-tools}
#   4. 写 $DSH_HOME/mcm-pilot.config.json（把探测到的 python/工作区固化下来）+ 在
#      $DSH_HOME/cordis.patch.yml 追加 insert（带 disabled: true 灰度）
param(
  [switch]$Enable,
  [switch]$NoDeps,
  [string]$Workspace = ""
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE ".dsh" }
$PkgRoot = Join-Path $DshHome "profiles\node_modules"
Write-Host "== mcm-pilot-suite 安装 ==" -ForegroundColor Cyan
Write-Host "repo      : $Repo"
Write-Host "DSH_HOME  : $DshHome"

# 1. Python
Write-Host "`n[1/4] 探测 Python …"
$pyJson = & node (Join-Path $Repo "tools\find-python.mjs") --json 2>$null
if ($LASTEXITCODE -ne 0) {
  $py = $null
} else {
  $py = ($pyJson | ConvertFrom-Json)
}
if (-not $py -or -not $py.python) {
  Write-Host "找不到可用 Python。请先装 Python 3.8+（推荐 Miniforge/Anaconda 或 python.org），" -ForegroundColor Red
  Write-Host "或设 MCM_PYTHON 指向解释器后重跑。`n提示：Windows 上 'python' 若是应用商店空壳，插件会报 'CLI 无输出'。" -ForegroundColor Red
  exit 1
}
Write-Host "  python  : $($py.python) ($($py.version))"

# 2. 依赖
if (-not $NoDeps) {
  Write-Host "`n[2/4] 安装绘图依赖（matplotlib/seaborn/pandas/numpy/openpyxl）…"
  & $py.python -m pip install --quiet --upgrade -r (Join-Path $Repo "packages\plot-tools\requirements.txt")
  if ($LASTEXITCODE -ne 0) { Write-Host "  pip 安装失败：可手动装，或加 -NoDeps 跳过（绘图工具会不可用）" -ForegroundColor Yellow }
  else { Write-Host "  依赖 OK" }
} else { Write-Host "`n[2/4] 跳过依赖安装（-NoDeps）" }

# 3. 复制包
Write-Host "`n[3/4] 复制插件到 profile node_modules …"
New-Item -ItemType Directory -Force -Path $PkgRoot | Out-Null
foreach ($pair in @(@("packages\mcm-pilot", "mcm-pilot"), @("packages\plot-tools", "dsh-plot-tools"))) {
  $src = Join-Path $Repo $pair[0]
  $dst = Join-Path $PkgRoot $pair[1]
  if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
  Copy-Item -Recurse -Force $src $dst
  Get-ChildItem -Recurse -Directory -Filter "__pycache__" -Path $dst -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
  Get-ChildItem -Recurse -Directory -Filter ".mplcache"  -Path $dst -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
  Write-Host "  $($pair[1]) -> $dst"
}

# 4. 配置文件 + 接线
Write-Host "`n[4/4] 写配置与接线 …"
$cfgPath = Join-Path $DshHome "mcm-pilot.config.json"
$ws = if ($Workspace) { $Workspace } elseif ($env:MCM_WORKSPACE) { $env:MCM_WORKSPACE } else { (Get-Location).Path }
$cfg = [ordered]@{ python = $py.python; plotPython = $py.python; workspace = $ws }
$cfg | ConvertTo-Json | Set-Content -Encoding UTF8 $cfgPath
Write-Host "  $cfgPath"
Write-Host "  workspace: $ws （改工作区就改这个文件，或设 MCM_WORKSPACE）"

$patchPath = Join-Path $DshHome "cordis.patch.yml"
if (Test-Path $patchPath) {
  Copy-Item $patchPath "$patchPath.bak-$(Get-Date -Format yyyyMMddHHmmss)" -Force
  $txt = Get-Content -Raw -Encoding UTF8 $patchPath
} else { $txt = "" }
$disabled = if ($Enable) { "" } else { "`n      disabled: true" }
$blocks = @(
  @("plot-tools", "dsh-plot-tools"),
  @("mcm-pilot", "mcm-pilot")
)
foreach ($b in $blocks) {
  if ($txt -match ("(?m)^\s*-?\s*id:\s*" + [regex]::Escape($b[0]) + "\s*$")) {
    Write-Host "  已存在 id=$($b[0])，跳过（如需改启停请直接编辑该文件）"
    continue
  }
  $add = "`n- insert:`n    - id: $($b[0])`n      name: '$($b[1])'$disabled`n"
  $txt = $txt.TrimEnd() + "`n" + $add
  Write-Host "  追加 insert: $($b[0])"
}
Set-Content -Encoding UTF8 -NoNewline $patchPath $txt
Write-Host "  $patchPath"

Write-Host "`n== 完成 ==" -ForegroundColor Green
Write-Host "自检：node tools\doctor.mjs --full"
if (-not $Enable) {
  Write-Host "当前为灰度（disabled: true）。启用：删掉 $patchPath 里对应行的 'disabled: true'（或重跑 install.ps1 -Enable，或侧边栏「插件」页开关）。"
}
Write-Host "重启 DSH（或等 HMR 重载）后，在会话里执行 mcm_start 开始；绘图可直接调 plot_data_chart。"
