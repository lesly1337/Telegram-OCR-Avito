import logging
import cv2
import numpy as np
import pytesseract
from PIL import Image
from easyocr import Reader
from app.config import settings

logger = logging.getLogger(__name__)

try:
    reader = Reader(['ru', 'en'], gpu=False)
except Exception as e:
    logger.error(f"Не удалось инициализировать EasyOCR: {e}")
    reader = None

def preprocess_image(image_path: str) -> np.ndarray:
    
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Не удалось загрузить изображение: {image_path}")
        
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    gaussian = cv2.GaussianBlur(enhanced, (0, 0), 2.0)
    sharpened = cv2.addWeighted(enhanced, 1.5, gaussian, -0.5, 0)
    return sharpened

def run_tesseract(image_path: str) -> str:
    try:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        
        processed_img = preprocess_image(image_path)
        config = '--psm 6'
        text = pytesseract.image_to_string(processed_img, lang=settings.tesseract_lang, config=config)
        return text.strip()
    except Exception as e:
        logger.error(f"Ошибка Tesseract: {e}")
        return ""

def run_easyocr(image_path: str) -> str:
    if not reader:
        return ""
    try:
        results = reader.readtext(image_path, detail=0)
        return " ".join(results).strip()
    except Exception as e:
        logger.error(f"Ошибка EasyOCR: {e}")
        return ""

def extract_text_from_image(image_path: str) -> dict:
    logger.info(f"Запуск OCR для {image_path}")
    
    easy_text = run_easyocr(image_path)
    tess_text = run_tesseract(image_path)
    
    combined = f"{easy_text}\n{tess_text}".strip()
    
    return {
        "easyocr": easy_text,
        "tesseract": tess_text,
        "combined": combined
    }
