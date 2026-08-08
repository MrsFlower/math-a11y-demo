# 查找测试浏览器（9333 端口）的启动命令行
Get-CimInstance Win32_Process -Filter "Name='chrome.exe' OR Name='msedge.exe'" |
    Where-Object { $_.CommandLine -like '*9333*' } |
    Select-Object ProcessId, CommandLine |
    Format-List
