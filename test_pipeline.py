import logging
import pandas as pd
from app.ocr.engine import extract_text_from_image
from app.extraction.regex_extractor import extract_all

logging.basicConfig(level=logging.INFO)

def main():
    # 1. Имитируем объявление (пока без Avito)
    listing = {
        "url": "https://avito.ru/item/123456789",
        "title": "Samsung Galaxy S23 Ultra",
        "category": "Смартфоны"
    }
    
    # 2. Запускаем OCR на нашей тестовой картинке
    image_path = "fixtures/test_image.jpg"
    print(f"⏳ Запуск OCR для {image_path}...")
    ocr_res = extract_text_from_image(image_path)
    
    print("\n--- Распознанный текст (Tesseract) ---")
    print(ocr_res["tesseract"])
    
    # 3. Ищем сущности (IMEI, SN и т.д.)
    print("\n--- Поиск сущностей ---")
    entities = extract_all(ocr_res["combined"])
    for key, values in entities.items():
        if values:
            print(f"{key}: {values}")
            
    # 4. Формируем строку для отчета
    row = {
        "Ссылка": listing["url"],
        "Категория/Заголовок": f'{listing["category"]} / {listing["title"]}',
        "SN": ", ".join(entities["SN"]),
        "IMEI": ", ".join(entities["IMEI"]),
        "MAC": ", ".join(entities["MAC"]),
        "Пароль": ", ".join(entities["PASSWORD"]),
        "Уверенность": "Высокая (Regex)"
    }
    
    # 5. Сохраняем в Excel
    df = pd.DataFrame([row])
    output_file = "data/tmp/test_report.xlsx"
    df.to_excel(output_file, index=False)
    
    print(f"\n✅ Отчет сохранен в {output_file}")
    print("\nСодержимое отчета:")
    print(df.to_string(index=False))

if __name__ == "__main__":
    main()