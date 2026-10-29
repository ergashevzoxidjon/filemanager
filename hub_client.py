"""Ko'p kompyuter rejimi: Telegram xabarlarini markaziy hub'dan olish.

Bitta botni bir nechta kompyuter bir vaqtda «tinglay» olmaydi. Shuning uchun Telegram
xabarlarni hub'ga yuboradi, hub esa ularni foydalanuvchi tanlagan kompyuterga uzatadi.
Har bir kompyuter hub'dan o'ziga tegishli xabarlarni so'rab turadi (long polling),
javobni esa to'g'ridan-to'g'ri Telegram'ga yuboradi.
"""
import asyncio
import logging

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import Update

log = logging.getLogger("ofisbot")


POLL_ACTIVE = 1.0   # soniya
POLL_IDLE = 3.0


class HubRejected(Exception):
    """Kompyuter hub'da rad etilgan yoki o'chirilgan."""


async def hub_bootstrap(hub_url: str, agent_id: str, agent_key: str) -> dict:
    """Hub'dan bot tokeni va foydalanuvchilar ro'yxatini oladi.
    Kompyuter hali tasdiqlanmagan bo'lsa, admin Telegram'da qabul qilguncha kutadi."""
    headers = {"X-Agent-Key": agent_key}
    timeout = aiohttp.ClientTimeout(total=30)
    told = False
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            try:
                async with session.get(hub_url, params={"a": "bootstrap", "agent": agent_id},
                                       headers=headers) as resp:
                    data = await resp.json(content_type=None)
            except Exception as e:  # internet yo'q va h.k.
                log.warning("Hub'ga ulanib bo'lmadi (%s). 30 sekunddan keyin qayta urinish.", e)
                await asyncio.sleep(30)
                continue
            if data.get("ok"):
                return data
            err = data.get("error")
            if err == "pending":
                if not told:
                    log.info("Telegram'da «✅ Qabul qilish» tugmasi bosilishi kutilmoqda...")
                    told = True
                await asyncio.sleep(10)
                continue
            raise HubRejected("rad etilgan" if err == "rejected" else "kalit hub'da topilmadi")


async def run_hub_client(bot: Bot, dp: Dispatcher, hub_url: str, agent_id: str,
                         agent_key: str) -> None:
    # v=2: hub kutib o'tirmaydi, darhol javob beradi. Biz o'zimiz qisqa tanaffus bilan so'raymiz:
    # faol paytda (oxirgi 2 daqiqada buyruq bo'lgan) - 1 soniyada, bo'sh paytda - 3 soniyada bir.
    params = {"a": "poll", "agent": agent_id, "v": "2", "wait": "0"}
    headers = {"X-Agent-Key": agent_key}
    timeout = aiohttp.ClientTimeout(total=30)
    last_activity = 0.0
    loop = asyncio.get_running_loop()
    tasks: set[asyncio.Task] = set()
    fails = 0

    async with aiohttp.ClientSession(timeout=timeout) as session:
        log.info("Hub'ga ulanilmoqda: %s (kompyuter: %s)", hub_url, agent_id)
        while True:
            try:
                async with session.get(hub_url, params=params, headers=headers) as resp:
                    if resp.status == 403:
                        err = (await resp.json(content_type=None)).get("error")
                        if err in ("rejected", "auth"):
                            raise HubRejected("hub bu kompyuterni qabul qilmadi (o'chirilgan yoki rad etilgan)")
                        log.error("Hub kompyuterni hali tasdiqlamagan (%s)", err)
                        await asyncio.sleep(60)
                        continue
                    data = await resp.json(content_type=None)
                if not data.get("ok"):
                    raise RuntimeError(data.get("error", "noma'lum xato"))
                if fails:
                    log.info("Hub bilan aloqa tiklandi")
                fails = 0
                updates = data.get("updates", [])
                if updates:
                    last_activity = loop.time()
                for raw in updates:
                    update = Update.model_validate(raw, context={"bot": bot})
                    task = asyncio.create_task(_handle(bot, dp, update))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
                await asyncio.sleep(POLL_ACTIVE if loop.time() - last_activity < 120 else POLL_IDLE)
            except (asyncio.CancelledError, HubRejected):
                raise
            except Exception as e:
                fails += 1
                wait = min(5 * fails, 60)
                if fails <= 3 or fails % 20 == 0:
                    log.warning("Hub bilan aloqa yo'q (%s). %s sekunddan keyin qayta urinish.",
                                e, wait)
                await asyncio.sleep(wait)


async def _handle(bot: Bot, dp: Dispatcher, update: Update) -> None:
    try:
        await dp.feed_update(bot, update)
    except Exception:
        log.exception("Xabarni qayta ishlashda xato")
