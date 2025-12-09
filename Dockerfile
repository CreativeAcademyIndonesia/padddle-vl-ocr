FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-gpu-sm120-offline

# Pastikan pakai root untuk install paket OS
USER root

# System dependency untuk pdf2image (poppler)
RUN mkdir -p /var/lib/apt/lists/partial && \
    apt-get update && \
    apt-get install -y poppler-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY app.py /app/app.py

# Install dependency Python untuk API + pdf2image
RUN pip install --no-cache-dir fastapi uvicorn[standard] python-multipart pdf2image

EXPOSE 8000

# (Opsional) kalau base image awalnya pakai user non-root, bisa balikin lagi:
# USER paddleocr

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
