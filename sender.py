"""Faylni Telegramga yuborish.

  • 49 MB gacha - oddiy Bot API orqali.
  • Kattaroq va API_ID/API_HASH sozlangan - MTProto orqali bitta faylda (2 GB gacha),
    2 GB dan katta bo'lsa 2 GB lik qismlarda. Hajm cheklovi yo'q.
  • Kattaroq, lekin API_ID sozlanmagan - 45 MB lik qismlarga bo'linadi (avvalgidek).
"""
from __future__ import annotations

import asyncio
import io
import shutil
import tempfile
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Awaitable, Callable

from aiogram import Bot
from aiogram.types import FSInputFile

try:
    from big_upload import MTPROTO_LIMIT, PART_SIZE, BigUploader, Progress
except Exception:  # telethon o'rnatilmagan - katta fayllar 45 MB lik qismlarda boradi
    MTPROTO_LIMIT, PART_SIZE, BigUploader, Progress = 0, 0, None, None

TELEGRAM_LIMIT = 49 * 1024 * 1024
UPLOAD_TIMEOUT = 900  # sekund: sekin internetda ham 49 MB ulgursin


@dataclass
class Sent:
    message_id: int
    file_id: str | None   # «Ulashish» tugmasi uchun (Bot API file_id)
    name: str


class FileSlice(io.RawIOBase):
    """Faylning bir bo'lagini alohida fayl kabi o'qish (diskka nusxa ko'chirmasdan)."""

    def __init__(self, path: Path, start: int, length: int, name: str) -> None:
        self._f = open(path, "rb")
        self._start, self._len, self.name = start, length, name
        self._pos = 0
        self._f.seek(start)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def read(self, n: int = -1) -> bytes:
        left = self._len - self._pos
        if n is None or n < 0 or n > left:
            n = left
        data = self._f.read(n)
        self._pos += len(data)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        base = {0: 0, 1: self._pos, 2: self._len}[whence]
        self._pos = max(0, min(self._len, base + offset))
        self._f.seek(self._start + self._pos)
        return self._pos

    def tell(self) -> int:
        return self._pos

    def close(self) -> None:
        self._f.close()
        super().close()


def split_file(src: Path, out_dir: Path, part_size: int) -> list[Path]:
    parts: list[Path] = []
    buf = 1024 * 1024
    with open(src, "rb") as f:
        idx = 1
        while True:
            part = out_dir / f"{src.name}.{idx:03d}"
            written = 0
            with open(part, "wb") as out:
                while written < part_size:
                    chunk = f.read(min(buf, part_size - written))
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
            if written == 0:
                part.unlink()
                break
            parts.append(part)
            idx += 1
    return parts


JOIN_HELP = ("Qanday birlashtiriladi:\n"
             "• Hamma qismlarni bitta papkaga yuklab oling\n"
             "• <b>7-Zip</b> bilan <code>.001</code> faylni oching → «Extract» (yoki «Combine files»)\n"
             "• Yoki cmd da: <code>copy /b \"fayl.001\"+\"fayl.002\" \"fayl\"</code>")


async def send_file(bot: Bot, chat_id: int, path: Path, part_mb: int,
                    caption: str | None = None, big: BigUploader | None = None,
                    status: Callable[[str], Awaitable[None]] | None = None) -> list[Sent]:
    size = path.stat().st_size
    caption = caption or path.name

    if size <= TELEGRAM_LIMIT:
        msg = await bot.send_document(chat_id, FSInputFile(path), caption=caption,
                                      request_timeout=UPLOAD_TIMEOUT)
        return [Sent(msg.message_id, msg.document.file_id if msg.document else None, path.name)]

    if big is not None:
        return await _send_big(bot, chat_id, path, size, caption, big, status)

    # API_ID sozlanmagan: 45 MB lik qismlar
    tmp = Path(tempfile.mkdtemp(prefix="ofisbot_"))
    try:
        parts = await asyncio.to_thread(split_file, path, tmp, part_mb * 1024 * 1024)
        sent: list[Sent] = []
        for i, part in enumerate(parts, 1):
            if status:
                await status(f"⏳ {escape(path.name)}\n🧩 {i}/{len(parts)}-qism yuborilmoqda...")
            msg = await bot.send_document(chat_id, FSInputFile(part),
                                          caption=f"{caption}\n🧩 {i}/{len(parts)}-qism",
                                          request_timeout=UPLOAD_TIMEOUT)
            sent.append(Sent(msg.message_id, msg.document.file_id if msg.document else None, part.name))
        await bot.send_message(chat_id, f"🧩 <b>{escape(path.name)}</b> {len(parts)} qismga bo'lib "
                                        f"yuborildi.\n\n{JOIN_HELP}\n\n"
                                        "<i>Bitta faylda olish uchun katta fayl rejimini yoqing "
                                        "(README: «Katta fayllar»).</i>")
        return sent
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def _send_big(bot: Bot, chat_id: int, path: Path, size: int, caption: str,
                    big: BigUploader, status) -> list[Sent]:
    parts = 1 if size <= MTPROTO_LIMIT else -(-size // PART_SIZE)
    sent: list[Sent] = []
    for i in range(parts):
        start = i * PART_SIZE if parts > 1 else 0
        length = min(PART_SIZE, size - start) if parts > 1 else size
        name = path.name if parts == 1 else f"{path.name}.{i + 1:03d}"
        cap = caption if parts == 1 else f"{caption}\n🧩 {i + 1}/{parts}-qism"
        title = escape(path.name) + (f" ({i + 1}/{parts})" if parts > 1 else "")
        prog = Progress(status, title, start, size) if status else None
        src = FileSlice(path, start, length, name)
        try:
            msg_id = await big.send(chat_id, src if parts > 1 else path, cap, prog)
        finally:
            src.close()
        sent.append(Sent(msg_id, await _file_id_of(bot, chat_id, msg_id), name))
    if parts > 1:
        await bot.send_message(chat_id, f"🧩 <b>{escape(path.name)}</b> {parts} qismga bo'lib "
                                        f"yuborildi (har biri 2 GB gacha).\n\n{JOIN_HELP}")
    return sent


async def _file_id_of(bot: Bot, chat_id: int, message_id: int) -> str | None:
    """MTProto orqali yuborilgan faylning Bot API file_id sini olish («Ulashish» uchun).
    Xabarni o'sha chatga jimgina nusxalab, file_id ni olamiz va nusxani darhol o'chiramiz."""
    if chat_id < 0:
        return None
    try:
        fwd = await bot.forward_message(chat_id, chat_id, message_id, disable_notification=True)
        try:
            return fwd.document.file_id if fwd.document else None
        finally:
            await bot.delete_message(chat_id, fwd.message_id)
    except Exception:
        return None

