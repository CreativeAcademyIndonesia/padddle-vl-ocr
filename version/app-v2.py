import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from paddleocr import PaddleOCRVL
import os
import shutil
import tempfile
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, List
from pypdf import PdfReader, PdfWriter

app = FastAPI(title="PaddleOCR-VL API")

def print_with_time(message: str):
    """Helper function untuk print dengan timestamp"""
    timestamp = datetime.now().strftime("%H:%M")
    print(f"{timestamp} {message}")

# Setup folder untuk output file yang bisa didownload
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Mount folder outputs agar bisa diakses via URL (misal: http://host/outputs/filename.md)
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

# Global variable untuk pipeline
pipeline = None

def get_pipeline():
    """Singleton untuk load model agar tidak reload setiap request"""
    global pipeline
    if pipeline is None:
        print_with_time("Inisialisasi Model PaddleOCR-VL...")
        pipeline = PaddleOCRVL()
        print_with_time("Model berhasil dimuat.")
    return pipeline

@app.on_event("startup")
async def startup_event():
    """Load model saat aplikasi start"""
    print_with_time("Startup - Load Model PaddleOCR-VL...")
    get_pipeline()

def create_response(success: bool, data: Any = None, message: str = "") -> Dict[str, Any]:
    """Helper untuk membuat format response standar"""
    print_with_time("Membuat Response...")
    return {
        "error": not success,
        "success": success,
        "data": data,
        "message": message
    }

def process_pdf_pages(input_path: str, pages_indices: List[int]) -> str:
    """
    Membuat file PDF baru yang hanya berisi halaman-halaman yang diminta.
    """
    print_with_time("Memproses halaman PDF...")
    try:
        reader = PdfReader(input_path)
        writer = PdfWriter()
        
        total_pages = len(reader.pages)
        added_pages = 0
        
        for p in pages_indices:
            p_idx = p - 1
            if 0 <= p_idx < total_pages:
                writer.add_page(reader.pages[p_idx])
                added_pages += 1
            else:
                print_with_time(f"Warning: Halaman {p} tidak ditemukan di dokumen (Total: {total_pages})")

        if added_pages == 0:
            raise ValueError("Tidak ada halaman valid yang dipilih untuk diproses.")

        with tempfile.NamedTemporaryFile(delete=False, suffix="_filtered.pdf") as tmp:
            writer.write(tmp)
            result = tmp.name
        print_with_time("Halaman PDF berhasil diproses.")
        return result
            
    except Exception as e:
        raise Exception(f"Gagal memproses halaman PDF: {str(e)}")

@app.get("/health")
async def health_check():
    """Endpoint untuk cek kesehatan service"""
    print_with_time("Health check...")
    return create_response(success=True, message="Service is healthy and ready")

@app.post("/document-parsing")
async def document_parsing(
    request: Request,
    file: UploadFile = File(...),
    pages: Optional[str] = Form(None)
):
    """
    Endpoint parsing dokumen dengan output JSON + URL Download File Markdown.
    """
    print_with_time("Document parsing...")
    temp_file_path = None
    processed_file_path = None
    
    ALLOWED_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.bmp'}
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in ALLOWED_EXTENSIONS:
        return JSONResponse(
            status_code=400,
            content=create_response(
                success=False, 
                message=f"Format file tidak didukung. Gunakan: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        )

    try:
        # Simpan file upload
        print_with_time("Menyimpan File...")
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_file_path = tmp.name

        input_to_model = temp_file_path
        
        # Handle PDF Page Selection
        if file_ext == '.pdf' and pages:
            try:
                pages_list = json.loads(pages)
                if isinstance(pages_list, list) and len(pages_list) > 0:
                    processed_file_path = process_pdf_pages(temp_file_path, pages_list)
                    input_to_model = processed_file_path
            except Exception as e:
                print_with_time(f"Gagal filter halaman: {e}")

        # Proses OCR
        print_with_time("OCR Document...")
        ocr_pipeline = get_pipeline()
        output = ocr_pipeline.predict(input=input_to_model)

        print_with_time("Extract Markdown...")
        markdown_list = []
        for res in output:
            markdown_list.append(res.markdown)

        full_markdown_text = ocr_pipeline.concatenate_markdown_pages(markdown_list)

        # --- CLEANING: Unescape karakter khusus ---
        # Mengubah literal '\n' menjadi baris baru sungguhan
        # Mengubah '\"' menjadi kutip sungguhan
        if isinstance(full_markdown_text, str):
            full_markdown_text = full_markdown_text.replace("\\n", "\n").replace('\\"', '"')

        # --- FITUR BARU: SIMPAN FILE MARKDOWN UNTUK DOWNLOAD ---
        
        # Buat nama file unik: originalname_timestamp_uuid.md
        original_stem = Path(file.filename).stem
        unique_id = f"{int(time.time())}_{str(uuid.uuid4())[:8]}"
        output_filename = f"{original_stem}_{unique_id}.md"
        output_filepath = os.path.join(OUTPUT_DIR, output_filename)

        # Tulis ke file fisik
        print_with_time("Menyimpan File Markdown...")
        with open(output_filepath, "w", encoding="utf-8") as f:
            f.write(full_markdown_text)

        # Generate Full Download URL
        print_with_time("Generate Full Download URL...")
        # base_url mengambil scheme (http/https) dan host:port dari request
        base_url = str(request.base_url).rstrip("/")
        download_url = f"{base_url}/outputs/{output_filename}"

        return create_response(
            success=True, 
            data={
                "markdown": full_markdown_text,
                "filename": file.filename,
                "output_filename": output_filename,
                "download_url": download_url,
                "pages_processed": len(markdown_list)
            },
            message="Document parsed successfully"
        )

    except Exception as e:
        print_with_time(f"Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content=create_response(success=False, message=f"Internal Server Error: {str(e)}")
        )
        
    finally:
        print_with_time("Bersihkan file temporary...")
        paths_to_clean = [p for p in [temp_file_path, processed_file_path] if p]
        for path in paths_to_clean:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
