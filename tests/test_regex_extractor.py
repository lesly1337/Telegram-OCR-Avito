import pytest
from app.extraction.regex_extractor import (
    is_valid_luhn, extract_all, extract_imei, 
    extract_mac, extract_sn, extract_password
)

def test_luhn():
    # Валидный IMEI
    assert is_valid_luhn("356938035643809") is True
    # Невалидный (изменена последняя цифра)
    assert is_valid_luhn("356938035643808") is False

def test_extract_imei():
    text = "IMEI: 356938035643809, также есть 356938035643800 и 123456789012345"
    imeis = extract_imei(text)
    assert len(imeis) == 1
    assert imeis[0] == "356938035643809"

def test_extract_imei_from_ocr_text():
    text = "IMEI1: 354484225821337 IMEI2: 355004225821336 S/N: RFCW13XPKE"
    result = extract_all(text)
    assert result["IMEI"] == ["354484225821337", "355004225821336"]
    assert result["SN"] == ["RFCW13XPKE"]

def test_extract_imei_with_separators_and_attached_text():
    assert extract_imei("IMEI: 356-938-035-643-809") == ["356938035643809"]
    assert extract_imei("IMEI:356938035643809 Сделано в Китае") == [
        "356938035643809"
    ]

def test_extract_imei_trims_extra_digits():
    text = "IMEI: 0356938035643809; IMEI: 3569380356438097"
    assert extract_imei(text) == ["356938035643809"]

def test_extract_mac():
    text = "MAC: A4:2B:B0:11:22:33 and another one A4-2B-B0-11-22-44."
    macs = extract_mac(text)
    assert len(macs) == 2
    assert macs[0] == "A4:2B:B0:11:22:33"
    assert macs[1] == "A4-2B-B0-11-22-44"

def test_extract_sn():
    # SNOWMAN123456 не должен срабатывать
    text = "There is a SNOWMAN123456 here. But here is SN: XCV12345678."
    sns = extract_sn(text)
    assert len(sns) == 1
    assert sns[0] == "XCV12345678"

def test_extract_password():
    # "number" не должно извлекаться как пароль
    text = "PIN number 12345 and Password: super_pass123."
    passwords = extract_password(text)
    # Из-за контекста "number" не подходит, а "super_pass123" должно найтись
    # (в PIN number 12345 регулярка может найти 12345, это нормально)
    assert "super_pass123" in passwords
    assert "number" not in passwords

def test_empty_input():
    res = extract_all("")
    assert res == {"IMEI": [], "MAC": [], "SN": [], "PASSWORD": []}