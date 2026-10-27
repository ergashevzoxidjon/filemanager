@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
echo === Bot sinov rejimida ishga tushmoqda ===
echo Telegram'da botga /start yozing. To'xtatish uchun shu oynani yoping.
echo.
python "%~dp0bot.py"
echo.
echo Bot to'xtadi. Xato bo'lsa, yuqoridagi yozuvni o'qing yoki logs\bot.log ni oching.
pause
