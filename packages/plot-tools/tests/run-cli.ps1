# run-cli.ps1 —— 手动跑 plot CLI 的小工具（把 stdout 重定向到文件后回读）
# 目的：规避 Windows 上 pwsh 管道直启 python 的 0xc0000142 初始化失败。
#
# 用法：
#   pwsh -File tests\run-cli.ps1 -SelfCheck
#   pwsh -File tests\run-cli.ps1 -Req .\tests\fixtures\req_accept1.json
#   pwsh -File tests\run-cli.ps1 -Req '--request={"data":[...],"plots":[...]}'
#
# Python 解析顺序：-Py 参数 → $env:PLOT_PYTHON → $env:MCM_PYTHON → PATH 上的 python。
# 工作区 = 本包目录（plot_plugin.py 所在处），可用 $env:PLOT_WORKSPACE 覆盖。
param(
  [string]$Req = "",
  [string]$Py = "",
  [switch]$SelfCheck
)
$ws = if ($env:PLOT_WORKSPACE) { $env:PLOT_WORKSPACE } else { (Resolve-Path (Join-Path $PSScriptRoot '..')).Path }
if (-not $Py) { $Py = if ($env:PLOT_PYTHON) { $env:PLOT_PYTHON } elseif ($env:MCM_PYTHON) { $env:MCM_PYTHON } else { 'python' } }

$out = Join-Path $env:TEMP ("plot_cli_out_" + [guid]::NewGuid().ToString('N').Substring(0,8) + ".json")
$err = Join-Path $env:TEMP ("plot_cli_err_" + [guid]::NewGuid().ToString('N').Substring(0,8) + ".log")
$cli = Join-Path $ws 'plot_plugin.py'
if (-not (Test-Path $cli)) { Write-Error "找不到 $cli（用 -Req 时请在包目录或设 PLOT_WORKSPACE）"; exit 2 }

if ($SelfCheck) {
  cmd /c "`"$Py`" `"$cli`" --self-check 1> `"$out`" 2> `"$err`"" | Out-Null
} elseif ($Req -like '--request=*') {
  $reqJson = $Req.Substring(9)
  $tmp = Join-Path $env:TEMP ("plot_req_" + [guid]::NewGuid().ToString('N').Substring(0,8) + ".json")
  [System.IO.File]::WriteAllText($tmp, $reqJson, (New-Object System.Text.UTF8Encoding($false)))
  cmd /c "`"$Py`" `"$cli`" --request-file `"$tmp`" 1> `"$out`" 2> `"$err`"" | Out-Null
  Remove-Item $tmp -ErrorAction SilentlyContinue
} elseif ($Req) {
  cmd /c "`"$Py`" `"$cli`" --request-file `"$Req`" 1> `"$out`" 2> `"$err`"" | Out-Null
} else {
  cmd /c "`"$Py`" `"$cli`" --self-check 1> `"$out`" 2> `"$err`"" | Out-Null
}
Write-Host "python  = $Py"
Write-Host "workdir = $ws"
Write-Host "rc=$LASTEXITCODE"
if (Test-Path $out) { Write-Host (Get-Content -Raw -LiteralPath $out -Encoding UTF8); Remove-Item $out -ErrorAction SilentlyContinue }
if ((Test-Path $err) -and (Get-Item $err).Length -gt 0) { Write-Host '---stderr---'; Write-Host (Get-Content -Raw -LiteralPath $err -Encoding UTF8) }
Remove-Item $err -ErrorAction SilentlyContinue
