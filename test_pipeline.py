import asyncio
import logging
from pathlib import Path
import pandas as pd
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage

from app.avito.collector import AvitoCollector
from app.ocr.engine import extract_text_from_image
from app.extraction.regex_extractor import extract_all
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_PHOTOS = 5

def format_val(val_list):
    if not val_list: return "-"
    return ", ".join(val_list)

async def main():
    collector = AvitoCollector()
    query = "iphone 13"
    
    logger.info(f"Ищем: {query}")
    listings = await collector.search(query, limit=1) # Берем 1 объявление для теста
    
    if not listings:
        logger.error("Ничего не найдено.")
        return
        
    rows = []
    
    for idx, listing in enumerate(listings):
        logger.info(f"Обрабатываем: {listing['title']}")
        
        images = await collector.get_images_from_listing(listing["url"])
        all_entities = {"IMEI": [], "SN": [], "MAC": [], "PASSWORD": []}
        downloaded_photos = []
        
        logger.info(f"Скачиваем до {MAX_PHOTOS} фото...")
        for i, image_url in enumerate(images[:MAX_PHOTOS]):
            save_path = Path(settings.tmp_dir) / f"test_item_{idx}_img_{i}.jpg"
            success = await collector.download_image(image_url, str(save_path))
            
            if success:
                downloaded_photos.append(save_path)
                ocr_res = extract_text_from_image(str(save_path))
                entities = extract_all(ocr_res["combined"])
                for key in all_entities:
                    all_entities[key].extend(entities[key])
            else:
                downloaded_photos.append(None)
                
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

    # Сохраняем в Excel
    df = pd.DataFrame([{k: v for k, v in r.items() if k != "_photos"} for r in rows])
    for i in range(MAX_PHOTOS):
        df[f"Фото {i+1}"] = "-"
        
    output_file = Path(settings.tmp_dir) / "test_report.xlsx"
    df.to_excel(output_file, index=False)

    # Вставляем картинки
    wb = load_workbook(output_file)
    ws = wb.active
    
    photo_start_col = 7 # Колонка G
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
                    excel_img_path = Path(settings.tmp_dir) / f"excel_test_{row_idx}_{photo_idx}.png"
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
    print(f"\n✅ Отчет сохранен: {output_file}")

if __name__ == "__main__":
    asyncio.run(main())