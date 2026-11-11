FROM python:3.12-slim

# ffmpeg is needed to trim the generated videos to exactly 3s
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# install python deps first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8140
EXPOSE 8140
CMD ["python", "app.py"]
