import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from paddleocr import PaddleOCRVL
import os
import shutil
import tempfile
import json
from pathlib import Path
from typing import Any, Optional, Dict, List
from pypdf import PdfReader, PdfWriter

app = FastAPI(title="PaddleOCR-VL API")

# Global variable untuk pipeline
pipeline = None

def get_pipeline():
    """Singleton untuk load model agar tidak reload setiap request"""
    global pipeline
    if pipeline is None:
        print("Inisialisasi Model PaddleOCR-VL...")
        pipeline = PaddleOCRVL()
        print("Model berhasil dimuat.")
    return pipeline

@app.on_event("startup")
async def startup_event():
    """Load model saat aplikasi start"""
    get_pipeline()

def create_response(success: bool, data: Any = None, message: str = "") -> Dict[str, Any]:
    """Helper untuk membuat format response standar"""
    return {
        "error": not success,
        "success": success,
        "data": data,
        "message": message
    }

def process_pdf_pages(input_path: str, pages_indices: List[int]) -> str:
    """
    Membuat file PDF baru yang hanya berisi halaman-halaman yang diminta.
    pages_indices diasumsikan 1-based (halaman 1 adalah index 0).
    Mengembalikan path ke file temporary baru.
    """
    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        
        total_pages = len(reader.pages)
        added_pages = 0
        
        for p in pages_indices:
            # Convert 1-based index to 0-based
            p_idx = p - 1
            if 0 <= p_idx < total_pages:
                writer.add_page(reader.pages[p_idx])
                added_pages += 1
            else:
                print(f"Warning: Halaman {p} tidak ditemukan di dokumen (Total: {total_pages})")

        if added_pages == 0:
            raise ValueError("Tidak ada halaman valid yang dipilih untuk diproses.")

        # Simpan ke temp file baru
        with tempfile.NamedTemporaryFile(delete=False, suffix="_filtered.pdf") as tmp:
            writer.write(tmp)
            return tmp.name
            
    except Exception as e:
        raise Exception(f"Gagal memproses halaman PDF: {str(e)}")

@app.get("/health")
async def health_check():
    """Endpoint untuk cek kesehatan service"""
    return create_response(success=True, message="Service is healthy and ready")

@app.post("/document-parsing")
async def document_parsing(
    file: UploadFile = File(...),
    pages: Optional[str] = Form(None)  # Menerima JSON string array, e.g. "[1, 3, 5]"
):
    """
    Endpoint untuk parsing dokumen PDF atau Image.
    - file: File PDF atau Image (.jpg, .png, .bmp)
    - pages: (Optional) JSON String array nomor halaman (1-based) khusus untuk PDF. Contoh: "[1, 2]"
    """
    temp_file_path = None
    processed_file_path = None
    
    ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.bmp'}
    file_ext = Path(file.filename).suffix.lower()
    
    # 1. Validasi ekstensi file
    if file_ext not in ALLOWED_EXTENSIONS:
        return JSONResponse(
            status_code=400,
            content=create_response(
                success=False, 
                message=f"Format file tidak didukung. Gunakan: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        )

    try:
        # 2. Simpan file upload ke temporary file utama
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_file_path = tmp.name

        # 3. Handle filtering halaman jika file adalah PDF dan parameter pages ada
        input_to_model = temp_file_path
        
        if file_ext == '.pdf' and pages:
            try:
                # Parse JSON string ke list integer
                pages_list = json.loads(pages)
                
                if isinstance(pages_list, list) and all(isinstance(i, int) for i in pages_list):
                    if len(pages_list) > 0:
                        # Buat file PDF baru hanya dengan halaman yang dipilih
                        processed_file_path = process_pdf_pages(temp_file_path, pages_list)
                        input_to_model = processed_file_path
                else:
                    print("Format parameter 'pages' tidak valid, memproses seluruh dokumen.")
            except json.JSONDecodeError:
                print("Gagal parsing parameter 'pages', memproses seluruh dokumen.")
            except Exception as e:
                # Jika gagal split, return error atau fallback (disini kita return error agar user tau)
                return JSONResponse(
                    status_code=400,
                    content=create_response(success=False, message=str(e))
                )

        # 4. Dapatkan instance pipeline
        ocr_pipeline = get_pipeline()

        # 5. Proses prediksi
        output = ocr_pipeline.predict(input=input_to_model)

        # 6. Ekstrak hasil Markdown
        markdown_list = []
        for res in output:
            md_info = res.markdown
            markdown_list.append(md_info)

        # Gabungkan halaman markdown
        full_markdown_text = ocr_pipeline.concatenate_markdown_pages(markdown_list)

        return create_response(
            success=True, 
            data={
                "markdown": full_markdown_text,
                "filename": file.filename,
                "pages_processed": len(markdown_list)
            },
            message="Document parsed successfully"
        )

    except Exception as e:
        print(f"Error processing document: {str(e)}")
        return JSONResponse(
            status_code=500,
            content=create_response(success=False, message=f"Internal Server Error: {str(e)}")
        )
        
    finally:
        # 7. Bersihkan semua file temporary
        paths_to_clean = [p for p in [temp_file_path, processed_file_path] if p]
        for path in paths_to_clean:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
