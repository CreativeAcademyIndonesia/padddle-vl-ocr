# Pull Image and make offline 
- docker pull ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-gpu-sm120-offline
- docker save ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-gpu-sm120-offline -o paddleocr-vl-latest-gpu-sm120-offline.tar
- docker load -i paddleocr-vl-latest-gpu-sm120-offline.tar
- docker run -it --gpus all --network host --user root ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-gpu-sm120-offline /bin/bash

# Clone Project 
- cd C:\Users\NAMA_KAMU\Documents  # atau folder kerja yang kamu mau
- git clone https://github.com/CreativeAcademyIndonesia/padddle-vl-ocr.git
- cd padddle-vl-ocr

# Build Image 
- docker build -t paddleocr-vl-api .

# Run Project 
docker run -d --gpus all --network bridge -p 8000:8000 --name paddleocr-vl-api paddleocr-vl-api

# Jika ada perubahan 
- docker build -t paddleocr-vl-api .
- docker ps -a
- docker stop paddleocr-vl-api
- docker rm paddleocr-vl-api

# Run Project 
docker run -d --gpus all --network bridge -p 8000:8000 --name paddleocr-vl-api paddleocr-vl-api