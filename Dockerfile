# Pakai image PaddleOCR-VL yang sudah kamu download sebagai base
FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-gpu-sm120-offline

# Set workdir
WORKDIR /app

# Copy kode API
COPY app.py /app/app.py

# Install dependensi untuk API
RUN pip install --no-cache-dir fastapi uvicorn[standard] python-multipart

# Expose port untuk API
EXPOSE 8000

# Jalankan server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
