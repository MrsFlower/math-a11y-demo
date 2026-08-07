# test_api.ps1 —— 运行 API 验收测试
# 用法： .\test_api.ps1           # 完整测试（会调用大模型，较慢，可能接近 3 分钟）
#        .\test_api.ps1 -Fast     # 快速模式（只测本地规则/结构接口，不逐例调 LLM）
#        .\test_api.ps1 -Port 8322 -Fast
param(
    [int]$Port = 8321,
    [switch]$Fast
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPy) { $py = $venvPy } else { $py = "python" }

if ($Fast) { $mode = "快速" } else { $mode = "完整" }
Write-Host "运行 API 测试（端口 $Port，$mode 模式）..." -ForegroundColor Green

if ($Fast) {
    & $py scripts/api_test.py $Port --fast
} else {
    & $py scripts/api_test.py $Port
}
