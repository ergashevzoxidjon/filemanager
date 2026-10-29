@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LAUNCHER=%STARTUP%\OfisBot.vbs"

rem Windows yonganda botni yashirin oynada ishga tushiradigan fayl
> "%LAUNCHER%" echo CreateObject("WScript.Shell").Run """%~dp0run_forever.bat""", 0, False

echo Avtomatik ishga tushish yoqildi.
echo Endi kompyuter yonganda bot o'zi ishga tushadi.
echo.
echo Bot hozir yashirin rejimda ishga tushirilmoqda...
wscript "%LAUNCHER%"
echo Tayyor. Telegram'ga "bot ishga tushdi" xabari kelishi kerak.
pause
