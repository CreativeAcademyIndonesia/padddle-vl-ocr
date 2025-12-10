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

OUTPUT_DIR = os.path.join("storage", "agen", "production-note", "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")
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
            
            # --- KONVERSI FULL PDF KE IMAGE ---
            # Tidak ada lagi slicing PDF sebelumnya
            print_with_time("Konversi FULL PDF ke Image High Res (300 DPI)...")
            
            try:
                # Convert SELURUH halaman PDF ke images
                # Gunakan dpi=300 untuk high resolution
                # fmt="jpeg" untuk matching request user
                images = convert_from_path(input_to_model, dpi=300, fmt="jpeg", thread_count=4)
                print_with_time(f"Berhasil convert total {len(images)} halaman ke gambar.")
                
                original_stem = Path(file.filename).stem
                
                for i, img in enumerate(images):
                    # Format nama file image: filename_page_{i+1}.jpg
                    # Page number di filename mulai dari 1
                    page_num = i + 1
                    image_filename = f"{original_stem}_page_{page_num}.jpg"
                    image_path = os.path.join(img_dir, image_filename)
                    
                    # Simpan dengan metadata DPI 300, Format JPEG
                    # Setting sesuai request: Baseline DCT, Huffman coding, YCbCr4:2:0
                    img.save(
                        image_path, 
                        "JPEG", 
                        dpi=(300, 300), 
                        quality=75, 
                        optimize=True, 
                        subsampling=2
                    )
                    
                    # Simpan path dengan info halaman untuk filtering nanti
                    all_image_paths.append({
                        "path": image_path,
                        "page_num": page_num
                    })
                    
            except Exception as e:
                raise Exception(f"Gagal convert PDF ke Image: {str(e)}. Pastikan poppler-utils terinstall.")
            
            # --- FILTER IMAGE UNTUK OCR ---
            # Pilih image mana saja yang akan masuk pipeline OCR berdasarkan input user
            if pages:
                try:
                    pages_list = json.loads(pages)
                    if isinstance(pages_list, list) and len(pages_list) > 0:
                        print_with_time(f"Filtering halaman untuk OCR: {pages_list}")
                        # User input page numbers (1-based index)
                        # Kita ambil image yang page_num-nya ada di list user
                        
                        target_pages = set(pages_list)
                        for img_info in all_image_paths:
                            if img_info["page_num"] in target_pages:
                                ocr_inputs.append(img_info["path"])
                                
                        if not ocr_inputs:
                             print_with_time("Warning: Tidak ada halaman yang cocok dengan filter user. Menggunakan semua halaman.")
                             ocr_inputs = [x["path"] for x in all_image_paths]
                    else:
                        # List kosong atau invalid format, pakai semua
                        ocr_inputs = [x["path"] for x in all_image_paths]
                except Exception as e:
                    print_with_time(f"Gagal parse filter halaman, memproses semua: {e}")
                    ocr_inputs = [x["path"] for x in all_image_paths]
            else:
                # Tidak ada filter, proses semua
                ocr_inputs = [x["path"] for x in all_image_paths]

        else:
            # Jika upload image, simpan di folder image
            saved_file_path = os.path.join(img_dir, file.filename)
            with open(saved_file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            
            ocr_inputs = [saved_file_path]
            # Untuk image upload, all_image_paths juga diisi agar info returned lengkap
            all_image_paths.append({"path": saved_file_path, "page_num": 1})

        # Proses OCR
        print_with_time(f"OCR Document ({len(ocr_inputs)} files)...")
        ocr_pipeline = get_pipeline()
        
        all_outputs = []
        for idx, inp_path in enumerate(ocr_inputs, start=1):
            print_with_time(f"Processing file {idx} of {len(ocr_inputs)}: {inp_path}")
            output = ocr_pipeline.predict(input=inp_path)
            
            # Save markdown per page seperti dokumentasi PaddleOCR-VL
            # Kita simpan di folder 'markdown_pages' di dalam folder tanggal
            markdown_pages_dir = os.path.join(base_path, "markdown_pages")
            os.makedirs(markdown_pages_dir, exist_ok=True)
            
            # Loop setiap result di output (biasanya 1 per file image input)
            for res in output:
                res.save_to_markdown(save_path=markdown_pages_dir)
                
            all_outputs.extend(output)

        print_with_time("Extract Markdown...")
        markdown_list = []
        for res in all_outputs:
            markdown_list.append(res.markdown)

        full_markdown_text = ocr_pipeline.concatenate_markdown_pages(markdown_list)

        # # --- CLEANING ---
        # if isinstance(full_markdown_text, str):
        #     full_markdown_text = full_markdown_text.replace("\\n", "\n").replace('\\"', '"')

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

        # URL untuk file markdown per halaman (stored_readme)
        stored_markdown = []
        markdown_pages_base = os.path.join(base_path, "markdown_pages")
        
        for inp_path in ocr_inputs:
             # Asumsi PaddleOCR-VL menyimpan markdown dengan nama file yang sama dengan input image
             stem = Path(inp_path).stem
             md_filename = f"{stem}.md"
             md_path = os.path.join(markdown_pages_base, md_filename)
             
             if os.path.exists(md_path):
                 rel = os.path.relpath(md_path, OUTPUT_DIR).replace("\\", "/")
                 stored_markdown.append(f"{base_url}/outputs/{rel}")

        return create_response(
            success=True, 
            data={
                "markdown": full_markdown_text,
                "filename": file.filename,
                "output_filename": output_filename,
                "download_url": download_url,
                "stored_images": stored_images_info,
                "stored_markdown": stored_markdown,
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