FROM python:3.11-slim

WORKDIR /app

# تثبيت FFmpeg + Node.js (لحل مشكلة JavaScript)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# تثبيت Node.js (مطلوب لحل تحدي n)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs

# تثبيت yt-dlp عبر pip
RUN pip install --upgrade pip
RUN pip install --upgrade yt-dlp

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
