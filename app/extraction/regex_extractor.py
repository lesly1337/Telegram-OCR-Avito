import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

def is_valid_luhn(number: str) -> bool:
    if not re.fullmatch(r"[0-9]+", number):
        return False
    digits = [int(d) for d in str(number)]
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    return total % 10 == 0

def _deduplicate(items: List[str]) -> List[str]:
    seen = set()
    return [x for x in items if not (x in seen or seen.add(x))]

def extract_imei(text: str) -> List[str]:
    valid_imeis = []

    # Цифра в метке IMEI1/IMEI2 не является частью номера. Без удаления
    # метки она может образовать с номером ложное, но валидное окно Луна.
    text = re.sub(
        r'\bI\s*M\s*E\s*I\s*[1-9]\s*[:=]',
        ' ',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\bI\s*M\s*E\s*I\s*[:=]',
        ' ',
        text,
        flags=re.IGNORECASE,
    )
    
    # Ищем блоки длиной от 15 до 18 цифр (с учетом разделителей).
    # 18 цифр — это максимум, чтобы захватить IMEI с 1-3 лишними цифрами,
    # но НЕ захватить 32-значный EID.
    pattern = r'(?<!\d)(\d(?:[\s\-\.:]*\d){14,17})(?!\d)'
    
    for match in re.finditer(pattern, text):
        raw_digits = match.group(0)
        digits = re.sub(r'\D', '', raw_digits)

        # При OCR-ошибке в слове IMEI (например IMEN2) regex может увидеть
        # блок ``2:355...``. Двоеточие после первой цифры однозначно отделяет
        # индекс метки, поэтому не включаем его в скользящие окна.
        if len(digits) > 15 and re.match(r'^\d[\s\.:]*:', raw_digits):
            digits = digits[1:]
        
        # Скользящее окно по 15 цифр
        for start in range(len(digits) - 14):
            candidate = digits[start : start + 15]
            if is_valid_luhn(candidate):
                valid_imeis.append(candidate)

    return _deduplicate(valid_imeis)


# MAC-адреса в форматах XX:XX:XX:XX:XX:XX или XX-XX-XX-XX-XX-XX
def extract_mac(text: str) -> List[str]:
    pattern = r'\b([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})\b'
    macs = [m.group(0).upper() for m in re.finditer(pattern, text)]
    return _deduplicate(macs)

# Поиск серийного номера
SN_LABEL = r'(?:S\s*[/\\|I1l]\s*N|SN|Serial(?:\s*Number)?|Серийный номер)'

def extract_sn(text: str) -> List[str]:
    pattern = rf'(?<![A-Z0-9]){SN_LABEL}[\s:=\-]+([A-Z0-9]{{8,15}})(?![A-Z0-9])'
    results = []
    for m in re.finditer(pattern, text, re.IGNORECASE):
        val = m.group(1).upper()
        if any(c.isalpha() for c in val) and any(c.isdigit() for c in val):
            results.append(val)
    return _deduplicate(results)

def extract_password(text: str) -> List[str]:
    """Контекстный поиск паролей."""
    password_pattern = (
        r'(?<![A-Z0-9])(?:Password|Pass|Пароль|WPA|Wifi|Pwd)'
        r'[\s:=\-]+([A-Za-z0-9_!@#$%^&*]{5,20})(?![A-Za-z0-9_!@#$%^&*])'
    )
    pin_pattern = r'(?<![A-Z0-9])PIN[\s:=\-]+(\d{4,8})(?!\d)'

    passwords = [
        match.group(1)
        for pattern in (password_pattern, pin_pattern)
        for match in re.finditer(pattern, text, re.IGNORECASE)
    ]
    return _deduplicate(passwords)

def extract_all(text: str) -> Dict[str, List[str]]:
    if not text:
        return {"IMEI": [], "MAC": [], "SN": [], "PASSWORD": []}
    return {
        "IMEI": extract_imei(text),
        "MAC": extract_mac(text),
        "SN": extract_sn(text),
        "PASSWORD": extract_password(text)
    }
