@echo off
rem Botni doim ishlatib turadi: xatodan to'xtasa, 15 sekunddan keyin qayta yoqadi.
rem Bu faylni qo'lda ochish shart emas - 3_autostart_yoqish.bat uni yashirin ishga tushiradi.
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist logs mkdir logs
python -c "import aiogram, mss, dotenv, telethon" >nul 2>&1 || call :deps
:loop
rem Python xatolari (masalan kutubxona yetishmasa) logs\crash.log ga yoziladi
python "%~dp0bot.py" >nul 2>> logs\crash.log
rem 4 = yangilandi -> kutubxonalarni tekshirib, darhol qayta yoqamiz
if errorlevel 4 goto updated
rem 2 = sozlama xatosi, 3 = bot allaqachon ishlayapti -> qayta urinmaymiz
if errorlevel 2 goto end
timeout /t 15 /nobreak >nul
goto loop
:updated
call :deps
goto loop
:end
exit /b

:deps
rem Har bir kutubxona alohida o'rnatiladi: bittasi o'rnatilmasa ham qolganlari o'rnatilsin
for /f "usebackq delims=" %%r in ("requirements.txt") do python -m pip install --disable-pip-version-check "%%r" >> logs\pip.log 2>&1
exit /b
