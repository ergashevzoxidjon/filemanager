"""Ofis fayl-bot (agent): shu kompyuterdagi fayllarni telefondan Telegram orqali boshqarish.

Ikki rejim bor:
  • Bitta kompyuter — HUB_URL bo'sh. Bot Telegram'dan xabarlarni o'zi oladi.
  • Ko'p kompyuter — HUB_URL to'ldirilgan. Xabarlar markaziy hub orqali keladi,
    telefonda «💻 Kompyuter» tugmasi bilan kerakli kompyuterni tanlaysiz.

Ishga tushirish:  python bot.py
"""
import asyncio
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
from hub_client import run_hub_client
from screen import take_screenshot
from search import search_files
from sender import send_file
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
        "🖥 /ekran — kompyuter ekranini rasmga olish\n"
        "🆔 /id — shu chat ID'sini bilish\n\n"
        "Faylni bosing → «📥 Menga yuborish».\n"
        "Fayl kelgach, ostidagi «↗️ Ulashish» tugmasi bilan uni istalgan "
        "chat, guruh yoki kanalga yuborasiz.\n"
        "49 MB dan katta fayllar bo'laklarga bo'lib yuboriladi."
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
    if st.st_size > cfg.max_file_mb * 1024 * 1024:
        text += f"\n\n⚠️ Fayl {cfg.max_file_mb} MB dan katta, yuborib bo'lmaydi."
    fid = reg.id(path)
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 Menga yuborish", callback_data=P(f"s:{fid}:me"))
    if cfg.group_id:
        kb.button(text="👥 Guruhga yuborish", callback_data=P(f"s:{fid}:gr"))
    kb.button(text="⬅️ Orqaga", callback_data=P(f"d:{reg.id(path.parent)}:0"))
    kb.adjust(2 if cfg.group_id else 1, 1)
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
    text, markup = roots_view()
    await message.answer(text, reply_markup=markup)


@dp.message(Command("id"))
async def cmd_id(message: Message):
    await message.answer(f"🆔 Chat ID: <code>{message.chat.id}</code>\n"
                         f"👤 Sizning ID: <code>{message.from_user.id}</code>")


@dp.message(Command("ekran"))
@dp.message(F.text == BTN_SCREEN)
async def cmd_screen(message: Message, bot: Bot):
    await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_PHOTO)
    try:
        png, w, h = await asyncio.to_thread(take_screenshot)
    except Exception as e:
        log.exception("Skrinshot xatosi")
        await message.answer(f"❌ Skrinshot olib bo'lmadi: {escape(str(e))}")
        return
    now = datetime.now()
    name = f"ekran_{now:%Y%m%d_%H%M%S}.png"
    caption = f"🖥 {cfg.agent_name if cfg.hub_mode else ''} {now:%d.%m.%Y %H:%M:%S}".replace("  ", " ")
    file = BufferedInputFile(png, filename=name)
    # Telegram rasm cheklovi: 10 MB va eni+bo'yi 10000 px dan oshmasin
    if len(png) < 9_500_000 and w + h < 10_000 and max(w, h) / max(min(w, h), 1) < 20:
        sent = await message.answer_photo(file, caption=caption)
    else:
        sent = await message.answer_document(file, caption=caption)
    if message.chat.type == "private":
        if sent.photo:
            token = shares.add(sent.photo[-1].file_id, name, kind="photo")
        else:
            token = shares.add(sent.document.file_id, name)
        await sent.edit_reply_markup(reply_markup=share_markup(token))
    log.info("Skrinshot: user=%s chat=%s", message.from_user.id, message.chat.id)


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
    text, markup = await asyncio.to_thread(dir_view, path, int(page))
    await safe_edit(cq.message, text, markup)
    await cq.answer()


@dp.callback_query(F.data.startswith("f:"))
async def cb_file(cq: CallbackQuery):
    path = reg.path(cq.data[2:])
    if not allowed(path) or not path.is_file():
        await cq.answer(STALE, show_alert=True)
        return
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
    if size > cfg.max_file_mb * 1024 * 1024:
        await cq.answer(f"Fayl {cfg.max_file_mb} MB dan katta.", show_alert=True)
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
    try:
        await bot.send_chat_action(chat_id, ChatAction.UPLOAD_DOCUMENT)
        sent = await send_file(bot, chat_id, path, cfg.part_mb, caption=caption)
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
    # Har bir faylga (yoki qismga) «Ulashish» tugmasini qo'shamiz
    for i, msg in enumerate(sent, 1):
        if not msg.document:
            continue
        name = path.name if len(sent) == 1 else f"{path.name}.{i:03d}"
        token = shares.add(msg.document.file_id, name)
        try:
            await msg.edit_reply_markup(reply_markup=share_markup(token))
        except TelegramBadRequest:
            pass


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


# ─────────────────────────── Ishga tushirish ───────────────────────────

def setup_logging() -> None:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    file_h = RotatingFileHandler(log_dir / "bot.log", maxBytes=5_000_000, backupCount=3,
                                 encoding="utf-8")
    file_h.setFormatter(fmt)
    console_h = logging.StreamHandler(sys.stdout)
    console_h.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_h)
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

    for observer in (dp.message, dp.callback_query, dp.inline_query):
        observer.outer_middleware(AccessMiddleware())

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
                                            f"({datetime.now():%d.%m.%Y %H:%M})")
            except Exception:
                pass  # foydalanuvchi hali botga /start bosmagan

    if cfg.hub_mode:
        # Buyruqlar ro'yxatini hub o'rnatadi; xabarlar hub orqali keladi
        await run_hub_client(bot, dp, cfg.hub_url, cfg.agent_id, cfg.agent_key)
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
        BotCommand(command="yordam", description="Yordam"),
    ])
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
