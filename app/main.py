import asyncio
import logging
import aiohttp
import socket

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.client.session.aiohttp import AiohttpSession

from app.config import settings
from app.storage.db import init_db, create_job
from app.agent.nlu import parse_user_request

# Настраиваем логирование так, чтобы мы видели ВСЁ
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    logger.info(f"Получен /start от {message.from_user.id}")
    try:
        await message.answer(
            "Привет! Я локальный агент для парсинга Avito и OCR.\n"
            "Напиши, что будем искать (например: «найди 10 iphone 13 на avito, нужны imei»)."
        )
        logger.info("Ответ на /start отправлен успешно.")
    except Exception as e:
        logger.error(f"Ошибка при отправке /start: {e}")

@dp.message(F.text)
async def handle_query(message: Message):
    logger.info(f"Получено сообщение: {message.text}")
    
    try:
        logger.info("Отправка статуса 'Анализирую...'")
        status_msg = await message.answer("⏳ Анализирую запрос с помощью локального ИИ...")
        logger.info("Статус отправлен. Ждем Ollama...")
    except Exception as e:
        logger.error(f"Не удалось отправить статус: {e}")
        return

    parsed = await parse_user_request(message.text)
    logger.info(f"Ollama ответила: {parsed}")
    
    if not parsed.get("query"):
        await status_msg.edit_text("Я не совсем понял, что вы хотите найти. Уточните запрос.")
        return
        
    job_id = await create_job(user_id=message.from_user.id, query=parsed["query"])
    logger.info(f"Задача создана: ID {job_id}")
    
    fields_str = ", ".join(parsed["fields"]) if parsed["fields"] else "все поля"
    limit = parsed["limit"] or settings.avito_max_items_default
    
    try:
        await status_msg.edit_text(
            f"✅ **Задача #{job_id} создана!**\n\n"
            f"🔎 Искать: `{parsed['query']}`\n"
            f"📊 Количество: {limit}\n"
            f"🎯 Извлекать: {fields_str}\n\n"
            f"*(Парсинг Avito и OCR скоро будут добавлены)*"
        )
        logger.info("Финальный ответ отправлен успешно.")
    except Exception as e:
        logger.error(f"Не удалось отправить финальный ответ: {e}")


async def main():
    await init_db()
    logger.info("База данных инициализирована.")
    
    # Максимально жесткая настройка сессии
    # Отключаем IPv6, отключаем keep-alive, ставим таймаут по умолчанию
    connector = aiohttp.TCPConnector(
        family=socket.AF_INET, 
        force_close=True,
        enable_cleanup_closed=True
    )
    session = AiohttpSession(timeout=30.0)
    session._connector = connector
    
    bot = Bot(token=settings.bot_token, session=session)
    
    try:
        logger.info("Пытаемся удалить вебхук...")
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Вебхук удален.")
    except Exception as e:
        logger.warning(f"Не удалось удалить вебхук: {e}")
        
    logger.info("Запускаем polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")