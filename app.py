from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Header
from fastapi.responses import JSONResponse
from paddleocr import PaddleOCRVL
from pdf2image import convert_from_path
import tempfile
import os
import shutil
from typing import List, Optional

# Static API Key
PADDLE_API_KEY = "332100185"

app = FastAPI()

# Load model sekali di awal
pipeline = PaddleOCRVL()


def process_ocr_output(output):
    """
    Konversi hasil OCR ke JSON-friendly format dan ekstrak Markdown builtin.
    Returns: (list_of_dicts, markdown_string)
    """
    results = []
    markdowns = []
    
    # Gunakan direktori sementara yang aman
    temp_dir = tempfile.mkdtemp()

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
    """Parse parameter pages. null → semua halaman."""
    if value is None or value.strip() == "" or value.lower() == "null":
        return None

    try:
        decoded = json.loads(value)
    except:
        raise HTTPException(400, detail="Format 'pages' harus JSON array, contoh: [1,2] atau null")

    if not isinstance(decoded, list) or not all(isinstance(x, int) and x > 0 for x in decoded):
        raise HTTPException(400, detail="'pages' harus berupa array angka contoh: [1,2]")

    return sorted(set(decoded))


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

    # Validate API Key
    if paddle_api_key != PADDLE_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    content_type = file.content_type or ""

    if not (content_type.startswith("image/") or content_type == "application/pdf"):
        raise HTTPException(400, "File harus berupa image/* atau PDF")

    requested_pages = parse_pages_param(pages)

    tmp_paths = []
    try:
        suffix = os.path.splitext(file.filename)[1] if file.filename else ""
        if not suffix:
            suffix = ".pdf" if content_type == "application/pdf" else ".png"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
            tmp_paths.append(tmp_path)

        pages_result = []

        # === PDF ===
        if content_type == "application/pdf" or suffix.lower() == ".pdf":
            pdf_pages = convert_from_path(tmp_path, dpi=200)
            if not pdf_pages:
                raise HTTPException(400, "PDF tidak valid atau kosong")

            total_pages = len(pdf_pages)
            if requested_pages is None:
                target_pages = list(range(1, total_pages + 1))
            else:
                target_pages = [p for p in requested_pages if 1 <= p <= total_pages]

                if not target_pages:
                    raise HTTPException(400, f"Halaman tidak valid. Total halaman PDF: {total_pages}")

            for page_num, image in enumerate(pdf_pages, start=1):
                if page_num not in target_pages:
                    continue

                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as img_tmp:
                    image.save(img_tmp.name, format="PNG")
                    img_path = img_tmp.name
                    tmp_paths.append(img_path)

                result_json, result_md = process_ocr_output(pipeline.predict(img_path))
                
                # Format markdown with page header
                page_md = f"## Page {page_num}\n\n{result_md}" if result_md else ""
                
                pages_result.append({
                    "page": page_num, 
                    "results": result_json,
                    "markdown": page_md
                })

        # === IMAGE ===
        else:
            if requested_pages and 1 not in requested_pages:
                raise HTTPException(400, "File gambar hanya memiliki halaman 1")

            result_json, result_md = process_ocr_output(pipeline.predict(tmp_path))
            
            # Format markdown with page header
            page_md = f"## Page 1\n\n{result_md}" if result_md else ""

            pages_result.append({
                "page": 1, 
                "results": result_json,
                "markdown": page_md
            })

        return JSONResponse(content={"pages": pages_result})

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"OCR gagal: {e}")
    finally:
        for p in tmp_paths:
            try: os.remove(p)
            except: pass