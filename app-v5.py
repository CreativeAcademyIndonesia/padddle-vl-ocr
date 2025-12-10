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
import fitz  # PyMuPDF

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
        # --- STRUKTUR FOLDER: outputs/YYYY/YYYY.MM.DD/{pdf|image}/filename ---
        now = datetime.now()
        year_str = now.strftime("%Y")
        date_str = now.strftime("%Y.%m.%d")
        
        base_path = os.path.join(OUTPUT_DIR, year_str, date_str)
        pdf_dir = os.path.join(base_path, "pdf")
        img_dir = os.path.join(base_path, "image")
        
        os.makedirs(pdf_dir, exist_ok=True)
        os.makedirs(img_dir, exist_ok=True)
        
        print_with_time(f"Output directories: {pdf_dir}, {img_dir}")

        # Simpan file upload ke lokasi persistent
        print_with_time("Menyimpan File Upload...")
        
        all_image_paths = [] # List semua gambar hasil convert (semua halaman)
        ocr_inputs = []      # List gambar yang AKAN di-OCR (sesuai filter user)

        if file_ext == '.pdf':
            # Simpan PDF Original
            saved_file_path = os.path.join(pdf_dir, file.filename)
            with open(saved_file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            
            input_to_model = saved_file_path
            
            # --- KONVERSI FULL PDF KE IMAGE (PyMuPDF) ---
            print_with_time("Konversi FULL PDF ke Image High Res (300 DPI) via PyMuPDF...")
            
            try:
                # Open PDF dengan PyMuPDF
                doc = fitz.open(input_to_model)
                print_with_time(f"Total halaman PDF: {len(doc)}")
                
                original_stem = Path(file.filename).stem
                
                # Matrix untuk resolusi 300 DPI
                # Default 72 DPI -> zoom = 300/72 ~= 4.167
                zoom = 300 / 72
                matrix = fitz.Matrix(zoom, zoom)
                
                for i in range(len(doc)):
                    page = doc.load_page(i)
                    pix = page.get_pixmap(matrix=matrix, alpha=False) # alpha=False -> RGB, no transparency
                    
                    # Format nama file image: filename_page_{i+1}.png
                    page_num = i + 1
                    image_filename = f"{original_stem}_page_{page_num}.png"
                    image_path = os.path.join(img_dir, image_filename)
                    
                    # Simpan sebagai PNG
                    pix.save(image_path)
                    
                    # Simpan path dengan info halaman untuk filtering nanti
                    all_image_paths.append({
                        "path": image_path,
                        "page_num": page_num
                    })
                
                print_with_time(f"Berhasil convert {len(doc)} halaman ke gambar.")
                doc.close()
                    
            except Exception as e:
                raise Exception(f"Gagal convert PDF ke Image dengan PyMuPDF: {str(e)}")
            
            # --- FILTER IMAGE UNTUK OCR ---
            if pages:
                try:
                    pages_list = json.loads(pages)
                    if isinstance(pages_list, list) and len(pages_list) > 0:
                        print_with_time(f"Filtering halaman untuk OCR: {pages_list}")
                        target_pages = set(pages_list)
                        for img_info in all_image_paths:
                            if img_info["page_num"] in target_pages:
                                ocr_inputs.append(img_info["path"])
                                
                        if not ocr_inputs:
                             print_with_time("Warning: Tidak ada halaman yang cocok dengan filter user. Menggunakan semua halaman.")
                             ocr_inputs = [x["path"] for x in all_image_paths]
                    else:
                        ocr_inputs = [x["path"] for x in all_image_paths]
                except Exception as e:
                    print_with_time(f"Gagal parse filter halaman, memproses semua: {e}")
                    ocr_inputs = [x["path"] for x in all_image_paths]
            else:
                ocr_inputs = [x["path"] for x in all_image_paths]

        else:
            # Jika upload image, simpan di folder image
            saved_file_path = os.path.join(img_dir, file.filename)
            with open(saved_file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            
            ocr_inputs = [saved_file_path]
            all_image_paths.append({"path": saved_file_path, "page_num": 1})

        # Proses OCR
        print_with_time(f"OCR Document ({len(ocr_inputs)} files)...")
        ocr_pipeline = get_pipeline()
        
        all_outputs = []
        for inp_path in ocr_inputs:
            # Predict per file
            output = ocr_pipeline.predict(input=inp_path)
            
            # Save markdown per page
            markdown_pages_dir = os.path.join(base_path, "markdown_pages")
            os.makedirs(markdown_pages_dir, exist_ok=True)
            
            for res in output:
                res.save_to_markdown(save_path=markdown_pages_dir)
                
            all_outputs.extend(output)

        print_with_time("Extract Markdown...")
        markdown_list = []
        for res in all_outputs:
            markdown_list.append(res.markdown)

        full_markdown_text = ocr_pipeline.concatenate_markdown_pages(markdown_list)

        # --- CLEANING ---
        if isinstance(full_markdown_text, str):
            full_markdown_text = full_markdown_text.replace("\\n", "\n").replace('\\"', '"')

        # --- SIMPAN MARKDOWN ---
        original_stem = Path(file.filename).stem
        unique_id = f"{int(time.time())}"
        output_filename = f"{original_stem}_{unique_id}.md"
        output_filepath = os.path.join(base_path, output_filename)

        print_with_time("Menyimpan File Markdown...")
        with open(output_filepath, "w", encoding="utf-8") as f:
            f.write(full_markdown_text)

        # Generate Full Download URL Markdown
        print_with_time("Generate Full Download URL...")
        base_url = str(request.base_url).rstrip("/")
        rel_path = os.path.relpath(output_filepath, OUTPUT_DIR).replace("\\", "/")
        download_url = f"{base_url}/outputs/{rel_path}"

        # URL untuk file image yang disimpan (SEMUA converted images, bukan cuma yg di-OCR)
        stored_images_info = []
        for img_info in all_image_paths:
             rel = os.path.relpath(img_info["path"], OUTPUT_DIR).replace("\\", "/")
             stored_images_info.append(f"{base_url}/outputs/{rel}")

        return create_response(
            success=True, 
            data={
                "markdown": full_markdown_text,
                "filename": file.filename,
                "output_filename": output_filename,
                "download_url": download_url,
                "stored_images": stored_images_info,
                "pages_processed": len(markdown_list)
            },
            message="Document parsed successfully"
        )

    except Exception as e:
        print_with_time(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content=create_response(success=False, message=f"Internal Server Error: {str(e)}")
        )
        
    finally:
        pass

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
