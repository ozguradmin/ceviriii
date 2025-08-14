# Python 3.11 slim
FROM python:3.11-slim

# System deps (ffmpeg)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App files
COPY . .

ENV PORT=5001
RUN mkdir -p /app/uploads /app/static/outputs /app/fonts

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:${PORT}", "--workers", "2", "--threads", "4"]

