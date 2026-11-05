import asyncio
import logging
import socket
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, FSInputFile
from aiogram.client.session.aiohttp import AiohttpSession
import pandas as pd
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage

from app.config import settings
from app.agent.nlu import parse_user_request
from app.avito.collector import AvitoAccessBlockedError, AvitoCollector
from app.ocr.engine import extract_text_from_image
from app.extraction.regex_extractor import extract_all
from app.storage.db import init_db, create_job, get_cached_listing, save_listing_to_cache

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

dp = Dispatcher()
MAX_PHOTOS = 5  # Сколько колонок с фото создавать в Excel

def format_val(val_list):
    if not val_list: return "-"
    return ", ".join(val_list)

async def safe_edit(message: Message, text: str):
    try:
        await message.edit_text(text)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я локальный агент для парсинга Avito и OCR.\n"
        "Напиши, что будем искать (например: «найди 3 iphone 13 на avito, нужны imei»)."
    )

@dp.message(F.text)
async def handle_query(message: Message):
    user_text = message.text
    status_msg = await message.answer("⏳ Анализирую запрос...")

    parsed = await parse_user_request(user_text)
    if not parsed.get("query"):
        await safe_edit(status_msg, "Я не совсем понял, что искать. Уточните запрос.")
        return
        
    job_id = await create_job(user_id=message.from_user.id, query=parsed["query"])
    limit = parsed["limit"] or settings.avito_max_items_default
    query = parsed["query"]

    await safe_edit(status_msg, f"✅ Задача #{job_id} создана. Ищу на Avito...")

    collector = AvitoCollector()
    
    try:
        listings = await collector.search(query, limit=limit)
        if not listings:
            await safe_edit(status_msg, "❌ Ничего не найдено.")
            return
            
        await safe_edit(status_msg, f"🔍 Найдено {len(listings)} объявлений. Проверяю кэш...")
        
        rows = []
        for idx, listing in enumerate(listings):
            avito_id = listing.get("avito_id")
            
            # 1. ПРОВЕРЯЕМ КЭШ
            cached_data = await get_cached_listing(avito_id)
            
            if cached_data:
                logger.info(f"♻️ Объявление {avito_id} найдено в кэше. Пропускаем OCR.")
                await safe_edit(status_msg, f"♻️ [{idx+1}/{len(listings)}] Взято из кэша: {listing['title'][:30]}...")
                
                # Для Excel нам все равно нужны фото, поэтому скачиваем их (но без OCR)
                images = await collector.get_images_from_listing(listing["url"])
                downloaded_photos = []
                for i, image_url in enumerate(images[:MAX_PHOTOS]):
                    save_path = Path(settings.tmp_dir) / f"job_{job_id}_item_{idx}_cached_img_{i}.jpg"
                    success = await collector.download_image(image_url, str(save_path))
                    downloaded_photos.append(save_path if success else None)
                
                all_entities = cached_data["entities"]
                
            else:
                # 2. ЕСЛИ НЕТ В КЭШЕ - ПАРСИМ
                logger.info(f"⬇️ Объявление {avito_id} отсутствует в кэше. Запускаем OCR...")
                await safe_edit(status_msg, f"⚙️ [{idx+1}/{len(listings)}] Обработка (OCR): {listing['title'][:30]}...")
                
                images = await collector.get_images_from_listing(listing["url"])
                all_entities = {"IMEI": [], "SN": [], "MAC": [], "PASSWORD": []}
                downloaded_photos = []
                
                for i, image_url in enumerate(images[:MAX_PHOTOS]):
                    save_path = Path(settings.tmp_dir) / f"job_{job_id}_item_{idx}_img_{i}.jpg"
                    success = await collector.download_image(image_url, str(save_path))
                    
                    if success:
                        downloaded_photos.append(save_path)
                        ocr_res = extract_text_from_image(str(save_path))
                        entities = extract_all(ocr_res["combined"])
                        for key in all_entities:
                            all_entities[key].extend(entities[key])
                    else:
                        downloaded_photos.append(None)
                
                # Временная ошибка загрузки не должна навсегда кэшировать неполный результат.
                if downloaded_photos and all(downloaded_photos):
                    await save_listing_to_cache(job_id, avito_id, listing["url"], listing["title"], all_entities)
                        
            # Формируем строку
            row = {
                "Ссылка": listing["url"],
                "Заголовок": listing["title"],
                "SN": format_val(list(set(all_entities["SN"]))),
                "IMEI": format_val(list(set(all_entities["IMEI"]))),
                "MAC": format_val(list(set(all_entities["MAC"]))),
                "Пароль": format_val(list(set(all_entities["PASSWORD"]))),
                "_photos": downloaded_photos
            }
            rows.append(row)

        await safe_edit(status_msg, "📊 Формирую Excel-отчет...")
        
        df = pd.DataFrame([{k: v for k, v in r.items() if k != "_photos"} for r in rows])
        for i in range(MAX_PHOTOS):
            df[f"Фото {i+1}"] = "-"
            
        output_file = Path(settings.tmp_dir) / f"report_{job_id}.xlsx"
        df.to_excel(output_file, index=False)

        wb = load_workbook(output_file)
        ws = wb.active
        
        photo_start_col = 7
        for i in range(MAX_PHOTOS):
            col_letter = get_column_letter(photo_start_col + i)
            ws.column_dimensions[col_letter].width = 20
        
        for row_idx, row_data in enumerate(rows, start=2):
            ws.row_dimensions[row_idx].height = 100
            for photo_idx, photo_path in enumerate(row_data["_photos"]):
                col_letter = get_column_letter(photo_start_col + photo_idx)
                cell_coord = f'{col_letter}{row_idx}'
                
                if photo_path and photo_path.exists():
                    try:
                        pil_img = PILImage.open(photo_path)
                        excel_img_path = Path(settings.tmp_dir) / f"excel_{job_id}_{row_idx}_{photo_idx}.png"
                        pil_img.convert("RGB").save(excel_img_path, "PNG")
                        
                        img = XLImage(str(excel_img_path))
                        img.width = 120
                        img.height = 90
                        ws.add_image(img, cell_coord)
                        ws[cell_coord].value = ""
                    except Exception as e:
                        logger.error(f"Ошибка вставки фото {photo_path}: {e}")
                        ws[cell_coord].value = "-"
                else:
                    ws[cell_coord].value = "-"
                    
        wb.save(output_file)

        await safe_edit(status_msg, "📤 Отправляю файл...")
        await message.answer_document(
            document=FSInputFile(output_file),
            caption=f"✅ Отчет по запросу «{query}» готов!\nНайдено: {len(rows)}"
        )
        try:
            await status_msg.delete()
        except Exception:
            pass

    except AvitoAccessBlockedError:
        await safe_edit(status_msg, "❌ Avito ограничил доступ с текущего IP. Проверьте прокси в PROXY_URL или пройдите проверку Avito в браузере.")
    except Exception as e:
        logger.exception("Ошибка в пайплайне")
        await safe_edit(status_msg, f"❌ Ошибка: {e}")


async def main():
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    await init_db()
    logger.info("Запуск бота...")

    session = AiohttpSession(proxy=settings.telegram_proxy_url or None, timeout=120.0)
    session._connector_init.update(family=socket.AF_INET, force_close=True)
    bot = Bot(token=settings.bot_token, session=session)
    try:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
        except Exception as e:
            logger.warning("Не удалось удалить вебхук: %s", e)
        await dp.start_polling(bot)
    finally:
        await session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
