from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from paddleocr import PaddleOCRVL
import tempfile
import os

app = FastAPI()

# Load model sekali di awal, supaya tidak reload tiap request
pipeline = PaddleOCRVL()
# Contoh kalau mau aktifkan opsi lain:
# pipeline = PaddleOCRVL(use_doc_orientation_classify=True,
#                        use_doc_unwarping=True,
#                        use_layout_detection=True)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/ocr")
async def ocr_document(file: UploadFile = File(...)):
    # Validasi mimetype dasar
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File harus berupa gambar")

    # Simpan ke file sementara
    try:
        suffix = os.path.splitext(file.filename)[1] if file.filename else ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan file sementara: {e}")

    try:
        # Panggil pipeline
        output = pipeline.predict(tmp_path)

        # Di dokumentasi contoh hanya ada res.print(), res.save_to_json(), res.save_to_markdown()
        # Cara paling “aman” untuk API: ambil data terstruktur dari masing-masing res.
        # Biasanya lib seperti ini punya method / property to_dict() atau serupa.
        # Kalau tidak ada, kamu bisa sementara pakai res.save_to_json ke folder temp lalu baca file JSON-nya.

        results = []
        for idx, res in enumerate(output):
            # *** Bagian ini mungkin perlu disesuaikan dengan API aslinya ***
            # Cek apakah ada method to_dict / to_json:
            if hasattr(res, "to_dict"):
                results.append(res.to_dict())
            elif hasattr(res, "to_json"):
                # Kalau to_json() mengembalikan string JSON
                import json
                results.append(json.loads(res.to_json()))
            else:
                # Fallback: simpan ke json sementara lalu baca
                json_dir = tempfile.mkdtemp()
                res.save_to_json(save_path=json_dir)
                # Library biasanya memberi nama file sendiri, jadi kamu perlu cek file di folder itu
                # Untuk contoh sederhana, ambil semua file .json di folder tersebut
                json_files = [f for f in os.listdir(json_dir) if f.endswith(".json")]
                import json
                for jf in json_files:
                    with open(os.path.join(json_dir, jf), "r", encoding="utf-8") as f:
                        results.append(json.load(f))

        return JSONResponse(content={"results": results})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR gagal: {e}")
    finally:
        # Bersihkan file sementara
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
