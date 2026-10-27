@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Ofis fayl-bot: o'rnatish ===
echo.

python --version >nul 2>&1
if errorlevel 1 goto nopython

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto piperror

if not exist config.env copy config.example.env config.env >nul

echo.
echo Tayyor. Hozir config.env ochiladi - token va ID'ingizni yozib, saqlang.
echo Keyin 2_test.bat ni ishga tushiring.
notepad config.env
pause
exit /b 0

:nopython
echo XATO: Python topilmadi.
echo python.org dan Python 3.12 ni o'rnating va "Add Python to PATH" belgisini qo'ying.
pause
exit /b 1

:piperror
echo XATO: kutubxonalar o'rnatilmadi. Internetni tekshiring va qayta urinib ko'ring.
pause
exit /b 1
