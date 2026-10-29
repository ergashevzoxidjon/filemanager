@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Bot to'xtatilmoqda...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and ($_.CommandLine -like '*%~dp0run_forever.bat*' -or $_.CommandLine -like '*%~dp0bot.py*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Bot to'xtatildi.
echo.
set /p ANS=Avtomatik ishga tushishni ham o'chiraymi? (h/y):
if /i "%ANS%"=="h" del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\OfisBot.vbs" 2>nul && echo Avtomatik ishga tushish o'chirildi.
pause
