from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str = Field(..., alias="BOT_TOKEN")
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list, alias="ADMIN_IDS")

    # Ollama
    ollama_base_url: str = Field("http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field("qwen2.5:7b-instruct", alias="OLLAMA_MODEL")

    # Avito
    avito_base_url: str = Field("https://www.avito.ru", alias="AVITO_BASE_URL")
    avito_max_items_default: int = Field(30, alias="AVITO_MAX_ITEMS_DEFAULT")
    avito_request_delay: float = Field(1.5, alias="AVITO_REQUEST_DELAY")
    avito_headless: bool = Field(True, alias="AVITO_HEADLESS")
    avito_use_fixtures: bool = Field(False, alias="AVITO_USE_FIXTURES")

    # Independent proxies: Avito (PROXY_URL, retained for compatibility) and Telegram
    proxy_url: str = Field("", alias="PROXY_URL")
    telegram_proxy_url: str = Field("", alias="TELEGRAM_PROXY_URL")

    # OCR
    tesseract_cmd: str = Field("/usr/bin/tesseract", alias="TESSERACT_CMD")
    tesseract_lang: str = Field("rus+eng", alias="TESSERACT_LANG")
    ocr_max_images_per_item: int = Field(6, alias="OCR_MAX_IMAGES_PER_ITEM")

    # Paths
    data_dir: Path = Field(Path("./data"), alias="DATA_DIR")
    db_path: Path = Field(Path("./data/app.db"), alias="DB_PATH")
    tmp_dir: Path = Field(Path("./data/tmp"), alias="TMP_DIR")

    # Logging
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _split_admins(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip()]
        return v


settings = Settings()
