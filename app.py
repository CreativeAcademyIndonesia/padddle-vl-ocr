from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Header
from fastapi.responses import JSONResponse
from paddleocr import PaddleOCRVL
from pdf2image import convert_from_path, pdfinfo_from_path 
import tempfile
import os
import shutil
import json
import logging
import datetime
import time
from typing import List, Optional, Any

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("OCR_API")

def log_process(msg: str):
    timestamp = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    logger.info(f"[{timestamp}] {msg}")

# Helper response standard
def create_response(success: bool, data: Any = None, message: str = "", error_code: int = 200):
    content = {
        "error": not success,
        "success": success,
        "data": data,
        "message": message
    }
    return JSONResponse(content=content, status_code=error_code)

PADDLE_API_KEY = "332100185"
app = FastAPI()

# --- LAZY LOADING SETUP ---
# Jangan load model di sini agar reload cepat.
# Model akan diload saat request pertama kali masuk.
pipeline = None

def get_pipeline():
    """Fungsi singleton untuk memuat model hanya jika belum ada"""
    global pipeline
    if pipeline is None:
        log_process("Loading PaddleOCR Model into memory... (This takes time)")
        pipeline = PaddleOCRVL()
        log_process("Model loaded successfully!")
    return pipeline

def process_ocr_output(output):
    """
    Konversi hasil OCR ke JSON-friendly format dan ekstrak Markdown builtin.
    Returns: (list_of_dicts, markdown_string)
    """
    results = []
    markdowns = []
    
    # Gunakan direktori sementara yang aman
    temp_dir = tempfile.mkdtemp()
    
    log_process("process ocr output")

    try:
        for idx, res in enumerate(output):
            # --- 1. Extract JSON Data ---
            if hasattr(res, "to_dict"):
                results.append(res.to_dict())
            elif hasattr(res, "to_json"):
                results.append(json.loads(res.to_json()))
            else:
                # Fallback: save to json file
                res.save_to_json(save_path=temp_dir)
                # Cari file json yang baru dibuat
                for jf in os.listdir(temp_dir):
                    if jf.endswith(".json"):
                        fpath = os.path.join(temp_dir, jf)
                        with open(fpath, "r", encoding="utf-8") as f:
                            results.append(json.load(f))
                        os.remove(fpath) # Hapus setelah baca

            # --- 2. Extract Markdown Builtin ---
            # Cek dokumentasi: https://docs.vllm.ai/projects/recipes/en/latest/PaddlePaddle/PaddleOCR-VL.html
            if hasattr(res, "save_to_markdown"):
                md_filename = f"out_{idx}.md"
                md_path = os.path.join(temp_dir, md_filename)
                try:
                    res.save_to_markdown(save_path=md_path)
                    if os.path.exists(md_path):
                        with open(md_path, "r", encoding="utf-8") as f:
                            markdowns.append(f.read())
                        os.remove(md_path) # Hapus setelah baca
                except Exception as e:
                    print(f"Gagal extract markdown builtin: {e}")

    finally:
        # Cleanup temp folder
        shutil.rmtree(temp_dir, ignore_errors=True)

    return results, "\n\n".join(markdowns)

def parse_pages_param(value: Optional[str]) -> Optional[List[int]]:
    """Parse parameter pages. Support JSON [1,2] atau CSV 1,2"""
    log_process("process parse pages params")
    if value is None:
        return None
    
    value = value.strip()
    if value == "" or value.lower() == "null":
        return None

    # Bersihkan kutip ganda/tunggal di awal & akhir jika terbawa (issue umum di curl Windows)
    if len(value) >= 2 and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")):
        value = value[1:-1]

    decoded = None

    # 1. Coba Parse sebagai JSON
    try:
        decoded = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        # 2. Jika gagal JSON, coba parse sebagai Comma Separated Values (contoh: "1, 3")
        try:
            # Split koma, filter empty, convert int
            decoded = [int(x.strip()) for x in value.split(',') if x.strip().isdigit()]
            if not decoded and value: # Jika value ada tapi hasil kosong (misal "abc")
                 raise ValueError 
        except ValueError:
             raise HTTPException(400, detail="Format 'pages' salah. Gunakan JSON array [1,2] atau angka dipisah koma '1,2'")
    
    # Handle jika input hanya satu angka integer (misal dari json "1")
    if isinstance(decoded, int):
        decoded = [decoded]

    if not isinstance(decoded, list):
        raise HTTPException(400, detail="Format 'pages' harus berupa list angka")

    # Pastikan semua elemen int dan positif
    try:
        final_pages = []
        for x in decoded:
            val = int(x)
            if val > 0:
                final_pages.append(val)
        
        if not final_pages and decoded: # List tidak kosong tapi isinya invalid semua
             raise HTTPException(400, detail="Halaman harus angka positif")
             
        return sorted(list(set(final_pages)))
    except (ValueError, TypeError):
        raise HTTPException(400, detail="Elemen halaman harus berupa angka")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ocr")
async def ocr_document(
    file: UploadFile = File(...),
    pages: Optional[str] = Form(None),
    paddle_api_key: Optional[str] = Header(None, alias="Paddle-API-Key")
):
    """OCR endpoint with PDF support and security via Paddle-API-Key."""
    start_time = time.time()
    log_process("--- START OCR REQUEST ---")

    # Validate API Key
    if paddle_api_key != PADDLE_API_KEY:
        return create_response(success=False, message="Unauthorized", error_code=401)

    content_type = file.content_type or ""

    if not (content_type.startswith("image/") or content_type == "application/pdf"):
        return create_response(success=False, message="File harus berupa image/* atau PDF", error_code=400)

    try:
        requested_pages = parse_pages_param(pages)
    except HTTPException as e:
        return create_response(success=False, message=e.detail, error_code=e.status_code)

    tmp_paths = []
    try:
        suffix = os.path.splitext(file.filename)[1] if file.filename else ""
        if not suffix:
            suffix = ".pdf" if content_type == "application/pdf" else ".png"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
            tmp_paths.append(tmp_path)
        
        log_process(f"File saved to temp: {tmp_path} ({os.path.getsize(tmp_path)} bytes)")

        pages_result = []

        # === PDF ===
        if content_type == "application/pdf" or suffix.lower() == ".pdf":
            try:
                # 1. Cek Info PDF (Total Halaman) tanpa convert gambar (Sangat Cepat)
                t_info = time.time()
                info = pdfinfo_from_path(tmp_path)
                total_pages = int(info["Pages"])
                log_process(f"PDF Info retrieved in {time.time() - t_info:.2f}s. Total Pages: {total_pages}")
            except Exception as e:
                 return create_response(success=False, message=f"Gagal membaca info PDF: {str(e)}", error_code=400)

            if total_pages == 0:
                return create_response(success=False, message="PDF kosong", error_code=400)

            # 2. Tentukan halaman mana saja yang mau di-process
            if requested_pages is None:
                target_pages = list(range(1, total_pages + 1))
            else:
                # Validasi halaman request
                target_pages = [p for p in requested_pages if 1 <= p <= total_pages]
                if not target_pages:
                    return create_response(success=False, message=f"Halaman tidak valid. Total halaman PDF: {total_pages}", error_code=400)

            # 3. Loop hanya pada halaman yang diminta (Hemat RAM & CPU)
            for page_num in target_pages:
                try:
                    log_process(f"Processing Page {page_num}...")
                    
                    # Convert HANYA 1 halaman spesifik
                    t_conv = time.time()
                    # first_page=page_num, last_page=page_num
                    images = convert_from_path(tmp_path, dpi=200, first_page=page_num, last_page=page_num)
                    log_process(f"  - PDF to Image conversion took {time.time() - t_conv:.2f}s")
                    
                    if not images:
                        continue
                        
                    image = images[0] # Ambil gambar hasil convert

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as img_tmp:
                        image.save(img_tmp.name, format="PNG")
                        img_path = img_tmp.name
                        tmp_paths.append(img_path)

                    t_ocr = time.time()
                    log_process(f"  - Starting OCR prediction for Page {page_num}")
                    
                    # Gunakan get_pipeline()
                    model = get_pipeline()
                    result_json, result_md = process_ocr_output(model.predict(img_path))
                    
                    log_process(f"  - OCR prediction & processing took {time.time() - t_ocr:.2f}s")
                    
                    # Format markdown with page header
                    page_md = f"## Page {page_num}\n\n{result_md}" if result_md else ""
                    
                    pages_result.append({
                        "page": page_num, 
                        "results": result_json,
                        "markdown": page_md
                    })
                except Exception as e:
                    log_process(f"ERROR processing page {page_num}: {e}")
                    continue

        # === IMAGE ===
        else:
            if requested_pages and 1 not in requested_pages:
                return create_response(success=False, message="File gambar hanya memiliki halaman 1", error_code=400)

            t_ocr = time.time()
            log_process("Starting OCR prediction for Image")
            
            # Gunakan get_pipeline()
            model = get_pipeline()
            result_json, result_md = process_ocr_output(model.predict(tmp_path))
            
            log_process(f"OCR prediction & processing took {time.time() - t_ocr:.2f}s")
            
            # Format markdown with page header
            page_md = f"## Page 1\n\n{result_md}" if result_md else ""

            pages_result.append({
                "page": 1, 
                "results": result_json,
                "markdown": page_md
            })

        total_duration = time.time() - start_time
        log_process(f"--- FINISHED OCR REQUEST in {total_duration:.2f}s ---")
        return create_response(success=True, data={"pages": pages_result})

    except Exception as e:
        log_process(f"CRITICAL ERROR: {str(e)}")
        return create_response(success=False, message=f"OCR gagal: {str(e)}", error_code=500)
    finally:
        for p in tmp_paths:
            try: os.remove(p)
            except: pass