FROM python:3.12-slim

# poppler-utils: requerido por pdf2image para el fallback visión del parser BBVA
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias primero (capa cacheada)
COPY bot/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente
COPY bot/ ./bot/

# Railway inyecta las variables de entorno en runtime, no necesitamos .env
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "bot.main"]
