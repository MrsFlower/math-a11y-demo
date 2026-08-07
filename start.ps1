# start.ps1 —— 一键启动服务（默认端口 8321）
# 用法： .\start.ps1            或   .\start.ps1 -Port 8322
# 不含任何密钥；API Key 请写在 .env（见 .env.example）。
param(
    [int]$Port = 8321
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 优先使用项目自带虚拟环境，其次用当前 python
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $py = $venvPy
    Write-Host "使用虚拟环境: $py"
} else {
    $py = "python"
    Write-Host "未发现 .venv，使用系统 python（建议先执行 python -m venv .venv）"
}

if (-not (Test-Path (Join-Path $PSScriptRoot ".env"))) {
    Write-Host "提示：未发现 .env，将以本地规则模式运行（无大模型解释）。复制 .env.example 为 .env 并填入 Key 可开启大模型。" -ForegroundColor Yellow
}

Write-Host "启动服务： http://127.0.0.1:$Port  （Ctrl+C 停止）" -ForegroundColor Green
& $py -m uvicorn app.main:app --port $Port
