import asyncio
import logging
import aiohttp
import socket
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile
from aiogram.client.session.aiohttp import AiohttpSession
import pandas as pd
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage

from app.config import settings
from app.storage.db import init_db, create_job
from app.agent.nlu import parse_user_request
from app.avito.collector import AvitoCollector
from app.ocr.engine import extract_text_from_image
from app.extraction.regex_extractor import extract_all

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

dp = Dispatcher()
MAX_PHOTOS = 5  # Сколько колонок с фото создавать в Excel

def format_val(val_list):
    if not val_list: return "-"
    return ", ".join(val_list)

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я локальный агент для парсинга Avito и OCR.\n"
        "Напиши, что будем искать (например: «найди 3 iphone 13 на avito, нужны imei»)."
    )

@dp.message(F.text)
async def handle_query(message: Message):
    user_text = message.text
    status_msg = await message.answer("⏳ Анализирую запрос с помощью локального ИИ...")

    # 1. Парсим запрос через Ollama
    parsed = await parse_user_request(user_text)
    if not parsed.get("query"):
        await status_msg.edit_text("Я не совсем понял, что искать. Уточните запрос.")
        return
        
    job_id = await create_job(user_id=message.from_user.id, query=parsed["query"])
    limit = parsed["limit"] or settings.avito_max_items_default
    query = parsed["query"]

    await status_msg.edit_text(
        f"✅ **Задача #{job_id} создана!**\n"
        f"🔎 Искать: `{query}`\n"
        f"📊 Количество: {limit}\n\n"
        f"⏳ Запускаю парсер Avito (это займет время)..."
    )

    collector = AvitoCollector()
    
    try:
        # 2. Ищем объявления
        listings = await collector.search(query, limit=limit)
        if not listings:
            await status_msg.edit_text("❌ Ничего не найдено (Avito заблокировал или пустая выдача).")
            return
            
        await status_msg.edit_text(f"🔍 Найдено {len(listings)} объявлений. Обрабатываю фото и запускаю OCR...")
        
        rows = []
        for idx, listing in enumerate(listings):
            await status_msg.edit_text(f"⚙️ Обработка {idx+1} из {len(listings)}: {listing['title'][:30]}...")
            
            images = await collector.get_images_from_listing(listing["url"])
            all_entities = {"IMEI": [], "SN": [], "MAC": [], "PASSWORD": []}
            downloaded_photos = []
            
            # Скачиваем и обрабатываем до MAX_PHOTOS фото
            for i, image_url in enumerate(images[:MAX_PHOTOS]):
                save_path = Path(settings.tmp_dir) / f"job_{job_id}_item_{idx}_img_{i}.jpg"
                success = await collector.download_image(image_url, str(save_path))
                
                if success:
                    downloaded_photos.append(save_path)
                    # Запускаем OCR
                    ocr_res = extract_text_from_image(str(save_path))
                    entities = extract_all(ocr_res["combined"])
                    for key in all_entities:
                        all_entities[key].extend(entities[key])
                else:
                    downloaded_photos.append(None)
                        
            # Формируем строку для отчета
            row = {
                "Ссылка": listing["url"],
                "Заголовок": listing["title"],
                "SN": format_val(list(set(all_entities["SN"]))),
                "IMEI": format_val(list(set(all_entities["IMEI"]))),
                "MAC": format_val(list(set(all_entities["MAC"]))),
                "Пароль": format_val(list(set(all_entities["PASSWORD"]))),
                "_photos": downloaded_photos  # Скрытое поле для путей к фото
            }
            rows.append(row)

        # 3. Генерируем XLSX
        await status_msg.edit_text("📊 Формирую Excel-отчет...")
        
        # Создаем DataFrame без скрытого поля _photos
        df = pd.DataFrame([{k: v for k, v in r.items() if k != "_photos"} for r in rows])
        
        # Добавляем пустые колонки для фото
        for i in range(MAX_PHOTOS):
            df[f"Фото {i+1}"] = "-"
            
        output_file = Path(settings.tmp_dir) / f"report_{job_id}.xlsx"
        df.to_excel(output_file, index=False)

        # 4. Вставляем картинки в Excel
        wb = load_workbook(output_file)
        ws = wb.active
        
        # Настраиваем ширину колонок для фото (они идут после текстовых данных, начиная с колонки G)
        # A=1, B=2, C=3, D=4, E=5, F=6, G=7
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
                        # Конвертируем webp в png (иначе openpyxl падает)
                        pil_img = PILImage.open(photo_path)
                        excel_img_path = Path(settings.tmp_dir) / f"excel_{job_id}_{row_idx}_{photo_idx}.png"
                        pil_img.convert("RGB").save(excel_img_path, "PNG")
                        
                        # Вставляем картинку
                        img = XLImage(str(excel_img_path))
                        img.width = 120
                        img.height = 90
                        ws.add_image(img, cell_coord)
                        
                        # Очищаем текст в ячейке, так как картинка его перекрывает
                        ws[cell_coord].value = ""
                    except Exception as e:
                        logger.error(f"Ошибка вставки фото {photo_path}: {e}")
                        ws[cell_coord].value = "-"
                else:
                    # Если фото нет, оставляем прочерк
                    ws[cell_coord].value = "-"
                    
        wb.save(output_file)

        # 5. Отправляем файл в Telegram
        await message.answer_document(
            document=FSInputFile(output_file),
            caption=f"✅ Отчет по запросу «{query}» готов!\nНайдено объявлений: {len(rows)}"
        )
        await status_msg.delete()

    except Exception as e:
        logger.exception("Ошибка в пайплайне")
        await status_msg.edit_text(f"❌ Произошла ошибка: {e}")


async def main():
    await init_db()
    logger.info("Запуск бота...")
    
    connector = aiohttp.TCPConnector(family=socket.AF_INET, force_close=True)
    session = AiohttpSession(timeout=60.0)
    session._connector = connector
    
    bot = Bot(token=settings.bot_token, session=session)
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"Не удалось удалить вебхук: {e}")
        
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")