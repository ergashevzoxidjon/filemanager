@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === GitHub'ga yuklash ===
git --version >nul 2>&1
if errorlevel 1 goto nogit

if exist .git goto haverepo
git init
git branch -M main
git remote add origin https://github.com/ergashevzoxidjon/filemanager.git
:haverepo

git add -A
echo.
echo Yuklanadigan fayllar:
git status --short
echo.
git commit -m "Fayl-bot: agent, hub va deploy sozlamalari"
git push -u origin main
if errorlevel 1 goto pusherror
echo.
echo Tayyor: https://github.com/ergashevzoxidjon/filemanager
pause
exit /b 0

:nogit
echo XATO: Git topilmadi. git-scm.com dan o'rnating.
pause
exit /b 1

:pusherror
echo.
echo XATO: push bo'lmadi. Yuqoridagi xabarni Claude'ga yuboring.
pause
exit /b 1
