import re
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

def is_valid_luhn(number: str) -> bool:
    if not number.isdigit():
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
    pattern = r'(?<!\d)(?:\d[ -]?){14}\d(?!\d)'
    matches = re.findall(pattern, text)
    
    valid_imeis = []
    for match in matches:
        clean_imei = re.sub(r'\D', '', match)
        if len(clean_imei) == 15 and is_valid_luhn(clean_imei):
            valid_imeis.append(clean_imei)
    return _deduplicate(valid_imeis)

# MAC-адреса в форматах XX:XX:XX:XX:XX:XX или XX-XX-XX-XX-XX-XX
def extract_mac(text: str) -> List[str]:
    pattern = r'\b([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})\b'
    macs = [m.group(0).upper() for m in re.finditer(pattern, text)]
    return _deduplicate(macs)

# Поиск серийного номера
def extract_sn(text: str) -> List[str]:
    pattern = (
        r'(?<![A-Z0-9])(?:S/N|SN|Serial(?:\s*Number)?|Серийный номер)'
        r'[\s:=\-]+([A-Z0-9]{8,15})(?![A-Z0-9])'
    )
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