# Restart test browser (9333 instance only, never touches main Chrome)
# 1. Kill old instance (match by user-data-dir, exclude child processes)
$old = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
    Where-Object { $_.CommandLine -like '*math-a11y-ext-test-profile*' -and $_.CommandLine -notlike '*--type=*' }
foreach ($p in $old) {
    Write-Output ("Kill old PID=" + $p.ProcessId)
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 3

# 2. Force developer_mode=true in profile Preferences
$prefsPath = "C:\Users\15866\.cache\math-a11y-ext-test-profile\Default\Preferences"
if (Test-Path $prefsPath) {
    $prefs = Get-Content $prefsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $prefs.extensions) { $prefs | Add-Member -NotePropertyName extensions -NotePropertyValue ([PSCustomObject]@{}) }
    if (-not $prefs.extensions.PSObject.Properties['ui']) { $prefs.extensions | Add-Member -NotePropertyName ui -NotePropertyValue ([PSCustomObject]@{}) }
    $prefs.extensions.ui.developer_mode = $true
    $prefs | ConvertTo-Json -Depth 100 -Compress | Set-Content $prefsPath -Encoding UTF8
    Write-Output "Preferences: developer_mode=true ensured"
}

# 3. Relaunch with same flags
$exe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$chromeArgs = @(
    "--user-data-dir=C:\Users\15866\.cache\math-a11y-ext-test-profile",
    "--remote-debugging-port=9333",
    "--enable-unsafe-extension-debugging",
    "--no-first-run",
    "--no-default-browser-check",
    "about:blank"
)
Start-Process -FilePath $exe -ArgumentList $chromeArgs
Write-Output "Test browser launched"

# 4. Wait for CDP ready
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    try {
        $v = Invoke-RestMethod -Uri "http://127.0.0.1:9333/json/version" -TimeoutSec 2
        Write-Output ("CDP ready: " + $v.Browser)
        exit 0
    } catch { }
}
Write-Output "!! CDP not ready in 20s"
