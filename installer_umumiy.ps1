##PS-START##
# FileBot - umumiy o'rnatuvchi (har kim o'z boti bilan).
# Oynada: bot tokeni, Telegram ID, bot username va kompyuter nomi so'raladi.
# Bot kompyuterdagi barcha disklarni va barcha fayllarni ko'radi (ROOTS=*).
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Repo = '__REPO__'
$Dir = Join-Path $env:LOCALAPPDATA 'FileBot'
$EnvFile = Join-Path $Dir 'config.env'
$Startup = [Environment]::GetFolderPath('Startup')
$Launcher = Join-Path $Startup 'FileBot.vbs'
$Utf8 = New-Object System.Text.UTF8Encoding $false

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

# Qora konsol oynasini yashiramiz - foydalanuvchi faqat chiroyli oynani ko'radi
Add-Type -Name Win -Namespace Native -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
'@
[void][Native.Win]::ShowWindow([Native.Win]::GetConsoleWindow(), 0)

# ─────────────────────────── Ranglar va shriftlar ───────────────────────────
function RGB([int]$r, [int]$g, [int]$b) { [System.Drawing.Color]::FromArgb($r, $g, $b) }
$C_BG      = RGB 248 250 252
$C_CARD    = RGB 255 255 255
$C_PRIMARY = RGB 37 99 235
$C_PRIM2   = RGB 124 58 237
$C_TEXT    = RGB 15 23 42
$C_MUTED   = RGB 100 116 139
$C_BORDER  = RGB 226 232 240
$C_OK      = RGB 22 163 74
$C_ERR     = RGB 220 38 38
$F_TITLE = New-Object System.Drawing.Font('Segoe UI', 20, [System.Drawing.FontStyle]::Bold)
$F_SUB   = New-Object System.Drawing.Font('Segoe UI', 10)
$F_LABEL = New-Object System.Drawing.Font('Segoe UI Semibold', 10)
$F_INPUT = New-Object System.Drawing.Font('Segoe UI', 11)
$F_HINT  = New-Object System.Drawing.Font('Segoe UI', 8.5)
$F_BTN   = New-Object System.Drawing.Font('Segoe UI Semibold', 11)

# ─────────────────────────── Oyna ───────────────────────────
$form = New-Object System.Windows.Forms.Form
$form.Text = 'FileBot - o''rnatish'
$form.ClientSize = New-Object System.Drawing.Size(560, 712)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedSingle'
$form.MaximizeBox = $false
$form.BackColor = $C_BG
$form.Font = $F_SUB

# Sarlavha: ko'kdan binafshaga o'tuvchi yorqin fon
$header = New-Object System.Windows.Forms.Panel
$header.SetBounds(0, 0, 560, 100)
$header.Add_Paint({
    param($s, $e)
    $rect = New-Object System.Drawing.Rectangle(0, 0, $s.Width, $s.Height)
    $brush = New-Object System.Drawing.Drawing2D.LinearGradientBrush($rect, $C_PRIMARY, $C_PRIM2, 20)
    $e.Graphics.FillRectangle($brush, $rect)
    $brush.Dispose()
})
$form.Controls.Add($header)

$logo = New-Object System.Windows.Forms.Label
$logo.Text = [char]::ConvertFromUtf32(0x1F4C2)
$logo.Font = New-Object System.Drawing.Font('Segoe UI Emoji', 30)
$logo.ForeColor = [System.Drawing.Color]::White
$logo.BackColor = [System.Drawing.Color]::Transparent
$logo.SetBounds(26, 18, 70, 64)
$header.Controls.Add($logo)

$title = New-Object System.Windows.Forms.Label
$title.Text = 'FileBot'
$title.Font = $F_TITLE
$title.ForeColor = [System.Drawing.Color]::White
$title.BackColor = [System.Drawing.Color]::Transparent
$title.SetBounds(100, 16, 420, 40)
$header.Controls.Add($title)

$sub = New-Object System.Windows.Forms.Label
$sub.Text = 'Kompyuterdagi fayllarni telefondan, Telegram orqali boshqaring'
$sub.Font = $F_SUB
$sub.ForeColor = RGB 224 231 255
$sub.BackColor = [System.Drawing.Color]::Transparent
$sub.SetBounds(102, 58, 440, 24)
$header.Controls.Add($sub)

# Oq kartochka
$card = New-Object System.Windows.Forms.Panel
$card.SetBounds(20, 112, 520, 528)
$card.BackColor = $C_CARD
$card.Add_Paint({
    param($s, $e)
    $pen = New-Object System.Drawing.Pen($C_BORDER)
    $e.Graphics.DrawRectangle($pen, 0, 0, $s.Width - 1, $s.Height - 1)
    $pen.Dispose()
})
$form.Controls.Add($card)

$script:y = 18
function Add-Field([string]$label, [string]$hint, [string]$linkText, [string]$linkUrl) {
    $l = New-Object System.Windows.Forms.Label
    $l.Text = $label; $l.Font = $F_LABEL; $l.ForeColor = $C_TEXT
    $l.SetBounds(22, $script:y, 300, 22)
    $card.Controls.Add($l)
    if ($linkText) {
        $lk = New-Object System.Windows.Forms.LinkLabel
        $lk.Text = $linkText; $lk.Font = $F_HINT; $lk.LinkColor = $C_PRIMARY
        $lk.TextAlign = 'MiddleRight'
        $lk.SetBounds(300, $script:y + 2, 198, 20)
        $url = $linkUrl
        $lk.Add_LinkClicked({ Start-Process $url }.GetNewClosure())
        $card.Controls.Add($lk)
    }
    $t = New-Object System.Windows.Forms.TextBox
    $t.Font = $F_INPUT; $t.BorderStyle = 'FixedSingle'; $t.BackColor = RGB 248 250 252
    $t.SetBounds(22, $script:y + 24, 476, 28)
    $card.Controls.Add($t)
    $h = New-Object System.Windows.Forms.Label
    $h.Text = $hint; $h.Font = $F_HINT; $h.ForeColor = $C_MUTED
    $h.SetBounds(22, $script:y + 56, 476, 18)
    $card.Controls.Add($h)
    $script:y += 78
    return @{ Box = $t; Hint = $h; Default = $hint }
}

$fToken = Add-Field 'Bot tokeni' 'Masalan: 1234567890:AAH...  (@BotFather -> /newbot)' '@BotFather ni ochish' 'https://t.me/BotFather'
$fUser  = Add-Field 'Bot username' 'Masalan: @mening_fayl_bot' '' ''
$fId    = Add-Field 'Sizning Telegram ID raqamingiz' 'Faqat raqam. Bir nechta bo''lsa vergul bilan' '@userinfobot ni ochish' 'https://t.me/userinfobot'
$fName  = Add-Field 'Kompyuter nomi' 'Telefonda shu nom bilan ko''rinadi' '' ''
$fName.Box.Text = $env:COMPUTERNAME

# 2 GB gacha fayllar uchun (ixtiyoriy): my.telegram.org dagi api_id va api_hash
$al = New-Object System.Windows.Forms.Label
$al.Text = '2 GB gacha fayllar (ixtiyoriy)'; $al.Font = $F_LABEL; $al.ForeColor = $C_TEXT
$al.SetBounds(22, $script:y, 280, 22)
$card.Controls.Add($al)
$alk = New-Object System.Windows.Forms.LinkLabel
$alk.Text = 'my.telegram.org ni ochish'; $alk.Font = $F_HINT; $alk.LinkColor = $C_PRIMARY
$alk.TextAlign = 'MiddleRight'; $alk.SetBounds(300, $script:y + 2, 198, 20)
$alk.Add_LinkClicked({ Start-Process 'https://my.telegram.org/apps' })
$card.Controls.Add($alk)
$apiId = New-Object System.Windows.Forms.TextBox
$apiId.Font = $F_INPUT; $apiId.BorderStyle = 'FixedSingle'; $apiId.BackColor = RGB 248 250 252
$apiId.SetBounds(22, $script:y + 24, 130, 28)
$card.Controls.Add($apiId)
$apiHash = New-Object System.Windows.Forms.TextBox
$apiHash.Font = $F_INPUT; $apiHash.BorderStyle = 'FixedSingle'; $apiHash.BackColor = RGB 248 250 252
$apiHash.SetBounds(160, $script:y + 24, 338, 28)
$card.Controls.Add($apiHash)
$apiHint = New-Object System.Windows.Forms.Label
$apiHint.Text = 'api_id va api_hash. Bo''sh qolsa: 49 MB dan kattasi bo''laklarda keladi (keyin /kattafayl)'
$apiHint.Font = $F_HINT; $apiHint.ForeColor = $C_MUTED
$apiHint.SetBounds(22, $script:y + 56, 476, 18)
$card.Controls.Add($apiHint)
$script:y += 78

# Ma'lumot: bot barcha disklarni ko'radi
$info = New-Object System.Windows.Forms.Label
$info.Text = [char]::ConvertFromUtf32(0x1F4BD) + '  Bot kompyuterdagi barcha disklar va papkalarni ko''radi (keyin ulangan fleshkalar ham).'
$info.Font = $F_HINT; $info.ForeColor = $C_PRIMARY; $info.BackColor = RGB 239 246 255
$info.TextAlign = 'MiddleLeft'; $info.Padding = New-Object System.Windows.Forms.Padding(8, 0, 0, 0)
$info.SetBounds(22, $script:y, 476, 34)
$card.Controls.Add($info)
$script:y += 48

$status = New-Object System.Windows.Forms.Label
$status.Font = $F_SUB; $status.ForeColor = $C_MUTED
$status.SetBounds(22, $script:y, 476, 44)
$status.Text = 'Avval Telegram''da botingizga kirib /start ni bosing.'
$card.Controls.Add($status)

$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Style = 'Marquee'; $bar.MarqueeAnimationSpeed = 30; $bar.Visible = $false
$bar.SetBounds(22, $script:y + 46, 476, 8)
$card.Controls.Add($bar)

$btn = New-Object System.Windows.Forms.Button
$btn.Text = 'O''rnatish'
$btn.Font = $F_BTN
$btn.FlatStyle = 'Flat'; $btn.FlatAppearance.BorderSize = 0
$btn.BackColor = $C_PRIMARY; $btn.ForeColor = [System.Drawing.Color]::White
$btn.Cursor = [System.Windows.Forms.Cursors]::Hand
$btn.SetBounds(300, 652, 240, 48)
$form.Controls.Add($btn)

$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Bekor qilish'
$cancel.Font = $F_BTN
$cancel.FlatStyle = 'Flat'; $cancel.FlatAppearance.BorderColor = $C_BORDER
$cancel.BackColor = $C_CARD; $cancel.ForeColor = $C_MUTED
$cancel.SetBounds(20, 652, 160, 48)
$cancel.Add_Click({ $form.Close() })
$form.Controls.Add($cancel)
$form.AcceptButton = $btn

# Oldin o'rnatilgan bo'lsa - qiymatlarni to'ldirib qo'yamiz (qayta sozlash / yangilash)
if (Test-Path $EnvFile) {
    foreach ($line in Get-Content $EnvFile -Encoding UTF8) {
        if ($line -match '^BOT_TOKEN=(.+)$') { $fToken.Box.Text = $Matches[1].Trim() }
        elseif ($line -match '^ALLOWED_USERS=(.+)$') { $fId.Box.Text = $Matches[1].Trim() }
        elseif ($line -match '^BOT_USERNAME=(.+)$') { $fUser.Box.Text = '@' + $Matches[1].Trim() }
        elseif ($line -match '^AGENT_NAME=(.+)$') { $fName.Box.Text = $Matches[1].Trim() }
        elseif ($line -match '^API_ID=(\d+)$') { $apiId.Text = $Matches[1] }
        elseif ($line -match '^API_HASH=([0-9a-fA-F]{32})$') { $apiHash.Text = $Matches[1] }
    }
    $status.Text = 'Avvalgi sozlamalar topildi. Tekshirib, «O''rnatish» ni bosing - bot yangilanadi.'
}

# ─────────────────────────── Yordamchilar ───────────────────────────
function Pump { [System.Windows.Forms.Application]::DoEvents() }
function Show-Status([string]$text, $color = $null) {
    $status.Text = $text
    if ($color) { $status.ForeColor = $color } else { $status.ForeColor = $C_MUTED }
    Pump
}
function Mark-Field($f, [string]$err) {
    if ($err) { $f.Hint.Text = $err; $f.Hint.ForeColor = $C_ERR; $f.Box.BackColor = RGB 254 242 242 }
    else { $f.Hint.Text = $f.Default; $f.Hint.ForeColor = $C_MUTED; $f.Box.BackColor = RGB 248 250 252 }
}
function Wait-Proc($p) { while (-not $p.HasExited) { Pump; Start-Sleep -Milliseconds 100 } }
function Download([string]$url, [string]$out) {
    $wc = New-Object System.Net.WebClient
    $wc.Headers.Add('User-Agent', 'FileBot-installer')
    $task = $wc.DownloadFileTaskAsync($url, $out)
    while (-not $task.IsCompleted) { Pump; Start-Sleep -Milliseconds 100 }
    if ($task.IsFaulted) { throw $task.Exception.InnerException }
}
function Tg([string]$token, [string]$method, $body = $null) {
    $url = "https://api.telegram.org/bot$token/$method"
    try {
        if ($body) {
            $json = $body | ConvertTo-Json -Compress
            return Invoke-RestMethod -Method Post -Uri $url -ContentType 'application/json; charset=utf-8' -Body $Utf8.GetBytes($json) -TimeoutSec 20
        }
        return Invoke-RestMethod -Uri $url -TimeoutSec 20
    } catch {
        $resp = $_.Exception.Response
        if ($resp) {
            try {
                $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
                return ($reader.ReadToEnd() | ConvertFrom-Json)
            } catch { }
        }
        throw
    }
}

# ─────────────────────────── 1. Tekshirish ───────────────────────────
function Validate {
    $ok = $true
    $token = $fToken.Box.Text.Trim()
    $user = $fUser.Box.Text.Trim().TrimStart('@')
    $ids = $fId.Box.Text.Trim()
    $name = $fName.Box.Text.Trim()
    if ($token -notmatch '^\d{5,}:[A-Za-z0-9_-]{30,}$') { Mark-Field $fToken 'Token noto''g''ri. @BotFather bergan to''liq tokenni kiriting'; $ok = $false } else { Mark-Field $fToken '' }
    if ($user -notmatch '^[A-Za-z][A-Za-z0-9_]{3,31}$') { Mark-Field $fUser 'Username noto''g''ri (masalan: @mening_fayl_bot)'; $ok = $false } else { Mark-Field $fUser '' }
    if ($ids -notmatch '^\d{4,}(\s*,\s*\d{4,})*$') { Mark-Field $fId 'Faqat raqam kiriting (masalan: 1462539043)'; $ok = $false } else { Mark-Field $fId '' }
    if (-not $name) { Mark-Field $fName 'Kompyuter nomini kiriting'; $ok = $false } else { Mark-Field $fName '' }
    $aid = $apiId.Text.Trim(); $ahash = $apiHash.Text.Trim().ToLower()
    $apiHint.ForeColor = $C_MUTED
    if ($aid -or $ahash) {
        if ($aid -notmatch '^\d{3,12}$' -or $ahash -notmatch '^[0-9a-f]{32}$') {
            $apiHint.Text = 'api_id - faqat raqam, api_hash - 32 belgi (0-9, a-f). Yoki ikkalasini bo''sh qoldiring'
            $apiHint.ForeColor = $C_ERR; $ok = $false
        }
    }
    if (-not $ok) { return $null }

    Show-Status 'Bot tekshirilmoqda...'
    try { $me = Tg $token 'getMe' } catch { Show-Status "Telegram'ga ulanib bo'lmadi. Internetni tekshiring." $C_ERR; return $null }
    if (-not $me.ok) { Mark-Field $fToken 'Telegram bu tokenni qabul qilmadi. @BotFather dan qayta oling'; Show-Status 'Token noto''g''ri.' $C_ERR; return $null }
    if ($me.result.username -ne $user) {
        Mark-Field $fUser "Bu token @$($me.result.username) botiga tegishli"
        Show-Status 'Token va username bir-biriga mos emas.' $C_ERR
        return $null
    }
    $idList = @($ids -split '\s*,\s*')
    foreach ($id in $idList) {
        $r = Tg $token 'sendMessage' @{ chat_id = [int64]$id; text = "FileBot: $name kompyuteriga o'rnatilmoqda..." }
        if (-not $r.ok) {
            Mark-Field $fId "ID $id ga xabar yuborib bo'lmadi"
            Show-Status "Avval Telegram'da @$user ga kirib /start ni bosing, so'ng qayta urinib ko'ring." $C_ERR
            Start-Process "https://t.me/$user"
            return $null
        }
    }
    $wh = Tg $token 'getWebhookInfo'
    if ($wh.ok -and $wh.result.url) {
        $ans = [System.Windows.Forms.MessageBox]::Show(
            "Bu bot boshqa tizimga ulangan (webhook):`n$($wh.result.url)`n`nUni uzib, FileBot'ga ulaymizmi?",
            'FileBot', 'YesNo', 'Question')
        if ($ans -ne 'Yes') { Show-Status 'Bekor qilindi: bot boshqa tizimga ulangan.' $C_ERR; return $null }
        [void](Tg $token 'deleteWebhook')
    }
    return @{ Token = $token; User = $user; Ids = ($idList -join ','); Name = $name; ApiId = $aid; ApiHash = $ahash }
}

# ─────────────────────────── 2. O'rnatish ───────────────────────────
function Install($v) {
    Show-Status 'Eski nusxa to''xtatilmoqda...'
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -and $_.CommandLine.Contains($Dir) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null

    # a) Tayyor FileBot.exe (Python kerak emas)
    $exeOk = $false
    Show-Status 'FileBot yuklab olinmoqda...'
    try {
        $rel = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ 'User-Agent' = 'FileBot-installer' } -TimeoutSec 20
        $asset = $rel.assets | Where-Object { $_.name -eq 'FileBot.exe' } | Select-Object -First 1
        if ($asset) {
            $tmpExe = Join-Path $Dir 'FileBot.exe.download'
            Download $asset.browser_download_url $tmpExe
            if ($asset.digest -and $asset.digest.StartsWith('sha256:')) {
                $hash = (Get-FileHash -Algorithm SHA256 $tmpExe).Hash.ToLower()
                if ($hash -ne $asset.digest.Substring(7).ToLower()) { Remove-Item $tmpExe; throw 'sha256 mos kelmadi' }
            }
            Move-Item -Force $tmpExe (Join-Path $Dir 'FileBot.exe')
            $exeOk = $true
        }
    } catch { }

    # b) Zaxira yo'l: Python + shu fayl ichidagi bot kodi
    if (-not $exeOk) {
        Show-Status 'Python tekshirilmoqda...'
        $py = $null
        $probe = 'import sys; v=sys.version_info[:2]; print(sys.executable if (3,10)<=v<=(3,13) else 0)'
        foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe|", 'py|-3.12', 'py|-3.13', 'py|-3.11', 'python|')) {
            try {
                $exe, $arg = $c.Split('|'); $pre = @(); if ($arg) { $pre = @($arg) }
                if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
                $out = (& $exe @pre -c $probe 2>$null | Select-Object -Last 1)
                if ($out -and (Test-Path $out)) { $py = $out.Trim(); break }
            } catch { }
        }
        if (-not $py) {
            Show-Status 'Python yuklab olinmoqda (25 MB)...'
            $setup = Join-Path $env:TEMP 'python-3.12.7-amd64.exe'
            Download 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' $setup
            Show-Status 'Python o''rnatilmoqda (1-2 daqiqa)...'
            $p = Start-Process -FilePath $setup -PassThru -ArgumentList '/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0 Include_tcltk=0 Shortcuts=0'
            Wait-Proc $p
            $py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
            if (-not (Test-Path $py)) { throw 'Python o''rnatilmadi' }
            Remove-Item $setup -ErrorAction SilentlyContinue
        }
        Show-Status 'Bot fayllari yozilmoqda...'
        $self = [IO.File]::ReadAllText($env:FB_SELF, [Text.Encoding]::UTF8)
        $mk = 'PAY' + 'LOAD'
        $m = [regex]::Match($self, "(?s)<#$mk\s*([A-Za-z0-9+/=\s]+?)\s*$mk#>")
        if (-not $m.Success) { throw 'O''rnatuvchi fayli buzilgan' }
        $zip = Join-Path $env:TEMP 'filebot_payload.zip'
        [IO.File]::WriteAllBytes($zip, [Convert]::FromBase64String(($m.Groups[1].Value -replace '\s', '')))
        Expand-Archive -Path $zip -DestinationPath $Dir -Force
        Remove-Item $zip -ErrorAction SilentlyContinue
        $vpy = Join-Path $Dir 'venv\Scripts\python.exe'
        if (-not (Test-Path $vpy)) {
            Show-Status 'Python muhiti yaratilmoqda...'
            Wait-Proc (Start-Process -FilePath $py -ArgumentList @('-m', 'venv', "`"$(Join-Path $Dir 'venv')`"") -PassThru -WindowStyle Hidden)
        }
        foreach ($req in (Get-Content (Join-Path $Dir 'requirements.txt') | Where-Object { $_.Trim() })) {
            Show-Status "Kutubxona o'rnatilmoqda: $req"
            Wait-Proc (Start-Process -FilePath $vpy -ArgumentList @('-m', 'pip', 'install', '-q', '--disable-pip-version-check', "`"$req`"") -PassThru -WindowStyle Hidden)
        }
    }

    Show-Status 'Sozlamalar saqlanmoqda...'
    $cfg = @(
        '# FileBot o''rnatuvchisi yaratgan',
        "BOT_TOKEN=$($v.Token)",
        "BOT_USERNAME=$($v.User)",
        "ALLOWED_USERS=$($v.Ids)",
        "AGENT_NAME=$($v.Name)",
        'ROOTS=*',
        'NOTIFY_START=1',
        'MAX_FILE_MB=0'
    )
    if ($v.ApiId) { $cfg += @("API_ID=$($v.ApiId)", "API_HASH=$($v.ApiHash)") }
    $cfg = $cfg -join "`r`n"
    [IO.File]::WriteAllText($EnvFile, $cfg + "`r`n", $Utf8)

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
echo O'chirildi.
pause
cd /d "%TEMP%"
rd /s /q "%~dp0"
'@
    [IO.File]::WriteAllText((Join-Path $Dir "o'chirish.bat"), $uninst.Replace("`n", "`r`n").Replace("`r`r", "`r"))

    Show-Status 'Bot ishga tushirilmoqda...'
    $vbs = 'CreateObject("WScript.Shell").Run """' + (Join-Path $Dir 'run.bat') + '""", 0, False'
    [IO.File]::WriteAllText($Launcher, $vbs, [Text.Encoding]::Default)
    Start-Process -FilePath 'wscript.exe' -ArgumentList ('"' + $Launcher + '"')
}

# ─────────────────────────── Tugma ───────────────────────────
$script:done = $false
$btn.Add_Click({
    if ($script:done) {
        Start-Process "https://t.me/$($fUser.Box.Text.Trim().TrimStart('@'))"
        $form.Close()
        return
    }
    $btn.Enabled = $false; $cancel.Enabled = $false
    $bar.Visible = $true
    try {
        $v = Validate
        if ($v) {
            foreach ($c in $card.Controls) { if ($c -is [System.Windows.Forms.TextBox] -or $c -is [System.Windows.Forms.CheckBox]) { $c.Enabled = $false } }
            Install $v
            $script:done = $true
            Show-Status "Tayyor! Bot ishga tushdi. Telegram'da @$($v.User) ga kiring - u sizga xabar yuboradi." $C_OK
            $btn.Text = 'Botni ochish'
            $btn.BackColor = $C_OK
            $cancel.Text = 'Yopish'
        }
    } catch {
        Show-Status "Xato: $($_.Exception.Message)" $C_ERR
    } finally {
        $bar.Visible = $false
        $btn.Enabled = $true; $cancel.Enabled = $true
    }
})

[void]$form.ShowDialog()
exit 0
