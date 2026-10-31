from __future__ import annotations

import shutil
import sys
import os
from importlib import import_module

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

REQUIRED_MODULES = [
    "aiogram", "pydantic", "pydantic_settings", "ollama",
    "langchain", "langchain_ollama",
    "playwright", "curl_cffi", "httpx", "tenacity",
    "PIL", "cv2", "pytesseract", "easyocr",
    "pandas", "openpyxl", "aiosqlite",
]


def check_python() -> None:
    if sys.version_info < (3, 11):
        raise SystemExit(f"Нужен Python >= 3.11, найден {sys.version.split()[0]}")
    print(f"[ok] Python {sys.version.split()[0]}")


def check_modules() -> None:
    missing = []
    for name in REQUIRED_MODULES:
        try:
            import_module(name)
            print(f"[ok] import {name}")
        except Exception as e:  # noqa: BLE001
            missing.append((name, e))
            print(f"[!!] import {name}: {e}")
    if missing:
        raise SystemExit(f"Не хватает модулей: {[m for m, _ in missing]}")


def check_tesseract() -> None:
    if not shutil.which("tesseract"):
        raise SystemExit("tesseract не найден в PATH")
    import pytesseract
    try:
        langs = set(pytesseract.get_languages())
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"tesseract не запускается: {e}") from e
    need = {"rus", "eng"}
    if not need.issubset(langs):
        raise SystemExit(f"В tesseract нет языков {need - langs}")
    print(f"[ok] tesseract языки: {sorted(langs)}")


def check_playwright() -> None:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("[ok] playwright chromium")
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"playwright chromium не запускается: {e}. Выполните `playwright install chromium`.") from e


def check_settings() -> None:
    from app.config import settings
    assert settings.bot_token and ":" in settings.bot_token, "BOT_TOKEN выглядит некорректно"
    print(f"[ok] config: model={settings.ollama_model}, db={settings.db_path}")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.tmp_dir.mkdir(parents=True, exist_ok=True)


def check_ollama() -> None:
    import httpx
    from app.config import settings
    try:
        r = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=5)
        r.raise_for_status()
        tags = [m["name"] for m in r.json().get("models", [])]
        print(f"[ok] ollama доступен, модели: {tags}")
        if not any(settings.ollama_model.split(":")[0] in t for t in tags):
            print(f"[!!] модель {settings.ollama_model} не скачана: ollama pull {settings.ollama_model}")
    except Exception as e:  # noqa: BLE001
        print(f"[!!] ollama недоступен: {e}. Запустите `ollama serve`.")


if __name__ == "__main__":
    check_python()
    check_modules()
    check_tesseract()
    check_playwright()
    check_settings()
    check_ollama()