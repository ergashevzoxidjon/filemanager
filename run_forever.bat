@echo off
rem Botni doim ishlatib turadi: xatodan to'xtasa, 15 sekunddan keyin qayta yoqadi.
rem Bu faylni qo'lda ochish shart emas - 3_autostart_yoqish.bat uni yashirin ishga tushiradi.
cd /d "%~dp0"
set PYTHONUTF8=1
:loop
python "%~dp0bot.py"
rem 2 = sozlama xatosi, 3 = bot allaqachon ishlayapti -> qayta urinmaymiz
if errorlevel 2 goto end
timeout /t 15 /nobreak >nul
goto loop
:end
