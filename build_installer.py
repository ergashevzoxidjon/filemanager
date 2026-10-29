"""Bitta faylli o'rnatuvchi yaratadi: FileBot_Ornatish.bat

Ishga tushirish: installer_yarat.bat (yoki python build_installer.py)

Natijadagi faylni istalgan Windows kompyuterga tashlab, ikki marta bosiladi. U:
  1) Python bo'lmasa, o'zi yuklab o'rnatadi (administrator huquqi shart emas);
  2) bot kodini %LOCALAPPDATA%\\FileBot ga yozadi va kutubxonalarni o'rnatadi;
  3) kompyuterni hub'da ro'yxatdan o'tkazadi - Telegram'ga «Qabul qilish» tugmasi keladi;
  4) botni yashirin ishga tushiradi va Windows yonganda avtomatik yoqiladigan qiladi.

O'rnatuvchi ichida bot tokeni YO'Q. Unda faqat hub manzili va ro'yxatdan o'tish kodi bor.
Kod bilan ham kompyuter faqat siz Telegram'da qabul qilgandan keyin ishlay boshlaydi.
"""
import base64
import hashlib
import hmac
import io
import json
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE = BASE / "sozlama.json"
OUT = BASE / "FileBot_Ornatish.bat"
AGENT_FILES = ["bot.py", "config.py", "explorer.py", "search.py", "screen.py", "sender.py",
               "shares.py", "hub_client.py", "big_upload.py", "preview.py", "updater.py", "zipper.py", "version.py",
               "requirements.txt"]

BAT_HEADER = r"""@echo off
chcp 65001 >nul
title FileBot - o'rnatish
set "FB_SELF=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t=[IO.File]::ReadAllText($env:FB_SELF,[Text.Encoding]::UTF8); $i=$t.IndexOf('#'+'#PS-START#'+'#'); Invoke-Expression $t.Substring($i)"
echo.
pause
exit /b
"""

# PowerShell qismi alohida faylda turadi
PS_TEMPLATE = BASE / "installer_template.ps1"



def enroll_code(secret: str) -> str:
    return hmac.new(secret.encode(), b"filebot-enroll", hashlib.sha256).hexdigest()[:24]


def build_payload() -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in AGENT_FILES:
            z.write(BASE / name, name)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return "\n".join(b64[i:i + 100] for i in range(0, len(b64), 100))


def hub_supports_register(hub_url: str) -> bool | None:
    req = urllib.request.Request(f"{hub_url}?a=register", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "filebot-build"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
    except Exception:
        return None  # internet yo'q - tekshirib bo'lmadi
    return '"error":"code"' in body


# Umumiy o'rnatuvchi: oyna ochiladi, oxirida konsol kutib qolmaydi
BAT_HEADER_GUI = r"""@echo off
chcp 65001 >nul
title FileBot - o'rnatish
set "FB_SELF=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -STA -Command "$t=[IO.File]::ReadAllText($env:FB_SELF,[Text.Encoding]::UTF8); $i=$t.IndexOf('#'+'#PS-START#'+'#'); Invoke-Expression $t.Substring($i)"
exit /b
"""
GUI_TEMPLATE = BASE / "installer_umumiy.ps1"
GUI_OUT = BASE / "FileBot_Setup.bat"


def build_generic(repo: str = "ergashevzoxidjon/filemanager", out: Path = GUI_OUT) -> Path:
    """Har kim o'z boti bilan o'rnatadigan umumiy o'rnatuvchi (ichida hech qanday maxfiy ma'lumot yo'q)."""
    ps = GUI_TEMPLATE.read_text(encoding="utf-8").replace("__REPO__", repo)
    text = BAT_HEADER_GUI + ps + "\n<#PAYLOAD\n" + build_payload() + "\nPAYLOAD#>\n"
    out.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
    return out


def main() -> None:
    if "--umumiy" in sys.argv:
        out = build_generic()
        print(f"Tayyor: {out}  ({out.stat().st_size // 1024} KB)")
        print("Bu faylni istalgan odamga berish mumkin: ichida token yoki kalit yo'q.")
        return
    if not STATE.exists():
        print("sozlama.json topilmadi. Avval sozlash.bat ni ishga tushiring.")
        sys.exit(1)
    st = json.loads(STATE.read_text(encoding="utf-8"))
    ps = PS_TEMPLATE.read_text(encoding="utf-8").replace("__HUB_URL__", st["hub_url"]).replace("__ENROLL__", enroll_code(st["secret"])).replace("__REPO__", st.get("repo", "ergashevzoxidjon/filemanager"))
    text = BAT_HEADER + ps + "\n<#PAYLOAD\n" + build_payload() + "\nPAYLOAD#>\n"
    OUT.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
    print(f"Tayyor: {OUT}  ({OUT.stat().st_size // 1024} KB)")

    ok = hub_supports_register(st["hub_url"])
    if ok is False:
        print("\nDIQQAT: hostingdagi hub.php eski. Yangi kompyuterlar ulana olmaydi.")
        print("  github_push.bat ni bosing, keyin cPanel -> Git Version Control ->")
        print("  Update from Remote va Deploy HEAD Commit ni bosing.")
    elif ok is None:
        print("\n(Hub'ni tekshirib bo'lmadi - internet yo'qmi?)")
    else:
        print("Hub yangi kompyuterlarni qabul qilishga tayyor.")
    print("\nBu faylni yangi kompyuterga yuboring (Telegram, fleshka) va ikki marta bosing.")
    print("Faylni begonalarga bermang: kompyuter faqat siz Telegram'da qabul qilgandan keyin ulanadi.")


if __name__ == "__main__":
    main()
    if sys.stdin and sys.stdin.isatty():
        input("\nEnter...")
