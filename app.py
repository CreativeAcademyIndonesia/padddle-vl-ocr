from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from paddleocr import PaddleOCRVL
from pdf2image import convert_from_path
import tempfile
import os
import json
from typing import List, Optional

app = FastAPI()

# Load model sekali di awal
pipeline = PaddleOCRVL()
# pipeline = PaddleOCRVL(use_doc_orientation_classify=True,
#                        use_doc_unwarping=True,
#                        use_layout_detection=True)


def ocr_output_to_dict_list(output):
    """
    Konversi list output dari pipeline.predict()
    menjadi list dict yang bisa di-JSON-kan.
    """
    results = []

    # Temp dir untuk fallback save_to_json
    json_dir = tempfile.mkdtemp()

    for res in output:
        # Kalau library sudah sediakan to_dict / to_json pakai itu
        if hasattr(res, "to_dict"):
            results.append(res.to_dict())
        elif hasattr(res, "to_json"):
            results.append(json.loads(res.to_json()))
        else:
            # Fallback: simpan ke json lalu baca lagi
            res.save_to_json(save_path=json_dir)
            json_files = [f for f in os.listdir(json_dir) if f.endswith(".json")]
            for jf in json_files:
                with open(os.path.join(json_dir, jf), "r", encoding="utf-8") as f:
                    results.append(json.load(f))

    # Bersihkan temp json_dir (kalau mau, bisa dibiarkan juga)
    for jf in os.listdir(json_dir):
        try:
            os.remove(os.path.join(json_dir, jf))
        except Exception:
            pass
    try:
        os.rmdir(json_dir)
    except Exception:
        pass

    return results


def parse_pages_param(pages_str: Optional[str]) -> Optional[List[int]]:
    """
    pages_str:
      - None / "" / "null" -> None (artinya semua halaman)
      - "[1,2]"            -> [1, 2]
    """
    if pages_str is None:
        return None

    s = pages_str.strip()
    if s == "" or s.lower() == "null":
        return None

    try:
        data = json.loads(s)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Parameter 'pages' harus berupa JSON array, misalnya [1,2] atau null.",
        )

    if not isinstance(data, list) or not all(isinstance(x, int) and x > 0 for x in data):
        raise HTTPException(
            status_code=400,
            detail="Parameter 'pages' harus berupa list integer positif, misalnya [1,2,3].",
        )

    # Hilangkan duplikat dan urutkan
    pages = sorted(set(data))
    return pages


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ocr")
async def ocr_document(
    file: UploadFile = File(...),
    pages: Optional[str] = Form(None),  # dikirim sebagai teks, misalnya "[1,2]" atau "null"
):
    content_type = file.content_type or ""

    # Hanya terima image/* atau application/pdf
    if not (content_type.startswith("image/") or content_type == "application/pdf"):
        raise HTTPException(
            status_code=400,
            detail="File harus berupa gambar (image/*) atau PDF (application/pdf)",
        )

    # Parse parameter pages
    requested_pages = parse_pages_param(pages)

    tmp_paths = []

    try:
        # Simpan file asli ke temp
        suffix = os.path.splitext(file.filename)[1] if file.filename else ""
        if not suffix:
            # Defaultkan berdasarkan content type
            if content_type == "application/pdf":
                suffix = ".pdf"
            elif content_type.startswith("image/"):
                suffix = ".png"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
            tmp_paths.append(tmp_path)

        pages_result = []

        # === CASE 1: PDF ===
        if content_type == "application/pdf" or suffix.lower() == ".pdf":
            # Convert setiap halaman PDF ke gambar
            pdf_pages = convert_from_path(tmp_path, dpi=200)

            if not pdf_pages:
                raise HTTPException(
                    status_code=400,
                    detail="PDF kosong atau tidak bisa dikonversi",
                )

            total_pages = len(pdf_pages)

            # Kalau requested_pages None -> pakai semua halaman
            if requested_pages is None:
                target_pages = list(range(1, total_pages + 1))
            else:
                # Filter hanya halaman yang valid
                target_pages = [p for p in requested_pages if 1 <= p <= total_pages]
                if not target_pages:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Parameter 'pages' di luar range. PDF hanya memiliki {total_pages} halaman.",
                    )

            # page_number dimulai dari 1
            for page_idx, page in enumerate(pdf_pages, start=1):
                if page_idx not in target_pages:
                    continue

                # Simpan tiap halaman sebagai PNG sementara
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as img_tmp:
                    page.save(img_tmp.name, format="PNG")
                    img_path = img_tmp.name
                    tmp_paths.append(img_path)

                # OCR per halaman
                output = pipeline.predict(img_path)
                page_results = ocr_output_to_dict_list(output)

                pages_result.append(
                    {
                        "page": page_idx,
                        "results": page_results,
                    }
                )

        # === CASE 2: GAMBAR BIASA ===
        else:
            # Untuk image, hanya punya "halaman" ke-1 saja
            if requested_pages is not None and 1 not in requested_pages:
                raise HTTPException(
                    status_code=400,
                    detail="File gambar hanya memiliki page 1. Jika kirim 'pages', pastikan mengandung 1 atau biarkan null.",
                )

            output = pipeline.predict(tmp_path)
            image_results = ocr_output_to_dict_list(output)

            pages_result.append(
                {
                    "page": 1,
                    "results": image_results,
                }
            )

        return JSONResponse(content={"pages": pages_result})

    except HTTPException:
        # Langsung lempar ulang kalau memang sudah HTTPException
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR gagal: {e}")
    finally:
        # Bersihkan semua file sementara
        for p in tmp_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
