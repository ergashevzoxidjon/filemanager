"""Ofis fayl-bot (agent): shu kompyuterdagi fayllarni telefondan Telegram orqali boshqarish.

Ikki rejim bor:
  • Bitta kompyuter — HUB_URL bo'sh. Bot Telegram'dan xabarlarni o'zi oladi.
  • Ko'p kompyuter — HUB_URL to'ldirilgan. Xabarlar markaziy hub orqali keladi,
    telefonda «💻 Kompyuter» tugmasi bilan kerakli kompyuterni tanlaysiz.

Ishga tushirish:  python bot.py
"""
from __future__ import annotations

import asyncio
import io
import os
import re
import logging
import socket
import sys
from datetime import datetime
from html import escape
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import (BotCommand, BufferedInputFile, CallbackQuery,
                           InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery,
                           InlineQueryResultCachedDocument,
                           InlineQueryResultCachedPhoto, KeyboardButton, Message,
                           ReplyKeyboardMarkup)
from aiogram.utils.keyboard import InlineKeyboardBuilder


from config import BASE_DIR, Config, ConfigError, load_config
from explorer import (Registry, display_name, human_size, is_allowed, list_dir,
                      same_path, short)
from hub_client import HubRejected, hub_bootstrap, run_hub_client
from search import search_files
from sender import send_file
import shutil
import tempfile
import updater
import zipper
from version import VERSION

# Qo'shimcha imkoniyatlar: kutubxona o'rnatilmagan bo'lsa ham bot asosiy ishini qilaversin
OPTIONAL_ERRORS: list[str] = []
import preview  # Pillow/PyMuPDF bo'lmasa ham ishlaydi (Edge orqali chizadi)
try:
    from PIL import Image
except Exception:  # noqa: BLE001
    Image = None
try:
    from big_upload import BigUploader
except Exception as _e:  # noqa: BLE001
    BigUploader = None
    OPTIONAL_ERRORS.append(f"Katta fayllar (telethon): {_e}")
from shares import ShareStore

PAGE_SIZE = 20
LOCK_PORT = 47291          # bot ikki marta ishga tushib qolmasligi uchun
EXIT_CONFIG_ERROR = 2      # run_forever.bat bu kodlarda qayta urinmaydi
EXIT_ALREADY_RUNNING = 3

log = logging.getLogger("ofisbot")
cfg: Config  # main() da yuklanadi
reg = Registry()
shares = ShareStore(BASE_DIR / "data" / "shares.json")
dp = Dispatcher()
waiting_search: set[int] = set()
user_loc: dict[int, Path] = {}   # har bir foydalanuvchi botda hozir qaysi papka/faylda turibdi
big_uploader: BigUploader | None = None   # API_ID sozlangan bo'lsa - 49 MB dan katta fayllar uchun

BTN_DISK = "📂 Disklar"
BTN_SEARCH = "🔎 Qidirish"
BTN_SCREEN = "🖥 Ekran"
BTN_HELP = "ℹ️ Yordam"
BTN_PC = "💻 Kompyuter"   # ko'p kompyuter rejimida hub o'zi javob beradi


def main_kb() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=BTN_DISK), KeyboardButton(text=BTN_SEARCH)],
            [KeyboardButton(text=BTN_SCREEN), KeyboardButton(text=BTN_HELP)]]
    if cfg.hub_mode:
        rows.insert(0, [KeyboardButton(text=BTN_PC)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def P(data: str) -> str:
    """Tugma ma'lumotiga kompyuter belgisini qo'shadi, hub uni kerakli kompyuterga
    yo'naltirishi uchun. Bitta kompyuter rejimida o'zgarishsiz qoladi."""
    return f"{cfg.agent_id}|{data}" if cfg.hub_mode else data


def share_query(token: str) -> str:
    return f"{cfg.agent_id} {token}" if cfg.hub_mode else token


def help_text() -> str:
    pc = (f"💻 Hozir tanlangan: <b>{escape(cfg.agent_name)}</b>\n"
          f"Boshqa kompyuterga o'tish: «{BTN_PC}» tugmasi yoki /kompyuter\n\n"
          if cfg.hub_mode else "")
    return (
        "🤖 <b>Fayl-bot</b>\n\n" + pc +
        "📂 /disk — disk va papkalarni ko'rish\n"
        "🔎 /izla <i>so'z</i> — fayl nomi bo'yicha qidirish\n"
        "🖥 /ekran — ochiq turgan papka yoki faylning ko'rinishi\n"
        "    (hech narsa ochilmagan bo'lsa - kompyuterning to'liq ekrani)\n"
        "🆔 /id — shu chat ID'sini bilish\n"
        "🔄 /yangilash — versiya va yangilanish\n"
        "🗜 Papka ichida «ZIP» — butun papkani bitta faylda olish\n\n"
        "Faylni bosing → «📥 Menga yuborish».\n"
        "Fayl kelgach, ostidagi «↗️ Ulashish» tugmasi bilan uni istalgan "
        "chat, guruh yoki kanalga yuborasiz.\n\n" + (
            "📦 Fayllar <b>2 GB gacha bitta faylda</b> yuboriladi (undan kattasi 2 GB lik qismlarda)."
            if big_uploader else
            "📦 Hozir 49 MB dan katta fayllar 45 MB lik bo'laklarda keladi.\n"
            "2 GB gacha bitta faylda olish uchun: /kattafayl"
        )
    )


# ─────────────────────────── Xavfsizlik ───────────────────────────

class AccessMiddleware(BaseMiddleware):
    """Faqat ALLOWED_USERS ro'yxatidagi odamlarga javob beradi."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and user.id in cfg.allowed_users:
            return await handler(event, data)
        uid = user.id if user else "?"
        name = user.full_name if user else "?"
        log.warning("Ruxsatsiz urinish: %s (%s)", uid, name)
        if isinstance(event, Message) and event.chat.type == "private":
            await event.answer(f"⛔ Ruxsat yo'q.\nSizning ID: <code>{uid}</code>")
        elif isinstance(event, CallbackQuery):
            await event.answer("⛔ Ruxsat yo'q", show_alert=True)
        elif isinstance(event, InlineQuery):
            await event.answer([], cache_time=0, is_personal=True)
        return None


def allowed(path: Path | None) -> bool:
    return path is not None and is_allowed(path, cfg.allowed_dirs)


# ─────────────────────────── Ko'rinishlar ───────────────────────────

def header() -> str:
    return f"💻 <b>{escape(cfg.agent_name)}</b>\n" if cfg.hub_mode else ""


def roots_view():
    kb = InlineKeyboardBuilder()
    for r in cfg.roots:
        kb.button(text=f"💽 {short(str(r))}", callback_data=P(f"d:{reg.id(r)}:0"))
    for f in cfg.favorites:
        kb.button(text=f"⭐ {short(display_name(f))}", callback_data=P(f"d:{reg.id(f)}:0"))
    kb.adjust(1)
    return header() + "🏠 <b>Disklar va tez papkalar</b>", kb.as_markup()


def dir_view(path: Path, page: int):
    dirs, files, err = list_dir(path)
    entries: list[tuple[Path, int | None]] = [(d, None) for d in dirs] + list(files)
    pages = max(1, -(-len(entries) // PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    chunk = entries[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    kb = InlineKeyboardBuilder()
    for p, size in chunk:
        if size is None:
            kb.button(text=f"📁 {short(p.name)}", callback_data=P(f"d:{reg.id(p)}:0"))
        else:
            kb.button(text=f"📄 {short(p.name, 32)} · {human_size(size)}",
                      callback_data=P(f"f:{reg.id(p)}"))
    kb.adjust(1)

    pid = reg.id(path)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=P(f"d:{pid}:{page - 1}")))
    if pages > 1:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data=P("noop")))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=P(f"d:{pid}:{page + 1}")))
    if nav:
        kb.row(*nav)

    bottom = []
    is_top = any(same_path(path, r) for r in cfg.roots)
    if not is_top and allowed(path.parent):
        bottom.append(InlineKeyboardButton(text="⬆️ Yuqoriga",
                                           callback_data=P(f"d:{reg.id(path.parent)}:0")))
    bottom.append(InlineKeyboardButton(text="🏠 Disklar", callback_data=P("r")))
    kb.row(InlineKeyboardButton(text="🖼 Ko'rinish", callback_data=P(f"v:{pid}")),
           InlineKeyboardButton(text="🗜 ZIP qilib olish", callback_data=P(f"z:{pid}")))
    kb.row(*bottom)

    text = (header() + f"📂 <code>{escape(str(path))}</code>\n"
            f"{len(dirs)} papka, {len(files)} fayl")
    if err:
        text += f"\n\n{err}"
    elif not entries:
        text += "\n\n<i>Papka bo'sh</i>"
    return text, kb.as_markup()


def file_view(path: Path):
    st = path.stat()
    text = (header() + f"📄 <b>{escape(path.name)}</b>\n"
            f"📦 {human_size(st.st_size)}\n"
            f"🕒 {datetime.fromtimestamp(st.st_mtime):%d.%m.%Y %H:%M}\n"
            f"📂 <code>{escape(str(path.parent))}</code>")
    if cfg.max_file_mb and st.st_size > cfg.max_file_mb * 1024 * 1024:
        text += f"\n\n⚠️ Fayl {cfg.max_file_mb} MB dan katta, yuborib bo'lmaydi."
    fid = reg.id(path)
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 Menga yuborish", callback_data=P(f"s:{fid}:me"))
    if cfg.group_id:
        kb.button(text="👥 Guruhga yuborish", callback_data=P(f"s:{fid}:gr"))
    kb.button(text="🖼 Ko'rinish", callback_data=P(f"v:{fid}"))
    kb.button(text="⬅️ Orqaga", callback_data=P(f"d:{reg.id(path.parent)}:0"))
    kb.adjust(2 if cfg.group_id else 1, 2)
    return text, kb.as_markup()


def share_markup(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="↗️ Ulashish", switch_inline_query=share_query(token))
    ]])


async def safe_edit(message: Message, text: str, markup) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            raise


# ─────────────────────────── Buyruqlar ───────────────────────────

@dp.message(CommandStart())
@dp.message(Command("yordam", "help"))
@dp.message(F.text == BTN_HELP)
async def cmd_start(message: Message):
    await message.answer(help_text(),
                         reply_markup=main_kb() if message.chat.type == "private" else None)


@dp.message(Command("kompyuter"))
@dp.message(F.text == BTN_PC)
async def cmd_pc(message: Message):
    # Ko'p kompyuter rejimida bu buyruqqa hub javob beradi va bu yerga yetib kelmaydi.
    await message.answer("Bu bot bitta kompyuter rejimida ishlayapti.")


@dp.message(Command("disk"))
@dp.message(F.text == BTN_DISK)
async def cmd_disk(message: Message):
    user_loc.pop(message.from_user.id, None)
    text, markup = roots_view()
    await message.answer(text, reply_markup=markup)


@dp.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"🆔 Chat ID: <code>{message.chat.id}</code>\n"
                         f"👤 Sizning ID: <code>{message.from_user.id}</code>")


@dp.message(Command("ekran"))
@dp.message(F.text == BTN_SCREEN)
async def cmd_screen(message: Message, bot: Bot):
    """Botda qaysi papka/fayl ochiq bo'lsa - o'shaning ko'rinishi; hech narsa ochilmagan bo'lsa -
    kompyuterning to'liq ekrani."""
    loc = user_loc.get(message.from_user.id)
    if loc is not None and allowed(loc) and loc.exists():
        await send_view(bot, message.chat.id, loc)
    else:
        await send_desktop(bot, message.chat.id)


async def send_photo_or_doc(bot: Bot, chat_id: int, png: bytes, name: str, caption: str,
                            markup=None) -> None:
    file = BufferedInputFile(png, filename=name)
    w = h = 0
    if png[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    elif Image is not None:
        try:
            with Image.open(io.BytesIO(png)) as im:
                w, h = im.size
        except Exception:  # noqa: BLE001
            pass
    # Telegram rasm cheklovi: 10 MB va eni+bo'yi 10000 px dan oshmasin
    as_photo = len(png) < 9_500_000 and (w == 0 or (w + h < 10_000 and max(w, h) / max(min(w, h), 1) < 20))
    sent = None
    if as_photo:
        try:
            sent = await bot.send_photo(chat_id, file, caption=caption)
        except TelegramBadRequest:
            file = BufferedInputFile(png, filename=name)
    if sent is not None and sent.photo:
        token = shares.add(sent.photo[-1].file_id, name, kind="photo")
    else:
        sent = await bot.send_document(chat_id, file, caption=caption)
        token = shares.add(sent.document.file_id, name)
    rows = [[InlineKeyboardButton(text="↗️ Ulashish", switch_inline_query=share_query(token))]]
    if markup:
        rows += markup
    if chat_id > 0:
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=sent.message_id,
                                                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        except TelegramBadRequest:
            pass


async def send_view(bot: Bot, chat_id: int, loc: Path) -> None:
    await bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
    try:
        if loc.is_dir():
            dirs, files, err = await asyncio.to_thread(list_dir, loc)
            png = await asyncio.to_thread(preview.render_folder, loc, dirs, files)
            note = "papka"
        else:
            png, note = await asyncio.to_thread(preview.render_file, loc)
    except Exception as e:
        log.exception("Ko'rinish xatosi: %s", loc)
        await bot.send_message(chat_id, f"❌ Ko'rinishni olib bo'lmadi: {escape(str(e))}")
        return
    caption = f"{'📂' if loc.is_dir() else '📄'} {loc}\n🖼 {note}"
    extra = [[InlineKeyboardButton(text="🖥 To'liq ekran", callback_data=P("scr"))]]
    if loc.is_file():
        extra.insert(0, [InlineKeyboardButton(text="📥 Faylni yuborish", callback_data=P(f"s:{reg.id(loc)}:me"))])
    ext = "png" if png[:4] == b"\x89PNG" else "jpg"
    await send_photo_or_doc(bot, chat_id, png, f"korinish_{datetime.now():%H%M%S}.{ext}", caption, extra)
    log.info("Ko'rinish: chat=%s | %s", chat_id, loc)


async def send_desktop(bot: Bot, chat_id: int) -> None:
    await bot.send_chat_action(chat_id, ChatAction.UPLOAD_PHOTO)
    try:
        from screen import take_screenshot  # mss o'rnatilmagan bo'lsa ham bot ishlayversin
        png, _w, _h = await asyncio.to_thread(take_screenshot)
    except Exception as e:
        log.exception("Skrinshot xatosi")
        await bot.send_message(chat_id, f"❌ Skrinshot olib bo'lmadi: {escape(str(e))}")
        return
    now = datetime.now()
    caption = f"🖥 {cfg.agent_name + ' · ' if cfg.hub_mode else ''}to'liq ekran · {now:%d.%m.%Y %H:%M:%S}"
    await send_photo_or_doc(bot, chat_id, png, f"ekran_{now:%Y%m%d_%H%M%S}.png", caption)
    log.info("Skrinshot: chat=%s", chat_id)


@dp.callback_query(F.data == "scr")
async def cb_desktop(cq: CallbackQuery, bot: Bot):
    await cq.answer("🖥 To'liq ekran olinmoqda...")
    await send_desktop(bot, cq.message.chat.id if cq.message else cq.from_user.id)


@dp.callback_query(F.data.startswith("v:"))
async def cb_view(cq: CallbackQuery, bot: Bot):
    path = reg.path(cq.data[2:])
    if not allowed(path) or not path.exists():
        await cq.answer(STALE, show_alert=True)
        return
    user_loc[cq.from_user.id] = path
    await cq.answer("🖼 Tayyorlanmoqda...")
    await send_view(bot, cq.message.chat.id if cq.message else cq.from_user.id, path)


@dp.message(Command("izla"))
async def cmd_search(message: Message, command: CommandObject):
    if command.args:
        await do_search(message, command.args)
    else:
        waiting_search.add(message.from_user.id)
        await message.answer("🔎 Qidiruv so'zini yozing (fayl nomidan bir qismi):")


@dp.message(F.text == BTN_SEARCH)
async def btn_search(message: Message):
    waiting_search.add(message.from_user.id)
    await message.answer("🔎 Qidiruv so'zini yozing (fayl nomidan bir qismi):")


@dp.message(F.text & ~F.text.startswith("/"))
async def any_text(message: Message):
    if message.from_user.id in waiting_search:
        waiting_search.discard(message.from_user.id)
        await do_search(message, message.text)
    elif message.chat.type == "private":
        await message.answer("Tugmalardan birini tanlang yoki /yordam ni bosing.",
                             reply_markup=main_kb())


async def do_search(message: Message, query: str):
    query = query.strip()
    if len(query) < 2:
        await message.answer("Kamida 2 ta harf yozing.")
        return
    status = await message.answer(header() + f"🔎 «{escape(query)}» qidirilmoqda...")
    results, more = await asyncio.to_thread(search_files, cfg.allowed_dirs, query)
    if not results:
        await status.edit_text(header() + f"😕 «{escape(query)}» bo'yicha hech narsa topilmadi.")
        return
    kb = InlineKeyboardBuilder()
    for p, is_dir in results:
        if is_dir:
            kb.button(text=f"📁 {short(p.name)}", callback_data=P(f"d:{reg.id(p)}:0"))
        else:
            kb.button(text=f"📄 {short(p.name)}", callback_data=P(f"f:{reg.id(p)}"))
    kb.adjust(1)
    text = header() + f"🔎 «{escape(query)}» — {len(results)} ta natija"
    if more:
        text += "\n<i>Natijalar ko'p, aniqroq so'z yozsangiz yaxshi.</i>"
    await status.edit_text(text, reply_markup=kb.as_markup())


# ─────────────────────────── Tugmalar ───────────────────────────

STALE = "Bu tugma eskirgan (bot qayta ishga tushgan). /disk ni qayta bosing."


@dp.callback_query(F.data == "noop")
async def cb_noop(cq: CallbackQuery):
    await cq.answer()


@dp.callback_query(F.data == "r")
async def cb_roots(cq: CallbackQuery):
    user_loc.pop(cq.from_user.id, None)
    text, markup = roots_view()
    await safe_edit(cq.message, text, markup)
    await cq.answer()


@dp.callback_query(F.data.startswith("d:"))
async def cb_dir(cq: CallbackQuery):
    _, pid, page = cq.data.split(":")
    path = reg.path(pid)
    if not allowed(path) or not path.is_dir():
        await cq.answer(STALE, show_alert=True)
        return
    user_loc[cq.from_user.id] = path
    text, markup = await asyncio.to_thread(dir_view, path, int(page))
    await safe_edit(cq.message, text, markup)
    await cq.answer()


@dp.callback_query(F.data.startswith("f:"))
async def cb_file(cq: CallbackQuery):
    path = reg.path(cq.data[2:])
    if not allowed(path) or not path.is_file():
        await cq.answer(STALE, show_alert=True)
        return
    user_loc[cq.from_user.id] = path
    text, markup = file_view(path)
    await safe_edit(cq.message, text, markup)
    await cq.answer()


@dp.callback_query(F.data.startswith("s:"))
async def cb_send(cq: CallbackQuery, bot: Bot):
    _, fid, target = cq.data.split(":")
    path = reg.path(fid)
    if not allowed(path) or not path.is_file():
        await cq.answer(STALE, show_alert=True)
        return
    size = path.stat().st_size
    if cfg.max_file_mb and size > cfg.max_file_mb * 1024 * 1024:
        await cq.answer(f"Fayl {cfg.max_file_mb} MB dan katta (MAX_FILE_MB).", show_alert=True)
        return
    to_group = target == "gr"
    if to_group and not cfg.group_id:
        await cq.answer("GROUP_ID sozlanmagan.", show_alert=True)
        return

    chat_id = cfg.group_id if to_group else cq.from_user.id
    await cq.answer("⏳ Yuborilmoqda...")
    status = await bot.send_message(cq.from_user.id,
                                    f"⏳ <b>{escape(path.name)}</b> ({human_size(size)}) yuborilmoqda...")
    caption = f"📄 {path.name}"
    if to_group:
        caption += f"\n👤 {cq.from_user.full_name}"
    async def show(text: str) -> None:
        try:
            await status.edit_text(text)
        except TelegramBadRequest:
            pass

    try:
        await bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
        sent = await send_file(bot, chat_id, path, cfg.part_mb, caption=caption,
                               big=big_uploader, status=show)
    except Exception as e:
        log.exception("Yuborishda xato: %s", path)
        await status.edit_text(f"❌ <b>{escape(path.name)}</b> yuborilmadi:\n{escape(str(e))}")
        return
    log.info("Yuborildi: user=%s -> %s | %s (%s)", cq.from_user.id,
             "guruh" if to_group else "shaxsiy", path, human_size(size))

    if to_group:
        extra = f", {len(sent)} qismda" if len(sent) > 1 else ""
        await status.edit_text(f"✅ <b>{escape(path.name)}</b> guruhga yuborildi{extra}.")
        return
    await status.delete()
    await add_share_buttons(bot, chat_id, sent)


async def add_share_buttons(bot: Bot, chat_id: int, sent) -> None:
    """Har bir yuborilgan faylga (yoki qismga) «Ulashish» tugmasini qo'shadi."""
    for item in sent:
        if not item.file_id:
            continue
        token = shares.add(item.file_id, item.name)
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=item.message_id,
                                                reply_markup=share_markup(token))
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data.startswith("z:"))
async def cb_zip(cq: CallbackQuery, bot: Bot):
    """Papkani (ichki papkalari bilan) ZIP qilib yuboradi."""
    path = reg.path(cq.data[2:])
    if not allowed(path) or not path.is_dir():
        await cq.answer(STALE, show_alert=True)
        return
    await cq.answer("🗜 Tayyorlanmoqda...")
    uid = cq.from_user.id
    title = escape(path.name or str(path))
    status = await bot.send_message(uid, f"🗜 <b>{title}</b>\nFayllar sanalmoqda...")

    async def show(text: str) -> None:
        try:
            await status.edit_text(text)
        except TelegramBadRequest:
            pass

    try:
        files, total = await asyncio.to_thread(zipper.scan, path)
    except zipper.ZipTooBig as e:
        await show(f"❌ <b>{title}</b>: {escape(str(e))}. Ichidagi kichikroq papkani tanlang.")
        return
    if not files:
        await show(f"📭 <b>{title}</b> papkasi bo'sh.")
        return
    head = f"🗜 <b>{title}</b>\n{len(files)} ta fayl · {human_size(total)}"
    await show(f"{head}\nSiqilmoqda...")
    loop = asyncio.get_running_loop()

    def progress(done: int, all_: int) -> None:
        pct = done * 100 // max(all_, 1)
        bar = "▓" * (pct // 10) + "░" * (10 - pct // 10)
        asyncio.run_coroutine_threadsafe(show(f"{head}\nSiqilmoqda: {bar} {pct}%"), loop)

    tmpdir = Path(tempfile.mkdtemp(prefix="filebot_zip_"))
    out = tmpdir / f"{(path.name or path.drive.rstrip(':') or 'disk')}.zip"
    try:
        skipped = await asyncio.to_thread(zipper.make_zip, path, files, total, out, progress)
        caption = f"🗜 {out.name}\n📂 {path}\n📄 {len(files) - len(skipped)} ta fayl"
        sent = await send_file(bot, uid, out, cfg.part_mb, caption=caption,
                               big=big_uploader, status=show)
    except Exception as e:  # noqa: BLE001
        log.exception("ZIP xatosi: %s", path)
        await show(f"❌ <b>{title}</b> ZIP qilinmadi:\n{escape(str(e))}")
        return
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    log.info("ZIP yuborildi: user=%s | %s (%s ta fayl, %s)", uid, path, len(files), human_size(total))
    await status.delete()
    await add_share_buttons(bot, uid, sent)
    if skipped:
        lst = "\n".join(f"• {escape(x)}" for x in skipped[:10])
        more = f"\n… va yana {len(skipped) - 10} ta" if len(skipped) > 10 else ""
        await bot.send_message(uid, f"⚠️ {len(skipped)} ta fayl ochiq yoki band bo'lgani uchun "
                                    f"ZIP ga qo'shilmadi:\n{lst}{more}")


# ─────────────────────────── Ulashish (inline) ───────────────────────────

@dp.inline_query()
async def inline_share(iq: InlineQuery):
    token = iq.query.strip()
    item = shares.get(token) if token else None
    if not item:
        await iq.answer([], cache_time=0, is_personal=True)
        return
    if item.get("kind") == "photo":
        result = InlineQueryResultCachedPhoto(
            id=token[:64], photo_file_id=item["file_id"], title=item["name"],
            caption=f"🖥 {item['name']}", parse_mode=None)
        await iq.answer([result], cache_time=0, is_personal=True)
        log.info("Ulashildi: user=%s | %s", iq.from_user.id, item["name"])
        return
    result = InlineQueryResultCachedDocument(
        id=token[:64],
        title=item["name"],
        description="Bosing — fayl shu chatga yuboriladi",
        document_file_id=item["file_id"],
        caption=f"📄 {item['name']}",
        parse_mode=None,
    )
    await iq.answer([result], cache_time=0, is_personal=True)
    log.info("Ulashildi: user=%s | %s", iq.from_user.id, item["name"])


# ─────────────────────────── Yangilanish ───────────────────────────

main_bot: Bot | None = None
background: set[asyncio.Task] = set()


def update_repo() -> str:
    return os.getenv("UPDATE_REPO", "").strip() or updater.DEFAULT_REPO


async def notify_admins(text: str) -> None:
    if main_bot is None:
        return
    for uid in cfg.allowed_users:
        try:
            await main_bot.send_message(uid, f"{escape(cfg.agent_name)}: {escape(text)}")
        except Exception:  # noqa: BLE001
            pass


# ─────────────────────────── Katta fayllar (2 GB) ───────────────────────────

KATTA_HELP = (
    "📦 <b>2 GB gacha fayllarni bitta faylda yuborish</b>\n\n"
    "Oddiy bot 50 MB gacha fayl yubora oladi. 2 GB gacha yuborish uchun Telegram'dan "
    "ikkita kalit olinadi (bir marta, 3 daqiqa):\n\n"
    "1) https://my.telegram.org ga telefon raqamingiz bilan kiring\n"
    "2) <b>API development tools</b> → istalgan nom (masalan FileBot) → <b>Create application</b>\n"
    "3) Chiqqan <b>App api_id</b> va <b>App api_hash</b> ni shunday yuboring:\n\n"
    "<code>/kattafayl 1234567 0123456789abcdef0123456789abcdef</code>\n\n"
    "Xabaringiz kalit bilan birga darhol o'chiriladi."
)


@dp.message(Command("kattafayl"))
async def cmd_big(message: Message, command: CommandObject, bot: Bot):
    global big_uploader
    args = (command.args or "").split()
    if len(args) != 2:
        state = ("✅ Hozir yoqilgan: fayllar 2 GB gacha bitta faylda boradi.\n\n"
                 if big_uploader else "")
        await message.answer(state + KATTA_HELP, disable_web_page_preview=True)
        return
    try:  # kalit chatda qolmasin
        await message.delete()
    except TelegramBadRequest:
        pass
    api_id, api_hash = args
    if not api_id.isdigit() or not re.fullmatch(r"[0-9a-f]{32}", api_hash.lower()):
        await message.answer("❌ Noto'g'ri. api_id - faqat raqam, api_hash - 32 belgi (0-9, a-f).\n\n"
                             + KATTA_HELP, disable_web_page_preview=True)
        return
    if BigUploader is None:
        await message.answer("❌ Bu kompyuterda telethon kutubxonasi o'rnatilmagan. "
                             "Botni /yangilash qiling yoki o'rnatuvchini qayta ishga tushiring.")
        return
    status = await message.answer("⏳ Kalitlar tekshirilmoqda...")
    trial = BigUploader(int(api_id), api_hash.lower(), cfg.token,
                        BASE_DIR / "data" / f"mtproto_{cfg.agent_id or 'bot'}.session")
    try:
        await trial._get_client()
    except Exception as e:  # noqa: BLE001
        log.warning("Katta fayl kalitlari ishlamadi: %s", e)
        await trial.close()
        await status.edit_text(f"❌ Telegram bu kalitlarni qabul qilmadi: {escape(str(e))}\n\n"
                               "my.telegram.org dagi qiymatlarni qayta tekshiring.")
        return
    old, big_uploader = big_uploader, trial
    if old is not None:
        await old.close()
    cfg.api_id, cfg.api_hash = int(api_id), api_hash.lower()
    save_env({"API_ID": api_id, "API_HASH": api_hash.lower(), "MAX_FILE_MB": "0"})
    log.info("Katta fayllar rejimi yoqildi (/kattafayl)")
    await status.edit_text("✅ Tayyor! Endi fayllar <b>2 GB gacha bitta faylda</b> yuboriladi.\n"
                           "2 GB dan kattasi 2 GB lik qismlarga bo'linadi.")


def save_env(values: dict[str, str]) -> None:
    """config.env dagi qiymatlarni yangilaydi (bo'lmasa qo'shadi)."""
    env = BASE_DIR / "config.env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    out, seen = [], set()
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in values.items() if k not in seen]
    tmp = env.with_suffix(".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, env)


@dp.message(Command("yangilash", "versiya"))
async def cmd_update(message: Message):
    status = await message.answer(f"💻 {escape(cfg.agent_name)} · v{VERSION}\n🔎 Yangilanish tekshirilmoqda...")
    try:
        info = await updater.check(update_repo())
    except Exception as e:  # noqa: BLE001
        await status.edit_text(f"💻 {escape(cfg.agent_name)} · v{VERSION}\n⚠️ Tekshirib bo'lmadi: {escape(str(e))}")
        return
    if not info:
        await status.edit_text(f"💻 {escape(cfg.agent_name)} · v{VERSION}\n✅ Eng so'nggi versiya o'rnatilgan.")
        return
    await status.edit_text(f"💻 {escape(cfg.agent_name)}\n🔄 v{VERSION} → v{info['version']} yuklanmoqda...\n"
                           "Bot bir daqiqada qayta ishga tushadi.")
    try:
        await updater.run_update(info, notify_admins)
    except Exception as e:  # noqa: BLE001
        log.exception("Yangilash xatosi")
        await message.answer(f"❌ Yangilab bo'lmadi: {escape(str(e))}")


# ─────────────────────────── Ishga tushirish ───────────────────────────

def setup_logging() -> None:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    file_h = RotatingFileHandler(log_dir / "bot.log", maxBytes=5_000_000, backupCount=3,
                                 encoding="utf-8")
    file_h.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_h)
    if sys.stdout is not None:  # .exe oynasiz ishlaganda konsol bo'lmaydi
        console_h = logging.StreamHandler(sys.stdout)
        console_h.setFormatter(fmt)
        root.addHandler(console_h)


def single_instance() -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        log.error("Bot allaqachon ishlab turibdi. Ikkinchi nusxa yopildi.")
        sys.exit(EXIT_ALREADY_RUNNING)
    return s


async def main() -> None:
    global cfg
    setup_logging()
    try:
        cfg = load_config()
    except ConfigError as e:
        log.error("SOZLAMA XATOSI: %s", e)
        sys.exit(EXIT_CONFIG_ERROR)
    _lock = single_instance()  # noqa: F841 — jarayon tugaguncha ushlab turiladi
    updater.cleanup_old()
    log.info("FileBot v%s (%s)", VERSION, "exe" if updater.is_frozen() else "python")

    for observer in (dp.message, dp.callback_query, dp.inline_query):
        observer.outer_middleware(AccessMiddleware())

    if cfg.hub_mode and (not cfg.token or not cfg.allowed_users):
        # O'rnatuvchi orqali qo'shilgan kompyuter: token va ruxsatlar hub'dan olinadi
        try:
            info = await hub_bootstrap(cfg.hub_url, cfg.agent_id, cfg.agent_key)
        except HubRejected as e:
            log.error("Hub: %s. Kompyuterni qayta qo'shish uchun o'rnatuvchini qayta ishga tushiring.", e)
            sys.exit(EXIT_CONFIG_ERROR)
        cfg.token = cfg.token or info["token"]
        if not cfg.api_id and info.get("api_id") and info.get("api_hash"):
            cfg.api_id, cfg.api_hash = int(info["api_id"]), str(info["api_hash"])
        cfg.allowed_users = cfg.allowed_users or {int(u) for u in info.get("users", [])}
        if info.get("name"):
            cfg.agent_name = info["name"]

    global big_uploader
    for err in OPTIONAL_ERRORS:
        log.warning("O'chirilgan imkoniyat - %s. Tuzatish: python -m pip install -r requirements.txt", err)
    if cfg.api_id and cfg.api_hash and BigUploader is not None:
        big_uploader = BigUploader(cfg.api_id, cfg.api_hash, cfg.token,
                                   BASE_DIR / "data" / f"mtproto_{cfg.agent_id or 'bot'}.session")
        log.info("Katta fayllar rejimi yoqilgan: 2 GB gacha bitta faylda, hajm cheklovi yo'q")
    else:
        log.info("Katta fayllar rejimi o'chiq (API_ID yo'q): 49 MB dan kattasi 45 MB lik qismlarda")

    session = None
    if cfg.bot_api_url:
        session = AiohttpSession(api=TelegramAPIServer.from_base(cfg.bot_api_url))
    bot = Bot(cfg.token, session=session,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    log.info("Bot: @%s | rejim: %s | papkalar: %s", me.username,
             f"ko'p kompyuter ({cfg.agent_id})" if cfg.hub_mode else "bitta kompyuter",
             ", ".join(str(p) for p in cfg.allowed_dirs))

    if cfg.notify_start:
        for uid in cfg.allowed_users:
            try:
                await bot.send_message(uid, f"🟢 {escape(cfg.agent_name)}: bot ishga tushdi "
                                            f"(v{VERSION}, {datetime.now():%d.%m.%Y %H:%M})")
            except Exception:
                pass  # foydalanuvchi hali botga /start bosmagan

    global main_bot
    main_bot = bot
    if os.getenv("AUTO_UPDATE", "1").strip() != "0":
        background.add(asyncio.create_task(updater.update_loop(notify_admins, update_repo())))

    if cfg.hub_mode:
        # Buyruqlar ro'yxatini hub o'rnatadi; xabarlar hub orqali keladi
        try:
            await run_hub_client(bot, dp, cfg.hub_url, cfg.agent_id, cfg.agent_key)
        except HubRejected as e:
            log.error("Hub: %s. Bot to'xtatildi.", e)
            sys.exit(EXIT_CONFIG_ERROR)
        return

    webhook = await bot.get_webhook_info()
    if webhook.url:
        log.error("Bu bot hub'ga ulangan (webhook bor). Bitta kompyuter rejimida ishlatish "
                  "uchun config.env ga HUB_URL ni yozing yoki boshqa bot tokenini oling.")
        sys.exit(EXIT_CONFIG_ERROR)
    await bot.set_my_commands([
        BotCommand(command="disk", description="Disk va papkalar"),
        BotCommand(command="izla", description="Fayl qidirish"),
        BotCommand(command="ekran", description="Ekran skrinshoti"),
        BotCommand(command="id", description="Chat ID"),
        BotCommand(command="kattafayl", description="2 GB gacha fayl yuborishni yoqish"),
        BotCommand(command="yangilash", description="Yangilanishni tekshirish"),
        BotCommand(command="yordam", description="Yordam"),
    ])
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
