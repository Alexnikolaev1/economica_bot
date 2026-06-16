FROM python:3.12-slim

WORKDIR /app

# Шрифты для PDF (кириллица)
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/data/local.db

# Railway Volume: смонтируйте том в /data (без директивы VOLUME — Railway не поддерживает)
RUN mkdir -p /data

EXPOSE 8080

CMD ["python", "bot.py"]
