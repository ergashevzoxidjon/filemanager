##PS-START##
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$HubUrl = '__HUB_URL__'
$Repo = '__REPO__'
$Enroll = '__ENROLL__'
$Dir = Join-Path $env:LOCALAPPDATA 'FileBot'
$Startup = [Environment]::GetFolderPath('Startup')
$Launcher = Join-Path $Startup 'FileBot.vbs'
$Utf8 = New-Object System.Text.UTF8Encoding $false

function Say([string]$m, [string]$c = 'Gray') { Write-Host $m -ForegroundColor $c }
function Step([string]$m) { Write-Host ''; Write-Host ">> $m" -ForegroundColor Cyan }
function Fail([string]$m) { Write-Host ''; Write-Host "XATO: $m" -ForegroundColor Red; exit 1 }

Say '==========================================' Cyan
Say '   FileBot - kompyuterni telefondan boshqarish' Cyan
Say '==========================================' Cyan

# ---------- 0. Eski nusxani to'xtatish ----------
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.Contains($Dir) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

# ---------- 1. Tayyor FileBot.exe (Python kerak emas) ----------
$ExeOk = $false
Step 'FileBot.exe yuklab olinmoqda (GitHub)'
try {
    $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ 'User-Agent' = 'FileBot-installer' }
    $asset = $rel.assets | Where-Object { $_.name -eq 'FileBot.exe' } | Select-Object -First 1
    if ($asset) {
        New-Item -ItemType Directory -Force -Path $Dir | Out-Null
        $tmpExe = Join-Path $Dir 'FileBot.exe.download'
        Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $tmpExe
        if ($asset.digest -and $asset.digest.StartsWith('sha256:')) {
            $hash = (Get-FileHash -Algorithm SHA256 $tmpExe).Hash.ToLower()
            if ($hash -ne $asset.digest.Substring(7).ToLower()) { Remove-Item $tmpExe; throw 'sha256 mos kelmadi' }
        }
        Move-Item -Force $tmpExe (Join-Path $Dir 'FileBot.exe')
        $ExeOk = $true
        Say "FileBot $($rel.tag_name) yuklandi" Green
    } else { Say "Release'da FileBot.exe topilmadi - Python rejimiga o'tiladi" Yellow }
} catch { Say "FileBot.exe yuklab olinmadi ($($_.Exception.Message)) - Python rejimiga o'tiladi" Yellow }

if (-not $ExeOk) {
# ---------- 1b. Python (zaxira yo'l) ----------
Step 'Python tekshirilmoqda'
$Py = $null
$probe = 'import sys; v=sys.version_info[:2]; print(sys.executable if (3,10)<=v<=(3,13) else 0)'
$cands = @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe|", 'py|-3.12', 'py|-3.13', 'py|-3.11', 'python|')
foreach ($c in $cands) {
    try {
        $exe, $arg = $c.Split('|'); $pre = @(); if ($arg) { $pre = @($arg) }
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $out = (& $exe @pre -c $probe 2>$null | Select-Object -Last 1)
        if ($out -and (Test-Path $out)) { $Py = $out.Trim(); break }
    } catch { }
}
if (-not $Py) {
    Say 'Python topilmadi - yuklab olinmoqda (taxminan 25 MB)...'
    $setup = Join-Path $env:TEMP 'python-3.12.7-amd64.exe'
    try {
        Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile $setup
    } catch { Fail "Python yuklab olinmadi. Internetni tekshiring. ($($_.Exception.Message))" }
    Say "Python o'rnatilmoqda (1-2 daqiqa)..."
    $p = Start-Process -FilePath $setup -Wait -PassThru -ArgumentList '/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0 Include_tcltk=0 Shortcuts=0'
    $Py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    if (-not (Test-Path $Py)) { Fail "Python o'rnatilmadi (kod $($p.ExitCode))." }
    Remove-Item $setup -ErrorAction SilentlyContinue
}
Say "Python: $Py" DarkGray

# ---------- 3. Bot kodi ----------
Step "Bot fayllari yozilmoqda: $Dir"
$self = [IO.File]::ReadAllText($env:FB_SELF, [Text.Encoding]::UTF8)
$mk = 'PAY' + 'LOAD'
$m = [regex]::Match($self, "(?s)<#$mk\s*([A-Za-z0-9+/=\s]+?)\s*$mk#>")
if (-not $m.Success) { Fail "O'rnatuvchi fayli buzilgan. Uni qaytadan yuklab oling." }
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$zip = Join-Path $env:TEMP 'filebot_payload.zip'
[IO.File]::WriteAllBytes($zip, [Convert]::FromBase64String(($m.Groups[1].Value -replace '\s', '')))
Expand-Archive -Path $zip -DestinationPath $Dir -Force
Remove-Item $zip -ErrorAction SilentlyContinue

# ---------- 4. Kutubxonalar ----------
Step "Kutubxonalar o'rnatilmoqda (birinchi safar 1-3 daqiqa)"
$VPy = Join-Path $Dir 'venv\Scripts\python.exe'
if (-not (Test-Path $VPy)) {
    & $Py -m venv (Join-Path $Dir 'venv')
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VPy)) { Fail 'Python muhiti yaratilmadi.' }
}
foreach ($req in (Get-Content (Join-Path $Dir 'requirements.txt') | Where-Object { $_.Trim() })) {
    & $VPy -m pip install --disable-pip-version-check -q $req
    if ($LASTEXITCODE -ne 0) {
        if ($req -match '^(aiogram|python-dotenv)') { Fail "$req o'rnatilmadi. Internetni tekshirib, qayta urinib ko'ring." }
        Say "  $req o'rnatilmadi - bu imkoniyat o'chiq bo'ladi, bot baribir ishlaydi." Yellow
    }
}

}  # Python rejimi tugadi

# ---------- 5. Ro'yxatdan o'tish ----------
$EnvFile = Join-Path $Dir 'config.env'
$existing = (Test-Path $EnvFile) -and ((Get-Content $EnvFile -Raw) -match 'AGENT_KEY=\S{16,}')
if ($existing) {
    Step "Avvalgi sozlamalar saqlandi (yangilash rejimi)"
} else {
    Step "Kompyuterni ro'yxatdan o'tkazish"
    $name = Read-Host "Telefonda ko'rinadigan nom [$env:COMPUTERNAME]"
    if (-not $name) { $name = $env:COMPUTERNAME }

    $roots = '*'  # barcha disklar va barcha fayllar

    $body = @{ code = $Enroll; name = $name; host = $env:COMPUTERNAME } | ConvertTo-Json -Compress
    try {
        $r = Invoke-RestMethod -Method Post -Uri "$HubUrl`?a=register" -ContentType 'application/json; charset=utf-8' -Body $Utf8.GetBytes($body)
    } catch { Fail "Hub'ga ulanib bo'lmadi yoki o'rnatuvchi eskirgan. ($($_.Exception.Message))" }
    if (-not $r.ok) { Fail "Hub ro'yxatdan o'tkazmadi: $($r.error)" }

    $cfg = @(
        '# FileBot o''rnatuvchisi yaratgan',
        "HUB_URL=$HubUrl",
        "AGENT_ID=$($r.agent)",
        "AGENT_KEY=$($r.key)",
        "AGENT_NAME=$name",
        "ROOTS=$roots",
        'NOTIFY_START=1'
    ) -join "`r`n"
    [IO.File]::WriteAllText($EnvFile, $cfg + "`r`n", $Utf8)

    Write-Host ''
    Say '------------------------------------------' Yellow
    Say " Telegram'ga xabar keldi: 'Yangi kompyuter ulanmoqchi'." Yellow
    Say " Telefonda 'Qabul qilish' tugmasini bosing." Yellow
    Say '------------------------------------------' Yellow
    $ok = $false
    for ($i = 0; $i -lt 120 -and -not $ok; $i++) {
        Start-Sleep -Seconds 5
        try {
            $b = Invoke-RestMethod -Uri "$HubUrl`?a=bootstrap&agent=$($r.agent)" -Headers @{ 'X-Agent-Key' = $r.key }
            if ($b.ok) { $ok = $true }
        } catch { Write-Host '.' -NoNewline }
    }
    Write-Host ''
    if ($ok) { Say 'Qabul qilindi!' Green }
    else { Say "Hali qabul qilinmadi. Bot ishga tushadi va tasdiqni o'zi kutib turadi." Yellow }
}

# ---------- 6. Ishga tushirish ----------
Step 'Avtomatik ishga tushish sozlanmoqda'
$run = @'
@echo off
rem FileBot ni doim ishlatib turadi. 4 = yangilandi (darhol qayta yoqiladi), 2/3 = to'xtash.
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist logs mkdir logs
:loop
if exist "%~dp0FileBot.exe" (
    "%~dp0FileBot.exe" 2>> logs\crash.log
) else (
    "%~dp0venv\Scripts\python.exe" "%~dp0bot.py" >nul 2>> logs\crash.log
)
if errorlevel 4 goto updated
if errorlevel 2 goto end
timeout /t 15 /nobreak >nul
goto loop
:updated
if not exist "%~dp0FileBot.exe" "%~dp0venv\Scripts\python.exe" -m pip install -q -r requirements.txt >> logs\pip.log 2>&1
goto loop
:end
'@
[IO.File]::WriteAllText((Join-Path $Dir 'run.bat'), $run.Replace("`n", "`r`n").Replace("`r`r", "`r"))

$uninst = @'
@echo off
chcp 65001 >nul
echo FileBot shu kompyuterdan o'chiriladi.
set /p ANS=Davom etamizmi? (h/y):
if /i not "%ANS%"=="h" exit /b
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.Contains('%~dp0'.TrimEnd('\')) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\FileBot.vbs" 2>nul
echo O'chirildi. Telefonda kompyuterni ro'yxatdan olib tashlash uchun: Kompyuter - savatcha tugmasi.
pause
cd /d "%TEMP%"
rd /s /q "%~dp0"
'@
[IO.File]::WriteAllText((Join-Path $Dir "o'chirish.bat"), $uninst.Replace("`n", "`r`n").Replace("`r`r", "`r"))

$vbs = 'CreateObject("WScript.Shell").Run """' + (Join-Path $Dir 'run.bat') + '""", 0, False'
[IO.File]::WriteAllText($Launcher, $vbs, [Text.Encoding]::Default)
Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + $Launcher + '"')

Write-Host ''
Say '==========================================' Green
Say ' TAYYOR! Bot yashirin rejimda ishlayapti.' Green
Say " Telegram'da botga kiring va 'Kompyuter' tugmasini bosing." Green
Say " Fayllar: $Dir" Green
Say " O'chirish uchun: shu papkadagi o'chirish.bat" Green
Say '==========================================' Green
exit 0
