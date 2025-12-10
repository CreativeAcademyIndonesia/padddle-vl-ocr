Flow Production Note Menjadi BOM - Rekap Order : 
1. Buat tabel berisi antrian production note yang harus di analisa 
    a. Struktur tabel 
    tabel name : mkt_queue_pn,
    id bigint autoincrement primary key, 
    filename : varchar,
    helper_prompt : text,
    rekap_order_page : varchar,
    material_fabric_page : varchar, 
    material_accessories_page : varchar, 
    status : enum waiting, on progress ocr, finish, failed, on progress analysis
    stored_images : text,
    stored_markdown : text,
    stored_full_markdown : varchar,
    readme_md : text,
    created_at : timestamp default current_timestamp()
    updated_at : timestamp default current_timestamp()




Inputan user : 
1. Upload file Production Note. 
2. Jelaskan secara singkat bagian dan struktur isi file tersebut. 
3. Sebutkan halaman yang berisi rekap order, tulis dalam format: 1, 2, 3, ... 
4. Sebutkan halaman yang berisi Material List Fabric, tulis dalam format: 1, 2, 3, ... 
5. Sebutkan halaman yang berisi Material List Accessories, tulis dalam format: 1, 2, 3, ... 6. Sebutkan halaman yang berisi Material List Pack, tulis dalam format: 1, 2, 3, ...