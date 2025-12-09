#Pull Image and make offline 
- docker pull ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-gpu-sm120-offline
- docker save ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-gpu-sm120-offline -o paddleocr-vl-latest-gpu-sm120-offline.tar
- docker load -i paddleocr-vl-latest-gpu-sm120-offline.tar
- docker run -it --gpus all --network host --user root ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-gpu-sm120-offline /bin/bash

# Clone Project 
- cd C:\Users\NAMA_KAMU\Documents  # atau folder kerja yang kamu mau
- git clone https://github.com/CreativeAcademyIndonesia/padddle-vl-ocr.git
- cd padddle-vl-ocr