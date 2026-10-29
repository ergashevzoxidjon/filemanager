"""Avtomatik yangilanish.

GitHub'dagi eng so'nggi Release tekshiriladi. Unda versiya yangi bo'lsa:
  • .exe rejimi    → FileBot.exe almashtiriladi (ishlab turgan exe nomi o'zgartiriladi, yangisi joyiga qo'yiladi);
  • manba rejimi   → .py fayllar yangilanadi (config.env, logs, data tegilmaydi).
So'ng bot 4-kod bilan chiqadi va ishga tushiruvchi (run.bat / run_forever.bat) uni darhol qayta yoqadi.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import sys
import zipfile
from pathlib import Path

import aiohttp

from config import BASE_DIR
from version import VERSION

log = logging.getLogger("ofisbot")

DEFAULT_REPO = "ergashevzoxidjon/filemanager"
API_BASE = "https://api.github.com"
EXE_ASSET = "FileBot.exe"
SRC_ASSET = "filebot-agent.zip"
EXIT_UPDATED = 4
CHECK_EVERY = 6 * 3600  # soniya
# Manba rejimida yangilanmaydigan fayllar (ishlab turgan .bat larni almashtirish xavfli)
SRC_ALLOWED_SUFFIXES = (".py", ".txt")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _ver(v: str) -> tuple[int, ...]:
    parts = []
    for p in v.lstrip("vV").split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts + [0] * (3 - len(parts)))


def cleanup_old() -> None:
    """Oldingi yangilanishdan qolgan eski exe ni o'chiradi."""
    for name in ("FileBot.old.exe", "update.tmp"):
        try:
            (BASE_DIR / name).unlink(missing_ok=True)
        except OSError:
            pass


async def check(repo: str = DEFAULT_REPO) -> dict | None:
    """Yangi versiya bo'lsa {'version', 'url', 'digest', 'size'} qaytaradi, aks holda None."""
    url = f"{API_BASE}/repos/{repo}/releases/latest"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"FileBot/{VERSION}"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        async with s.get(url, headers=headers) as r:
            if r.status == 404:
                raise RuntimeError("GitHub'da Release topilmadi (repo yopiqmi yoki hali Release yo'qmi?)")
            r.raise_for_status()
            data = await r.json(content_type=None)
    latest = str(data.get("tag_name", "")).lstrip("vV")
    if not latest or _ver(latest) <= _ver(VERSION):
        return None
    want = EXE_ASSET if is_frozen() else SRC_ASSET
    for a in data.get("assets", []):
        if a.get("name") == want:
            digest = str(a.get("digest") or "")
            return {"version": latest, "url": a["browser_download_url"], "size": a.get("size", 0),
                    "digest": digest.split(":", 1)[1] if digest.startswith("sha256:") else ""}
    raise RuntimeError(f"v{latest} Release'ida {want} fayli yo'q")


async def download_and_apply(info: dict) -> None:
    tmp = BASE_DIR / "update.tmp"
    h = hashlib.sha256()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1800)) as s:
        async with s.get(info["url"], headers={"User-Agent": f"FileBot/{VERSION}"}) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                async for chunk in r.content.iter_chunked(1 << 20):
                    f.write(chunk)
                    h.update(chunk)
    if info.get("digest") and h.hexdigest() != info["digest"]:
        tmp.unlink(missing_ok=True)
        raise RuntimeError("Yuklangan fayl buzilgan (sha256 mos kelmadi)")
    await asyncio.to_thread(_apply, tmp)


def _apply(tmp: Path) -> None:
    if is_frozen():
        exe = Path(sys.executable).resolve()
        old = exe.with_name("FileBot.old.exe")
        old.unlink(missing_ok=True)
        os.replace(exe, old)          # Windows ishlab turgan exe nomini o'zgartirishga ruxsat beradi
        try:
            os.replace(tmp, exe)
        except OSError:
            os.replace(old, exe)      # muvaffaqiyatsiz bo'lsa - eskisini qaytaramiz
            raise
        return
    data = tmp.read_bytes()
    tmp.unlink(missing_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            p = Path(name)
            if p.is_absolute() or ".." in p.parts or "/" in name.strip("/") or p.suffix not in SRC_ALLOWED_SUFFIXES:
                continue  # faqat ildizdagi .py/.txt fayllar
            target = BASE_DIR / p.name
            part = target.with_suffix(target.suffix + ".new")
            part.write_bytes(z.read(name))
            os.replace(part, target)


def restart_for_update() -> None:
    """Ishga tushiruvchi (run.bat) 4-kodni ko'rib, botni darhol qayta yoqadi."""
    logging.shutdown()
    os._exit(EXIT_UPDATED)


async def update_loop(notify, repo: str = DEFAULT_REPO) -> None:
    """Fon vazifasi: har 6 soatda yangilanishni tekshiradi va o'rnatadi."""
    await asyncio.sleep(60)  # bot to'liq ishga tushib olsin
    while True:
        try:
            info = await check(repo)
            if info:
                await run_update(info, notify)
        except Exception as e:  # noqa: BLE001
            log.warning("Yangilanishni tekshirib bo'lmadi: %s", e)
        await asyncio.sleep(CHECK_EVERY)


async def run_update(info: dict, notify) -> None:
    log.info("Yangilanish: v%s -> v%s", VERSION, info["version"])
    try:
        await notify(f"🔄 Yangilanmoqda: v{VERSION} → v{info['version']}...")
    except Exception:  # noqa: BLE001
        pass
    await download_and_apply(info)
    log.info("Yangilandi, qayta ishga tushirilmoqda")
    restart_for_update()
