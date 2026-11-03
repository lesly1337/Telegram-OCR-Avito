import logging
import os
import pandas as pd
from app.ocr.engine import extract_text_from_image
from app.extraction.regex_extractor import extract_all

logging.basicConfig(level=logging.INFO)

DEBUG_DIR = "data/tmp"


def main():
    listing = {
        "url": "https://avito.ru/item/123456789",
        "title": "Samsung Galaxy S23 Ultra",
        "category": "Смартфоны"
    }

    os.makedirs(DEBUG_DIR, exist_ok=True)

    image_path = "fixtures/test_image.jpg"
    print(f"⏳ Запуск OCR для {image_path}...")
    ocr_res = extract_text_from_image(image_path, debug_dir=DEBUG_DIR)

    VERBOSE = False

    final_entities = {"IMEI": [], "SN": [], "MAC": [], "PASSWORD": []}

    print("\n--- Результаты по вариантам ---")
    for name, text in ocr_res["by_variant"].items():
        found = {k: [] for k in final_entities}
        for line in text.splitlines():
            for k, v in extract_all(line).items():
                found[k] += v

        if VERBOSE:
            print(f"\n[{name}]\n{text or '(пусто)'}")
        print(f"[{name}] → {({k: v for k, v in found.items() if v}) or '—'}")

        for k in final_entities:
            final_entities[k] += found[k]

    # Убираем дубли, сохраняя порядок (IMEI1 / IMEI2)
    final_entities = {k: list(dict.fromkeys(v)) for k, v in final_entities.items()}
    final_entities["IMEI"] = ocr_res["voted_imei"]

    print("\n--- Итог ---")
    for key, values in final_entities.items():
        print(f"{key}: {values if values else '(не найдено)'}")

    row = {
        "Ссылка": listing["url"],
        "Категория/Заголовок": f'{listing["category"]} / {listing["title"]}',
        "SN": ", ".join(final_entities["SN"]),
        "IMEI": ", ".join(final_entities["IMEI"]),
        "MAC": ", ".join(final_entities["MAC"]),
        "Пароль": ", ".join(final_entities["PASSWORD"]),
        "Уверенность": "Средняя (OCR)"
    }

    df = pd.DataFrame([row])
    output_file = os.path.join(DEBUG_DIR, "test_report.xlsx")
    df.to_excel(output_file, index=False)

    print(f"\n✅ Отчет сохранен в {output_file}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
