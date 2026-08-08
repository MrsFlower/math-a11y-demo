# Relaunch test browser. Extension is persisted in profile (UI-loaded),
# no --load-extension needed (flag is ignored on Chrome 137+ anyway).

# 1. Graceful close via CDP
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:9333/json/close/notarget" -TimeoutSec 1 -ErrorAction SilentlyContinue | Out-Null
} catch { }
$ws = $null
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:9333/json/version" -TimeoutSec 2 | Out-Null
    $browserOpen = $true
} catch {
    $browserOpen = $false
}
if ($browserOpen) {
    Write-Output "Closing browser via Browser.close ..."
    $py = @"
import json, urllib.request, websockets, asyncio
async def m():
    ws = json.load(urllib.request.urlopen('http://127.0.0.1:9333/json/version'))['webSocketDebuggerUrl']
    async with websockets.connect(ws, origin=None) as w:
        await w.send(json.dumps({'id':1,'method':'Browser.close'}))
asyncio.run(m())
print('close sent')
"@
    $py | python -
    Start-Sleep -Seconds 4
}

# 2. Verify port free
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:9333/json/version" -TimeoutSec 2 | Out-Null
    Write-Output "!! port 9333 still occupied"
    exit 1
} catch { }

# 3. Relaunch (extension auto-loads from profile)
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
