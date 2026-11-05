FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

RUN python -c "import easyocr; easyocr.Reader(['ru', 'en'], gpu=False)"

COPY app ./app
COPY scripts/check_proxy_routes.py ./scripts/check_proxy_routes.py
COPY scripts/avito_verify.py ./scripts/avito_verify.py
CMD ["python", "-m", "app.main"]
