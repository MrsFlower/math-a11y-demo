# 查找监听 8321 的进程并终止，然后在项目目录重启 uvicorn（带 --reload）。
$conn = Get-NetTCPConnection -LocalPort 8321 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($conn) {
    Write-Output ("killing PID=" + $conn.OwningProcess)
    Stop-Process -Id $conn.OwningProcess -Force
    Start-Sleep -Seconds 1
} else {
    Write-Output "no listener on 8321"
}
Set-Location (Join-Path $PSScriptRoot "..")
Start-Process -WindowStyle Hidden -FilePath "python" -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8321","--reload"
Start-Sleep -Seconds 4
$check = Get-NetTCPConnection -LocalPort 8321 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($check) { Write-Output ("restarted OK, PID=" + $check.OwningProcess) } else { Write-Output "restart FAILED" }
