import logging
import re
import string
import cv2
import numpy as np
import pytesseract
from easyocr import Reader
from app.extraction.regex_extractor import extract_imei

logger = logging.getLogger(__name__)

try:
    reader = Reader(['en'], gpu=False)
except Exception as e:
    logger.error(f"Не удалось инициализировать EasyOCR: {e}")
    reader = None

ALLOW = string.ascii_uppercase + string.digits + "/:-."
TARGET_HEIGHTS = (48, 80)  # высота строки в px после ресайза; для бота можно оставить одну
FULL_HD_LANDSCAPE = (1920, 1080)


def calculate_full_hd_size(width: int, height: int) -> tuple[int, int]:
    """Уменьшает крупный вход до Full HD, не увеличивая небольшие кадры."""
    if width <= 0 or height <= 0:
        raise ValueError("Размеры изображения должны быть положительными")

    max_width, max_height = FULL_HD_LANDSCAPE
    if height > width:
        max_width, max_height = max_height, max_width

    scale = min(1.0, max_width / width, max_height / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def build_variants(image_path: str, scale: int = 3) -> dict[str, np.ndarray]:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Не удалось загрузить изображение: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    target_width, target_height = calculate_full_hd_size(gray.shape[1], gray.shape[0])
    if (target_width, target_height) != (gray.shape[1], gray.shape[0]):
        gray = cv2.resize(
            gray,
            (target_width, target_height),
            interpolation=cv2.INTER_AREA,
        )
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    inv = cv2.bitwise_not(clahe.apply(gray))  # белый текст -> тёмный на светлом
    _, otsu_inv = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return {"inv": inv, "otsu_inv": otsu_inv}


def detect_lines(arr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Строки текста через детектор EasyOCR -> (x1, y1, x2, y2)."""
    if not reader:
        return []
    horizontal, _free = reader.detect(
        arr, min_size=10, text_threshold=0.5, low_text=0.3, width_ths=0.3
    )
    boxes = [(int(x1), int(y1), int(x2), int(y2)) for x1, x2, y1, y2 in horizontal[0]]
    return sorted(boxes, key=lambda b: (b[1], b[0]))


def merge_boxes_into_rows(
    boxes: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Объединяет боксы одной печатной строки в общий OCR-кроп.

    Детектор часто возвращает метку и значение отдельными боксами, например
    ``IMEI 1:`` и сам номер. Общий кроп сохраняет их контекст и позволяет
    распознавать несколько значений, напечатанных в одной строке.
    """
    rows: list[list[tuple[int, int, int, int]]] = []

    for box in sorted(boxes, key=lambda b: ((b[1] + b[3]) / 2, b[0])):
        box_center = (box[1] + box[3]) / 2
        box_height = box[3] - box[1]

        for row in rows:
            row_y1 = min(item[1] for item in row)
            row_y2 = max(item[3] for item in row)
            row_center = (row_y1 + row_y2) / 2
            row_height = row_y2 - row_y1
            if abs(box_center - row_center) <= 0.45 * max(box_height, row_height):
                row.append(box)
                break
        else:
            rows.append([box])

    return [
        (
            min(box[0] for box in row),
            min(box[1] for box in row),
            max(box[2] for box in row),
            max(box[3] for box in row),
        )
        for row in rows
        if len(row) > 1
    ]


def crop_line(arr: np.ndarray, box, height: int) -> np.ndarray | None:
    x1, y1, x2, y2 = box
    h, w = arr.shape[:2]
    # EasyOCR нередко заканчивает бокс за 1-3 символа до фактического конца.
    # Запас зависит от высоты текста, чтобы одинаково работать при ином scale.
    right_padding = max(12, round((y2 - y1) * 1.2))
    crop = arr[
        max(y1 - 6, 0):min(y2 + 6, h),
        max(x1 - 12, 0):min(x2 + right_padding, w),
    ]
    if crop.size == 0:
        return None
    k = height / crop.shape[0]
    crop = cv2.resize(crop, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    # белая рамка: Tesseract плохо читает текст, прижатый к краю картинки
    return cv2.copyMakeBorder(crop, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)


def tess_line(crop: np.ndarray) -> str:
    cfg = f"--oem 3 --psm 7 -c tessedit_char_whitelist={ALLOW}"
    return pytesseract.image_to_string(crop, lang="eng", config=cfg).strip()


def easy_line(crop: np.ndarray) -> str:
    return " ".join(reader.readtext(crop, detail=0, allowlist=ALLOW + " ")).strip()


def easy_full(arr: np.ndarray) -> str:
    return " ".join(reader.readtext(arr, detail=0, allowlist=ALLOW + " ")).strip()


def _safe(fn, *args) -> str:
    try:
        return fn(*args)
    except Exception as e:
        logger.error(f"{fn.__name__}: {e}")
        return ""


IMEI_LABEL = re.compile(r'(?:I\s*M\s*[E3]\s*[I1LN]|M\s*E\s*I\s*D)', re.IGNORECASE)


def _is_near_imei_label(text: str, candidate: str, max_distance: int = 32) -> bool:
    """Проверяет, расположен ли цифровой кандидат рядом с IMEI/MEID."""
    labels = list(IMEI_LABEL.finditer(text))
    if not labels:
        return False

    digit_positions = [index for index, char in enumerate(text) if char.isdigit()]
    digits = "".join(text[index] for index in digit_positions)
    start = digits.find(candidate)
    if start < 0:
        return False

    candidate_start = digit_positions[start]
    candidate_end = digit_positions[start + len(candidate) - 1] + 1
    return any(
        min(
            abs(candidate_start - label.end()),
            abs(label.start() - candidate_end),
        )
        <= max_distance
        for label in labels
    )


def _same_imei_with_bad_leading_digit(left: str, right: str) -> bool:
    """Группирует OCR-конфликт 356.../256..., не склеивая два реальных IMEI."""
    if len(left) != 15 or len(right) != 15 or left[0] == right[0]:
        return False
    return sum(a != b for a, b in zip(left[1:], right[1:])) <= 1


def vote_imei_candidates(texts: dict[str, str]) -> list[str]:
    """Выбирает IMEI по согласию движков, контексту и префиксу 35."""
    evidence: dict[str, dict[str, object]] = {}

    for variant, text in texts.items():
        if variant.startswith("tess_"):
            engine = "tesseract"
        elif variant.startswith("easy_"):
            engine = "easyocr"
        else:
            continue

        for line in text.splitlines():
            for candidate in extract_imei(line):
                item = evidence.setdefault(
                    candidate,
                    {
                        "engines": set(),
                        "variants": set(),
                        "contexts": set(),
                        "order": len(evidence),
                    },
                )
                item["engines"].add(engine)
                item["variants"].add(variant)
                if _is_near_imei_label(line, candidate):
                    item["contexts"].add(variant)

    groups: list[list[str]] = []
    for candidate in evidence:
        for group in groups:
            if any(
                _same_imei_with_bad_leading_digit(candidate, member)
                for member in group
            ):
                group.append(candidate)
                break
        else:
            groups.append([candidate])

    selected: list[tuple[int, str]] = []
    for group in groups:
        engines = set().union(*(evidence[item]["engines"] for item in group))
        variants = set().union(*(evidence[item]["variants"] for item in group))
        contexts = set().union(*(evidence[item]["contexts"] for item in group))

        # Либо два независимых движка согласились/дали близкие варианты,
        # либо один движок подтвердил номер в нескольких OCR-вариантах рядом
        # с явной меткой IMEI. Одиночные Luhn-совпадения не принимаем.
        if len(engines) < 2 and not (len(variants) >= 2 and contexts):
            continue

        winner = max(
            group,
            key=lambda item: (
                bool(evidence[item]["contexts"]),
                len(evidence[item]["engines"]),
                item.startswith("35"),
                len(evidence[item]["variants"]),
            ),
        )
        selected.append((evidence[winner]["order"], winner))

    return [candidate for _, candidate in sorted(selected)]


def extract_text_from_image(image_path: str, debug_dir: str | None = None) -> dict:
    logger.info(f"Запуск OCR для {image_path}")
    variants = build_variants(image_path)
    texts: dict[str, str] = {}

    if debug_dir:
        for name, arr in variants.items():
            cv2.imwrite(f"{debug_dir}/{name}.png", arr)

    # 1) Кадр целиком (EasyOCR) — как раньше, ловит крупные поля
    if reader:
        for name, arr in variants.items():
            texts[f"easy_full_{name}"] = _safe(easy_full, arr)

    # 2) Построчно
    detected_boxes = detect_lines(variants["otsu_inv"])
    row_boxes = merge_boxes_into_rows(detected_boxes)
    boxes = detected_boxes + row_boxes
    logger.info(
        "Найдено боксов: %s, объединенных строк: %s",
        len(detected_boxes),
        len(row_boxes),
    )

    for name, arr in variants.items():
        for height in TARGET_HEIGHTS:
            tess_out, easy_out = [], []
            for i, box in enumerate(boxes):
                crop = crop_line(arr, box, height)
                if crop is None:
                    continue
                if debug_dir and height == TARGET_HEIGHTS[0]:
                    cv2.imwrite(f"{debug_dir}/line_{name}_{i:02d}.png", crop)
                tess_out.append(_safe(tess_line, crop))
                if reader:
                    easy_out.append(_safe(easy_line, crop))

            texts[f"tess_lines_{name}_h{height}"] = "\n".join(t for t in tess_out if t)
            texts[f"easy_lines_{name}_h{height}"] = "\n".join(t for t in easy_out if t)

    return {
        "by_variant": texts,
        "combined": "\n".join(texts.values()),
        "voted_imei": vote_imei_candidates(texts),
    }
