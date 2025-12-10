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
from pdf2image import convert_from_path

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

def process_pdf_pages(input_path: str, pages_indices: List[int], output_path: Optional[str] = None) -> str:
    """
    Membuat file PDF baru yang hanya berisi halaman-halaman yang diminta.
    Output disimpan ke output_path jika disediakan, jika tidak menggunakan temporary file.
    Menjaga resolusi/kualitas asli halaman.
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
                # add_page di pypdf menyalin halaman reference tanpa re-encoding konten
                # jadi resolusi/kualitas asli terjaga
                writer.add_page(reader.pages[p_idx])
                added_pages += 1
            else:
                print_with_time(f"Warning: Halaman {p} tidak ditemukan di dokumen (Total: {total_pages})")

        if added_pages == 0:
            raise ValueError("Tidak ada halaman valid yang dipilih untuk diproses.")

        if output_path:
            with open(output_path, "wb") as f:
                writer.write(f)
            result = output_path
        else:
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
        
        ocr_inputs = []
        download_url_pdf_filtered = None

        if file_ext == '.pdf':
            # Simpan di folder PDF
            saved_file_path = os.path.join(pdf_dir, file.filename)
            with open(saved_file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            
            # Input model awal adalah file yang disimpan
            input_to_model = saved_file_path
            
            # --- HANDLE PDF PAGE SELECTION ---
            if pages:
                try:
                    pages_list = json.loads(pages)
                    if isinstance(pages_list, list) and len(pages_list) > 0:
                        # Buat nama file filtered
                        original_stem = Path(file.filename).stem
                        filtered_filename = f"{original_stem}_filtered.pdf"
                        processed_file_path = os.path.join(pdf_dir, filtered_filename)
                        
                        # Process dan simpan ke file persistent, bukan temp
                        process_pdf_pages(input_to_model, pages_list, output_path=processed_file_path)
                        
                        input_to_model = processed_file_path # Gunakan subset untuk konversi
                        
                        # Generate URL download untuk filtered PDF
                        rel_path_pdf = os.path.relpath(processed_file_path, OUTPUT_DIR).replace("\\", "/")
                        base_url_req = str(request.base_url).rstrip("/")
                        download_url_pdf_filtered = f"{base_url_req}/outputs/{rel_path_pdf}"
                        
                except Exception as e:
                    print_with_time(f"Gagal filter halaman: {e}")
            
            # --- KONVERSI PDF KE IMAGE ---
            print_with_time("Konversi PDF ke Image High Res (300 DPI)...")
            
            try:
                # Convert PDF (original atau subset) ke images
                # Gunakan dpi=300 untuk high resolution
                images = convert_from_path(input_to_model, dpi=300)
                print_with_time(f"Berhasil convert {len(images)} halaman ke gambar.")
                
                original_stem = Path(file.filename).stem
                
                for i, img in enumerate(images):
                    # Format nama file image: filename_page_{i}.jpg
                    image_filename = f"{original_stem}_page_{i+1}.jpg"
                    image_path = os.path.join(img_dir, image_filename)
                    
                    # Simpan dengan metadata DPI 300
                    img.save(image_path, "JPEG", quality=95, dpi=(300, 300))
                    ocr_inputs.append(image_path)
                    
            except Exception as e:
                raise Exception(f"Gagal convert PDF ke Image: {str(e)}. Pastikan poppler-utils terinstall.")
                
        else:
            # Jika upload image, simpan di folder image
            saved_file_path = os.path.join(img_dir, file.filename)
            with open(saved_file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            
            ocr_inputs = [saved_file_path]

        # Proses OCR
        print_with_time(f"OCR Document ({len(ocr_inputs)} files)...")
        ocr_pipeline = get_pipeline()
        
        all_outputs = []
        for inp_path in ocr_inputs:
            # Predict per file
            output = ocr_pipeline.predict(input=inp_path)
            output.save_to_markdown(save_path="output")
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

        # URL untuk file yang disimpan (images)
        stored_images_info = []
        for inp in ocr_inputs:
             rel = os.path.relpath(inp, OUTPUT_DIR).replace("\\", "/")
             stored_images_info.append(f"{base_url}/outputs/{rel}")

        return create_response(
            success=True, 
            data={
                "markdown": full_markdown_text,
                "filename": file.filename,
                "output_filename": output_filename,
                "download_url": download_url,
                "filtered_pdf_url": download_url_pdf_filtered,
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
        # File temporary sudah tidak digunakan karena filtered PDF sekarang disimpan persistent
        # Namun jika ada file temp lain di masa depan bisa dibersihkan di sini
        pass

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
