FROM python:3.11-slim

WORKDIR /app

# تثبيت FFmpeg و yt-dlp وأدوات أخرى
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# تثبيت yt-dlp مباشرة من pip
RUN pip install --upgrade pip
RUN pip install yt-dlp

# نسخ متطلبات Python وتثبيتها
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ باقي الملفات
COPY . .

# أمر التشغيل
CMD ["python", "bot.py"]
