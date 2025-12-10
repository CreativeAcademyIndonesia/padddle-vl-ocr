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