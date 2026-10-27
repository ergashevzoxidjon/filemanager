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


async def run_hub_client(bot: Bot, dp: Dispatcher, hub_url: str, agent_id: str,
                         agent_key: str) -> None:
    params = {"a": "poll", "agent": agent_id}
    headers = {"X-Agent-Key": agent_key}
    timeout = aiohttp.ClientTimeout(total=45)
    tasks: set[asyncio.Task] = set()
    fails = 0

    async with aiohttp.ClientSession(timeout=timeout) as session:
        log.info("Hub'ga ulanilmoqda: %s (kompyuter: %s)", hub_url, agent_id)
        while True:
            try:
                async with session.get(hub_url, params=params, headers=headers) as resp:
                    if resp.status == 403:
                        log.error("Hub AGENT_ID yoki AGENT_KEY ni qabul qilmadi. "
                                  "config.env va hub config.php ni tekshiring.")
                        await asyncio.sleep(60)
                        continue
                    data = await resp.json(content_type=None)
                if not data.get("ok"):
                    raise RuntimeError(data.get("error", "noma'lum xato"))
                if fails:
                    log.info("Hub bilan aloqa tiklandi")
                fails = 0
                for raw in data.get("updates", []):
                    update = Update.model_validate(raw, context={"bot": bot})
                    task = asyncio.create_task(_handle(bot, dp, update))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
            except asyncio.CancelledError:
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
