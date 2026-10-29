"""Katta fayllarni yuborish (2 GB gacha bitta faylda, undan kattasi 2 GB lik qismlarda).

Oddiy Bot API faqat 50 MB gacha fayl qabul qiladi. Telegram'ning asosiy protokoli (MTProto)
orqali esa bot 2 GB gacha fayl yubora oladi. Buning uchun my.telegram.org dan olinadigan
API_ID va API_HASH kerak. Ular bo'lmasa, bot avvalgidek 45 MB lik qismlarga bo'lib yuboradi.
"""
import asyncio
import logging
import time
from pathlib import Path
from typing import Awaitable, Callable

from telethon import TelegramClient
from telethon.tl.types import InputPeerChannel, InputPeerChat, InputPeerUser

log = logging.getLogger("ofisbot")

MTPROTO_LIMIT = 2000 * 1024 * 1024 - 1   # Telegram: bot uchun bitta fayl 2 GB gacha
PART_SIZE = 1990 * 1024 * 1024            # undan katta fayllar shu hajmdagi qismlarga bo'linadi

ProgressFn = Callable[[int, int], Awaitable[None]]


def input_peer(chat_id: int):
    """Bot API chat ID sidan MTProto peer. Botlar 0 access_hash ishlatishi mumkin."""
    if chat_id > 0:
        return InputPeerUser(chat_id, 0)
    s = str(chat_id)
    if s.startswith("-100"):
        return InputPeerChannel(int(s[4:]), 0)
    return InputPeerChat(-chat_id)


class BigUploader:
    def __init__(self, api_id: int, api_hash: str, bot_token: str, session_file: Path) -> None:
        self._args = (api_id, api_hash, bot_token)
        self._session_file = session_file
        self._client: TelegramClient | None = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> TelegramClient:
        async with self._lock:
            if self._client and self._client.is_connected():
                return self._client
            api_id, api_hash, token = self._args
            self._session_file.parent.mkdir(parents=True, exist_ok=True)
            client = TelegramClient(str(self._session_file), api_id, api_hash,
                                    receive_updates=False, connection_retries=10,
                                    request_retries=10, flood_sleep_threshold=120)
            await client.start(bot_token=token)
            log.info("Katta fayllar uchun MTProto ulanishi tayyor")
            self._client = client
            return client

    async def send(self, chat_id: int, path: Path, caption: str,
                   progress: ProgressFn | None = None) -> int:
        """Faylni yuboradi va Telegram'dagi xabar ID sini qaytaradi."""
        client = await self._get_client()
        msg = await client.send_file(
            input_peer(chat_id), str(path), caption=caption, force_document=True,
            parse_mode=None, part_size_kb=512,
            progress_callback=(lambda sent, total: progress(sent, total)) if progress else None,
        )
        return msg.id

    async def close(self) -> None:
        if self._client:
            await self._client.disconnect()


class Progress:
    """Holat xabarini har bir necha sekundda yangilab turadi (foiz, tezlik, qolgan vaqt)."""

    def __init__(self, update: Callable[[str], Awaitable[None]], title: str,
                 offset: int, grand_total: int) -> None:
        self._update = update
        self._title = title
        self._offset = offset
        self._grand = grand_total
        self._start = time.monotonic()
        self._last = 0.0

    async def __call__(self, sent: int, total: int) -> None:
        now = time.monotonic()
        if now - self._last < 4 and sent < total:
            return
        self._last = now
        done = self._offset + sent
        pct = done * 100 // max(self._grand, 1)
        speed = sent / max(now - self._start, 0.1)
        left = (self._grand - done) / max(speed, 1)
        bar = "▓" * (pct // 10) + "░" * (10 - pct // 10)
        try:
            await self._update(f"⏳ {self._title}\n{bar} {pct}%\n"
                               f"🚀 {speed / 1048576:.1f} MB/s · ⌛ ~{_fmt(left)}")
        except Exception:
            pass  # holatni yangilash xatosi yuborishni to'xtatmasin


def _fmt(sec: float) -> str:
    sec = int(sec)
    if sec < 60:
        return f"{sec} s"
    if sec < 3600:
        return f"{sec // 60} daq {sec % 60} s"
    return f"{sec // 3600} soat {sec % 3600 // 60} daq"
