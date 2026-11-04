import asyncio
import logging
import pandas as pd
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage
from app.avito.collector import AvitoCollector
from app.ocr.engine import extract_text_from_image
from app.extraction.regex_extractor import extract_all
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def format_val(val_list):
    if not val_list:
        return "-"
    return ", ".join(val_list)

async def main():
    collector = AvitoCollector()
    
    query = "iphone 13"
    logger.info(f"Ищем: {query}")
    listings = await collector.search(query, limit=1)
    
    if not listings:
        return
        
    listing = listings[0]
    logger.info(f"Обрабатываем: {listing['title']}")
    
    images = await collector.get_images_from_listing(listing["url"])
    if not images:
        return
        
    logger.info(f"Доступно {len(images)} картинок. Проверяем до 7...")
    
    all_entities = {"IMEI": [], "SN": [], "MAC": [], "PASSWORD": []}
    best_image_path = Path(settings.tmp_dir) / "avito_test_image_0.jpg" # По умолчанию первая картинка
    found_data = False
    
    for i, image_url in enumerate(images[:7]):
        save_path = Path(settings.tmp_dir) / f"avito_test_image_{i}.jpg"
        success = await collector.download_image(image_url, str(save_path))
        if not success:
            continue
            
        ocr_res = extract_text_from_image(str(save_path))
        entities = extract_all(ocr_res["combined"])
        
        if entities["IMEI"] or entities["SN"]:
            logger.info(f"🔥 Найдены данные на картинке {i+1}!")
            if not found_data:
                best_image_path = save_path # Запоминаем первую удачную картинку
                found_data = True
            for key in all_entities:
                all_entities[key].extend(entities[key])
                
    # Очищаем дубликаты
    for key in all_entities:
        all_entities[key] = list(set(all_entities[key]))
    
    print("\n--- ИТОГОВЫЕ Найденные сущности ---")
    print(f"IMEI: {format_val(all_entities['IMEI'])}")
    print(f"SN: {format_val(all_entities['SN'])}")
    
    row = {
        "Ссылка": listing["url"],
        "Заголовок": listing["title"],
        "SN": format_val(all_entities["SN"]),
        "IMEI": format_val(all_entities["IMEI"]),
        "MAC": format_val(all_entities["MAC"]),
        "Пароль": format_val(all_entities["PASSWORD"]),
        "Фото": "" # Оставим пустым, картинка вставится поверх
    }
    
    df = pd.DataFrame([row])
    output_file = Path(settings.tmp_dir) / "avito_report.xlsx"
    df.to_excel(output_file, index=False)
    
    # ВСТАВКА КАРТИНКИ
    if best_image_path and best_image_path.exists():
        try:
            wb = load_workbook(output_file)
            ws = wb.active
            
            ws.column_dimensions['G'].width = 30
            ws.row_dimensions[2].height = 150
            
            img = XLImage(str(best_image_path))
            img.width = 200
            img.height = 150
            
            ws.add_image(img, 'G2')
            wb.save(output_file)
            logger.info("Картинка успешно встроена в Excel.")
        except Exception as e:
            logger.error(f"Не удалось вставить картинку в Excel: {e}")

    print(f"\n✅ Отчет сохранен: {output_file}")

if __name__ == "__main__":
    asyncio.run(main())