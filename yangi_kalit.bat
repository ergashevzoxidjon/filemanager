@echo off
chcp 65001 >nul
echo Yangi maxfiy kalit (AGENT_KEY yoki webhook_secret uchun):
echo.
python -c "import secrets; print(secrets.token_urlsafe(24))"
echo.
echo Shu satrni nusxalab, config.env va hub config.php ga bir xil qilib yozing.
pause
