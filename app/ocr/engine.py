import logging
import cv2
import numpy as np
import pytesseract
from PIL import Image
from easyocr import Reader
from app.config import settings

logger = logging.getLogger(__name__)

# Инициализируем EasyOCR (при первом запуске он может скачать модели)
# Используем русский и английский
try:
    reader = Reader(['ru', 'en'], gpu=False)
except Exception as e:
    logger.error(f"Не удалось инициализировать EasyOCR: {e}")
    reader = None

def preprocess_image(image_path: str) -> np.ndarray:
    """Предобработка изображения для улучшения OCR."""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Не удалось загрузить изображение: {image_path}")
        
    # Переводим в оттенки серого
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Увеличиваем контрастность и применяем бинаризацию (адаптивную)
    # Это помогает выделить текст на этикетках
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 11, 2
    )
    return thresh

def run_tesseract(image_path: str) -> str:
    """Распознавание через Tesseract."""
    try:
        # Можно передать предобработанную картинку (thresh) в pytesseract
        # но для начала попробуем прямое распознавание
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang=settings.tesseract_lang)
        return text.strip()
    except Exception as e:
        logger.error(f"Ошибка Tesseract: {e}")
        return ""

def run_easyocr(image_path: str) -> str:
    """Распознавание через EasyOCR."""
    if not reader:
        return ""
    try:
        # EasyOCR принимает путь к файлу или numpy array
        results = reader.readtext(image_path, detail=0)
        return " ".join(results).strip()
    except Exception as e:
        logger.error(f"Ошибка EasyOCR: {e}")
        return ""

def extract_text_from_image(image_path: str) -> dict:
    logger.info(f"Запуск OCR для {image_path}")
    
    # Tesseract кормим ОРИГИНАЛ (он лучше читает цветное/серое без жесткой обработки)
    try:
        img = Image.open(image_path)
        tess_text = pytesseract.image_to_string(img, lang=settings.tesseract_lang).strip()
    except Exception as e:
        logger.error(f"Ошибка Tesseract: {e}")
        tess_text = ""

    # EasyOCR кормим оригинал (он справляется лучше всех)
    easy_text = run_easyocr(image_path)
    
    # Объединяем оба результата (чтобы не потерять данные)
    combined = f"{tess_text}\n{easy_text}".strip()
    
    # Для отладки сохраняем объединенный текст в файл
    with open("data/tmp/ocr_result.txt", "w", encoding="utf-8") as f:
        f.write(combined)
    
    return {
        "tesseract": tess_text,
        "easyocr": easy_text,
        "combined": combined
    }