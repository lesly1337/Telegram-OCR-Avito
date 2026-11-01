import logging
from app.ocr.engine import extract_text_from_image
from app.extraction.regex_extractor import extract_all

logging.basicConfig(level=logging.INFO)

# Укажите путь к вашей картинке
IMAGE_PATH = "fixtures/test_image.jpg" 

def main():
    print(f"Анализируем: {IMAGE_PATH}")
    ocr_results = extract_text_from_image(IMAGE_PATH)
    
    print("\n--- Результат Tesseract ---")
    print(ocr_results["tesseract"])
    
    print("\n--- Результат EasyOCR ---")
    print(ocr_results["easyocr"])
    
    print("\n--- Поиск сущностей ---")
    entities = extract_all(ocr_results["combined"])
    for key, values in entities.items():
        if values:
            print(f"{key}: {values}")

if __name__ == "__main__":
    main()