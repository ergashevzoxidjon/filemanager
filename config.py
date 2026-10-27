"""config.env faylini o'qiydi va tekshiradi."""
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
log = logging.getLogger("ofisbot")


class ConfigError(Exception):
    pass


@dataclass
class Config:
    token: str
    allowed_users: set[int]
    group_id: int | None
    roots: list[Path]
    favorites: list[Path] = field(default_factory=list)
    part_mb: int = 45
    max_file_mb: int = 1000
    notify_start: bool = True
    # Ko'p kompyuter rejimi (markaziy hub orqali). HUB_URL bo'sh bo'lsa - bitta kompyuter rejimi.
    hub_url: str = ""
    agent_id: str = ""
    agent_key: str = ""
    agent_name: str = "Kompyuter"
    # O'z Bot API serveringiz (2 GB gacha fayl uchun). Bo'sh = api.telegram.org
    bot_api_url: str = ""

    @property
    def hub_mode(self) -> bool:
        return bool(self.hub_url)

    @property
    def allowed_dirs(self) -> list[Path]:
        """Bot kira oladigan barcha papkalar (disklar + tez papkalar)."""
        return self.roots + self.favorites


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

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or "BU_YERGA" in token or ":" not in token:
        raise ConfigError("config.env ichida BOT_TOKEN to'g'ri yozilmagan.")

    users_raw = os.getenv("ALLOWED_USERS", "").replace(" ", "")
    try:
        users = {int(x) for x in users_raw.split(",") if x}
    except ValueError:
        raise ConfigError("ALLOWED_USERS faqat raqamlardan iborat bo'lishi kerak (vergul bilan).")
    if not users or users == {123456789}:
        raise ConfigError("ALLOWED_USERS ga o'z Telegram ID'ingizni yozing.")

    group_raw = os.getenv("GROUP_ID", "").strip()
    try:
        group_id = int(group_raw) if group_raw else None
    except ValueError:
        raise ConfigError("GROUP_ID raqam bo'lishi kerak (odatda -100 bilan boshlanadi).")

    roots = [p for p in _paths(os.getenv("ROOTS", "D:\\")) if _exists(p, "ROOTS")]
    if not roots:
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
        roots=roots,
        favorites=favorites,
        part_mb=max(1, min(_int("PART_MB", 45), 49)),
        max_file_mb=_int("MAX_FILE_MB", 1000),
        notify_start=os.getenv("NOTIFY_START", "1").strip() != "0",
        hub_url=hub_url,
        agent_id=agent_id,
        agent_key=agent_key,
        agent_name=agent_name,
        bot_api_url=os.getenv("BOT_API_URL", "").strip().rstrip("/"),
    )


def _exists(path: Path, name: str) -> bool:
    if path.is_dir():
        return True
    log.warning("%s: %s topilmadi, o'tkazib yuborildi", name, path)
    return False
