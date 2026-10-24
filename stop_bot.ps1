$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
    Where-Object { $_.CommandLine -like '*bot.py*' }

if (-not $procs) {
    Write-Output 'Бот не запущен.'
    exit
}

foreach ($p in $procs) {
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Output ('Остановлен PID ' + $p.ProcessId)
}
