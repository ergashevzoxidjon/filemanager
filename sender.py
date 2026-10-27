"""Faylni Telegramga yuborish. 49 MB dan kattasini bo'laklarga bo'ladi."""
import asyncio
from html import escape
import shutil
import tempfile
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, Message

TELEGRAM_LIMIT = 49 * 1024 * 1024
UPLOAD_TIMEOUT = 900  # sekund: sekin internetda ham katta fayl ulgursin


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


async def send_file(bot: Bot, chat_id: int, path: Path, part_mb: int,
                    caption: str | None = None) -> list[Message]:
    """Yuborilgan hujjat xabarlarini qaytaradi (katta fayl bo'lsa - har bir qism)."""
    size = path.stat().st_size
    if size <= TELEGRAM_LIMIT:
        msg = await bot.send_document(chat_id, FSInputFile(path), caption=caption,
                                      request_timeout=UPLOAD_TIMEOUT)
        return [msg]

    tmp = Path(tempfile.mkdtemp(prefix="ofisbot_"))
    try:
        parts = await asyncio.to_thread(split_file, path, tmp, part_mb * 1024 * 1024)
        total = len(parts)
        sent: list[Message] = []
        for i, part in enumerate(parts, 1):
            cap = f"{caption or path.name}\n🧩 {i}/{total}-qism"
            sent.append(await bot.send_document(chat_id, FSInputFile(part), caption=cap,
                                                request_timeout=UPLOAD_TIMEOUT))
        await bot.send_message(
            chat_id,
            f"🧩 <b>{escape(path.name)}</b> {total} qismga bo'lib yuborildi.\n\n"
            "Qanday birlashtiriladi:\n"
            "• Hamma qismlarni bitta papkaga yuklab oling\n"
            "• <b>7-Zip</b> bilan <code>.001</code> faylni oching → «Extract» (yoki «Combine files»)\n"
            "• Yoki cmd da: <code>copy /b \"fayl.001\"+\"fayl.002\" \"fayl\"</code>",
        )
        return sent
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
