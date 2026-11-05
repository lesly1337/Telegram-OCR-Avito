"""Проверка подключения Telegram и страны выхода прокси Avito без вывода секретов."""

import asyncio
import socket

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from curl_cffi import requests

from app.avito.collector import AvitoCollector
from app.config import settings


async def check_telegram() -> bool:
    route = "прокси" if settings.telegram_proxy_url else "напрямую"
    session = None
    try:
        session = AiohttpSession(proxy=settings.telegram_proxy_url or None, timeout=15)
        session._connector_init.update(family=socket.AF_INET, force_close=True)
        bot = Bot(token=settings.bot_token, session=session)
        await bot.get_me()
        print(f"Telegram ({route}): подключение успешно")
        return True
    except Exception as exc:
        # Тексты сетевых ошибок могут содержать URL с паролем или токен бота.
        print(f"Telegram ({route}): ошибка {type(exc).__name__}")
        return False
    finally:
        if session is not None:
            await session.close()


async def check_avito_country() -> bool:
    collector = AvitoCollector()
    if not collector.proxy_url:
        print("Avito: PROXY_URL не задан")
        return False
    try:
        response = await asyncio.to_thread(
            requests.get, "https://ipwho.is/", timeout=15, **collector._curl_proxy_options()
        )
        response.raise_for_status()
        data = response.json()
        country = data.get("country_code") if data.get("success") else None
        if not country:
            print("Avito: сервис геолокации не определил страну")
            return False
        print(f"Avito: страна выхода по данным ipwho.is — {country}")
        return country == "RU"
    except Exception as exc:
        print(f"Avito: ошибка проверки геолокации {type(exc).__name__}")
        return False


async def main() -> int:
    telegram_ok, avito_ok = await asyncio.gather(check_telegram(), check_avito_country())
    return 0 if telegram_ok and avito_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
