"""Bir martalik sozlash: config.env va hub/config.php ni yaratadi, so'ng hub'ni ishga tushiradi.

Ishga tushirish: sozlash.bat (yoki python sozlash.py)
Kalitlar shu yerda avtomatik yaratiladi. Token faqat sizning kompyuteringizdagi fayllarga yoziladi.
"""
import json
import re
import secrets
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATE = BASE / "sozlama.json"          # .gitignore da bor - GitHub'ga chiqmaydi
CONFIG_PHP = BASE / "hub" / "config.php"
CONFIG_ENV = BASE / "config.env"


def ask(prompt: str, default: str = "", check=None) -> str:
    while True:
        hint = f" [{default}]" if default else ""
        value = input(f"{prompt}{hint}: ").strip() or default
        if not value:
            print("  Bo'sh bo'lmasin.")
            continue
        if check and not check(value):
            continue
        return value


def check_token(v: str) -> bool:
    if re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{30,}", v):
        return True
    print("  Token ko'rinishi: 123456789:AAH... (BotFather beradi)")
    return False


def check_ids(v: str) -> bool:
    if re.fullmatch(r"\d+(\s*,\s*\d+)*", v):
        return True
    print("  Faqat raqamlar, bir nechta bo'lsa vergul bilan")
    return False


def check_agent(v: str) -> bool:
    if re.fullmatch(r"[a-z0-9]{1,10}", v):
        return True
    print("  1-10 ta kichik lotin harf yoki raqam (masalan: ofis, uy, sklad)")
    return False


def php_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def write_config_php(st: dict) -> None:
    agents = "\n".join(
        f"        {php_str(a)} => ['name' => {php_str(v['name'])}, 'key' => {php_str(v['key'])}],"
        for a, v in st["agents"].items())
    CONFIG_PHP.write_text(f"""<?php
// sozlash.py yaratgan. Qo'lda o'zgartirsangiz, sozlash.py qayta ishga tushganda ustiga yoziladi.
return [
    'bot_token' => {php_str(st['token'])},
    'webhook_secret' => {php_str(st['secret'])},
    'allowed_users' => [{', '.join(str(u) for u in st['users'])}],
    'agents' => [
{agents}
    ],
    'api_id' => {int(st.get('api_id', 0))},
    'api_hash' => {php_str(st.get('api_hash', ''))},
    'timezone' => 'Asia/Tashkent',
    'public_url' => {php_str(st['hub_url'])},
];
""", encoding="utf-8")


def write_config_env(st: dict, agent: str, roots: str, favorites: str) -> None:
    old = {}
    if CONFIG_ENV.exists():
        for line in CONFIG_ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                old[k.strip()] = v.strip()
    values = {
        "BOT_TOKEN": st["token"],
        "ALLOWED_USERS": ",".join(str(u) for u in st["users"]),
        "GROUP_ID": old.get("GROUP_ID", ""),
        "ROOTS": roots,
        "FAVORITES": favorites,
        "PART_MB": old.get("PART_MB", "45"),
        "MAX_FILE_MB": "0",
        "NOTIFY_START": old.get("NOTIFY_START", "1"),
        "HUB_URL": st["hub_url"],
        "AGENT_ID": agent,
        "AGENT_KEY": st["agents"][agent]["key"],
        "AGENT_NAME": st["agents"][agent]["name"],
        "API_ID": str(st.get("api_id", "") or ""),
        "API_HASH": st.get("api_hash", ""),
    }
    lines = ["# sozlash.py yaratgan. Qiymatlarni qo'shtirnoqsiz yozing."]
    lines += [f"{k}={v}" for k, v in values.items()]
    CONFIG_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def hub_call(st: dict, action: str) -> tuple[int, str]:
    code, text = _hub_request(st, f"{st['hub_url']}?a={action}")
    if code == 403:  # hub'ning eski versiyasi kalitni faqat manzil orqali qabul qiladi
        code, text = _hub_request(st, f"{st['hub_url']}?a={action}&key={st['secret']}")
    return code, text


def _hub_request(st: dict, url: str) -> tuple[int, str]:
    req = urllib.request.Request(url,
                                 headers={"X-Setup-Key": st["secret"], "User-Agent": "filebot-setup"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def run_setup(st: dict) -> None:
    code, text = hub_call(st, "setup")
    print(f"\nHub javobi ({code}):\n{text.strip()}")
    if code != 200 or text.count("OK") < 2:
        print("\n✘ Hub sozlanmadi. Tekshiring:")
        print("  • config.php to'g'ri papkaga yuklandimi (hub.php turgan papka)?")
        print(f"  • Brauzerda {st['hub_url']} ochilsa 'OK' chiqyaptimi?")
        print("  Yuqoridagi xabarni Claude'ga yuboring.")
        input("\nEnter...")
        sys.exit(1)
    print("\n✔ Hub tayyor. Endi 2_test.bat ni ishga tushiring va Telegram'da botga /kompyuter yozing.")
    input("\nEnter...")


def enable_big_files() -> None:
    """API_ID/API_HASH ni sozlaydi: 49 MB dan katta fayllar bitta faylda (2 GB gacha) boradi."""
    st = json.loads(STATE.read_text(encoding="utf-8"))
    print("=== Katta fayllar rejimini yoqish ===\n")
    print("1) Brauzerda https://my.telegram.org oching va telefon raqamingiz bilan kiring")
    print("2) «API development tools» → ilova nomi (masalan FileBot) → Create application")
    print("3) Chiqqan App api_id va App api_hash ni shu yerga yozing\n")
    api_id = ask("App api_id (raqam)", str(st.get("api_id") or ""),
                 lambda v: v.isdigit() or print("  Faqat raqam") or False)
    api_hash = ask("App api_hash (32 belgi)", st.get("api_hash", ""),
                   lambda v: bool(re.fullmatch(r"[0-9a-f]{32}", v)) or print("  32 ta belgi: 0-9, a-f") or False)
    st["api_id"], st["api_hash"] = int(api_id), api_hash
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    write_config_php(st)
    if CONFIG_ENV.exists():  # shu kompyuterning config.env iga ham yozamiz
        lines = [l for l in CONFIG_ENV.read_text(encoding="utf-8").splitlines()
                 if not l.startswith(("API_ID=", "API_HASH=", "MAX_FILE_MB="))]
        lines += [f"API_ID={api_id}", f"API_HASH={api_hash}", "MAX_FILE_MB=0"]
        CONFIG_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n✔ Saqlandi.")
    print("=" * 60)
    print("ENDI cPanel'da: public_html/filebot → Upload → shu fayl (ustiga yozilsin):")
    print(f"  {CONFIG_PHP}")
    print("Keyin har bir kompyuterda botni qayta ishga tushiring")
    print("(4_toxtatish.bat → 3_autostart_yoqish.bat, yoki kompyuterni qayta yoqing).")
    print("=" * 60)
    input("\nEnter...")


def main() -> None:
    if "--api" in sys.argv:
        enable_big_files()
        return
    if "--setup" in sys.argv:  # faqat hub'ni ishga tushirish, savollarsiz
        st = json.loads(STATE.read_text(encoding="utf-8"))
        print(f"Hub: {st['hub_url']}")
        run_setup(st)
        return

    print("=== Fayl-bot: sozlash ===\n")
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    first = not st
    if first:
        print("Birinchi sozlash. Kerak bo'ladi: bot tokeni, Telegram ID'ingiz va sayt domeni.\n")
        st["token"] = ask("Bot tokeni (@BotFather)", check=check_token)
        ids = ask("Telegram ID (@userinfobot). Bir nechta bo'lsa vergul bilan", check=check_ids)
        st["users"] = [int(x) for x in re.findall(r"\d+", ids)]
        domain = ask("Sayt domeni (masalan mylogo.uz)").replace("https://", "").replace("http://", "").strip("/")
        st["hub_url"] = f"https://{domain}/filebot/hub.php"
        st["secret"] = secrets.token_urlsafe(24)
        st["agents"] = {}
    else:
        print(f"Avvalgi sozlama topildi. Hub: {st['hub_url']}")
        print(f"Kompyuterlar: {', '.join(st['agents']) or '-'}\n")

    print("\nShu kompyuter haqida:")
    agent = ask("Qisqa nom (lotincha, masalan: ofis)", "ofis" if not st["agents"] else "", check_agent)
    name = ask("Telefonda ko'rinadigan nom", st["agents"].get(agent, {}).get("name", "Ofis kompyuteri"))
    roots = "*"  # bot kompyuterdagi barcha disklarni ko'radi
    favorites = input("Tez papkalar (ixtiyoriy, ; bilan): ").strip()
    key = st["agents"].get(agent, {}).get("key") or secrets.token_urlsafe(24)
    st["agents"][agent] = {"name": name, "key": key}

    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    write_config_php(st)
    write_config_env(st, agent, roots, favorites)
    print("\n✔ config.env yozildi (shu kompyuter uchun)")
    print(f"✔ {CONFIG_PHP} yozildi (hosting uchun)")

    print("\n" + "=" * 60)
    print("ENDI cPanel'da:")
    print("  File Manager → hub.php turgan papkani oching (public_html/filebot) →")
    print(f"  Upload → AYNAN shu fayl: {CONFIG_PHP}")
    print("  (eski config.php bo'lsa, ustiga yozilsin)")
    print("=" * 60)
    input("\nYuklab bo'lgach Enter bosing...")
    run_setup(st)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBekor qilindi.")
