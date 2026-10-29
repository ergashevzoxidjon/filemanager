"""config.env faylini o'qiydi va tekshiradi."""
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# .exe (PyInstaller) bo'lsa - exe turgan papka, aks holda shu fayl turgan papka
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
log = logging.getLogger("ofisbot")


class ConfigError(Exception):
    pass


@dataclass
class Config:
    token: str
    allowed_users: set[int]
    group_id: int | None
    root_list: list[Path]
    favorites: list[Path] = field(default_factory=list)
    part_mb: int = 45
    max_file_mb: int = 0          # 0 = cheklovsiz
    notify_start: bool = True
    # Ko'p kompyuter rejimi (markaziy hub orqali). HUB_URL bo'sh bo'lsa - bitta kompyuter rejimi.
    hub_url: str = ""
    agent_id: str = ""
    agent_key: str = ""
    agent_name: str = "Kompyuter"
    # O'z Bot API serveringiz (2 GB gacha fayl uchun). Bo'sh = api.telegram.org
    bot_api_url: str = ""
    # my.telegram.org dan: 49 MB dan katta fayllarni bitta faylda (2 GB gacha) yuborish uchun
    api_id: int = 0
    api_hash: str = ""
    all_drives: bool = False      # True = kompyuterdagi barcha disklar (ROOTS=* yoki bo'sh)

    @property
    def roots(self) -> list[Path]:
        """Bot ko'radigan disklar. «Barchasi» rejimida har safar qaytadan aniqlanadi -
        keyin ulangan fleshka yoki tarmoq disklari ham darhol ko'rinadi."""
        return detect_drives() if self.all_drives else self.root_list

    @property
    def hub_mode(self) -> bool:
        return bool(self.hub_url)

    @property
    def allowed_dirs(self) -> list[Path]:
        """Bot kira oladigan barcha papkalar (disklar + tez papkalar)."""
        return self.roots + self.favorites


_drive_cache: tuple[float, list[Path]] = (0.0, [])


def detect_drives() -> list[Path]:
    """Kompyuterdagi barcha disklar (C:\\, D:\\, fleshka, tarmoq disklari). 10 soniya keshlanadi."""
    global _drive_cache
    now = time.monotonic()
    if now - _drive_cache[0] < 10 and _drive_cache[1]:
        return list(_drive_cache[1])
    drives = _scan_drives()
    _drive_cache = (now, drives)
    return list(drives)


def _scan_drives() -> list[Path]:
    if sys.platform != "win32":
        return [Path("/")]
    try:
        found = [Path(d) for d in os.listdrives()]  # Python 3.12+
    except (AttributeError, OSError):
        import string
        found = [Path(f"{c}:\\") for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")]
    ready = []
    for d in found:
        try:
            os.listdir(d)       # bo'sh CD/DVD o'quvchi va uzilgan disklarni o'tkazib yuboramiz
            ready.append(d)
        except OSError:
            pass
    return ready or [Path("C:\\")]


def _paths(value: str) -> list[Path]:
    return [Path(p.strip().strip('"')) for p in value.split(";") if p.strip()]


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name} raqam bo'lishi kerak, hozir: {raw!r}")


def load_config() -> Config:
    env_file = BASE_DIR / "config.env"
    if not env_file.exists():
        raise ConfigError("config.env topilmadi. install.bat ni ishga tushiring yoki "
                          "config.example.env dan nusxa oling.")
    load_dotenv(env_file, override=True)

    # Hub rejimida token va foydalanuvchilar ro'yxati hub'dan olinadi (o'rnatuvchi shunday sozlaydi)
    via_hub = bool(os.getenv("HUB_URL", "").strip())
    token = os.getenv("BOT_TOKEN", "").strip()
    if "BU_YERGA" in token:
        token = ""
    if token and ":" not in token:
        raise ConfigError("config.env ichida BOT_TOKEN to'g'ri yozilmagan.")
    if not token and not via_hub:
        raise ConfigError("config.env ichida BOT_TOKEN yozilmagan.")

    users_raw = os.getenv("ALLOWED_USERS", "").replace(" ", "")
    try:
        users = {int(x) for x in users_raw.split(",") if x}
    except ValueError:
        raise ConfigError("ALLOWED_USERS faqat raqamlardan iborat bo'lishi kerak (vergul bilan).")
    if users == {123456789}:
        users = set()
    if not users and not via_hub:
        raise ConfigError("ALLOWED_USERS ga o'z Telegram ID'ingizni yozing.")

    group_raw = os.getenv("GROUP_ID", "").strip()
    try:
        group_id = int(group_raw) if group_raw else None
    except ValueError:
        raise ConfigError("GROUP_ID raqam bo'lishi kerak (odatda -100 bilan boshlanadi).")

    # ROOTS bo'sh yoki * bo'lsa - kompyuterdagi barcha disklar va barcha fayllar
    roots_raw = os.getenv("ROOTS", "").strip()
    all_drives = roots_raw in ("", "*") or roots_raw.upper() in ("ALL", "BARCHASI")
    roots = [] if all_drives else [p for p in _paths(roots_raw) if _exists(p, "ROOTS")]
    if not all_drives and not roots:
        raise ConfigError("ROOTS dagi birorta disk/papka topilmadi.")
    favorites = [p for p in _paths(os.getenv("FAVORITES", "")) if _exists(p, "FAVORITES")]

    hub_url = os.getenv("HUB_URL", "").strip()
    agent_id = os.getenv("AGENT_ID", "").strip().lower()
    agent_key = os.getenv("AGENT_KEY", "").strip()
    agent_name = os.getenv("AGENT_NAME", "").strip() or agent_id or "Kompyuter"
    if hub_url:
        if not hub_url.startswith("https://") and not hub_url.startswith("http://"):
            raise ConfigError("HUB_URL https:// bilan boshlanishi kerak.")
        if not re.fullmatch(r"[a-z0-9]{1,10}", agent_id):
            raise ConfigError("AGENT_ID 1-10 ta lotin harf/raqam bo'lishi kerak (masalan: ofis).")
        if len(agent_key) < 16:
            raise ConfigError("AGENT_KEY kamida 16 belgidan iborat bo'lishi kerak.")

    return Config(
        token=token,
        allowed_users=users,
        group_id=group_id,
        root_list=roots,
        all_drives=all_drives,
        favorites=favorites,
        part_mb=max(1, min(_int("PART_MB", 45), 49)),
        max_file_mb=_int("MAX_FILE_MB", 0),
        notify_start=os.getenv("NOTIFY_START", "1").strip() != "0",
        hub_url=hub_url,
        agent_id=agent_id,
        agent_key=agent_key,
        agent_name=agent_name,
        bot_api_url=os.getenv("BOT_API_URL", "").strip().rstrip("/"),
        api_id=_int("API_ID", 0),
        api_hash=os.getenv("API_HASH", "").strip(),
    )


def _exists(path: Path, name: str) -> bool:
    if path.is_dir():
        return True
    log.warning("%s: %s topilmadi, o'tkazib yuborildi", name, path)
    return False
