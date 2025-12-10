FROM ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-gpu-sm120-offline

USER root

ENV TZ=Asia/Jakarta

RUN mkdir -p /var/lib/apt/lists/partial && \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        tzdata \
        poppler-utils && \
    ln -fs /usr/share/zoneinfo/Asia/Jakarta /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]