FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl \
       ghostscript \
       poppler-utils \
       tesseract-ocr \
       tesseract-ocr-eng \
       tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

COPY . /app

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/input /data/work /data/output /data/originals /data/reports /data/backups \
    && chown -R appuser:appuser /data /app

USER appuser
EXPOSE 8050

CMD ["uvicorn", "translator.api:app", "--host", "0.0.0.0", "--port", "8050"]
