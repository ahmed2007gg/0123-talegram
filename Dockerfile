FROM python:3.11-slim

WORKDIR /app

# تثبيت FFmpeg و yt-dlp وأدوات أخرى
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# تثبيت yt-dlp
RUN pip install --upgrade pip && pip install yt-dlp

# نسخ المتطلبات وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الكود
COPY bot.py .

# التشغيل
CMD ["python", "bot.py"]
