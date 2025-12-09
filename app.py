import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from paddleocr import PaddleOCRVL
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional, Dict

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

@app.get("/health")
async def health_check():
    """Endpoint untuk cek kesehatan service"""
    return create_response(success=True, message="Service is healthy and ready")

@app.post("/document-parsing")
async def document_parsing(file: UploadFile = File(...)):
    """
    Endpoint untuk parsing dokumen PDF.
    Menerima file PDF, menyimpannya sementara, memproses dengan PaddleOCR-VL,
    dan mengembalikan hasil markdown.
    """
    temp_file_path = None
    
    # Validasi ekstensi file
    if not file.filename.lower().endswith('.pdf'):
        return JSONResponse(
            status_code=400,
            content=create_response(success=False, message="File harus berformat PDF")
        )

    try:
        # 1. Simpan file upload ke temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_file_path = tmp.name

        # 2. Dapatkan instance pipeline
        ocr_pipeline = get_pipeline()

        # 3. Proses prediksi
        # Note: Operasi ini blocking, dalam production traffic tinggi 
        # sebaiknya dijalankan di threadpool atau worker terpisah.
        output = ocr_pipeline.predict(input=temp_file_path)

        # 4. Ekstrak hasil Markdown
        markdown_list = []
        
        # Kita hanya mengambil konten markdown text untuk response API JSON
        # Jika butuh gambar hasil crop, logic-nya perlu disesuaikan (misal return zip atau url)
        for res in output:
            md_info = res.markdown
            markdown_list.append(md_info)

        # Gabungkan halaman markdown
        full_markdown_text = ocr_pipeline.concatenate_markdown_pages(markdown_list)

        # 5. Return success response
        return create_response(
            success=True, 
            data={
                "markdown": full_markdown_text,
                "filename": file.filename
            },
            message="Document parsed successfully"
        )

    except Exception as e:
        # Log error sebenarnya di server console
        print(f"Error processing document: {str(e)}")
        return JSONResponse(
            status_code=500,
            content=create_response(success=False, message=f"Internal Server Error: {str(e)}")
        )
        
    finally:
        # 6. Bersihkan file temporary
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception as cleanup_error:
                print(f"Failed to remove temp file: {cleanup_error}")

if __name__ == "__main__":
    # Menjalankan server uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)