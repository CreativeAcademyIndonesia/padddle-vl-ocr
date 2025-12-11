Flow Production Note Menjadi BOM - Rekap Order : 

TODO List : 
A. Buatkan Struktur create tabel untuk data berikut : 
1. Buat tabel berisi antrian production note yang harus di analisa 
    a. Struktur tabel 
    tabel name : tp_header,
    --system--
CREATE TABLE tp_header (
    -- system
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tp_filename VARCHAR(255),
    helper_prompt TEXT,
    rekap_order_page VARCHAR(50),
    material_fabric_page VARCHAR(50),
    material_accessories_page VARCHAR(50),
    material_pack_page VARCHAR(50),
    STATUS ENUM(
        'waiting',
        'on progress ocr',
        'finish',
        'failed',
        'on progress analysis'
    ) DEFAULT 'waiting',
    stored_images TEXT,
    stored_markdown TEXT,
    stored_full_markdown VARCHAR(5000),
    readme_md TEXT,

    -- business
    contract_no VARCHAR(100),
    customer_buyer VARCHAR(255),
    style VARCHAR(100),
    order_date DATE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
) ENGINE=INNODB DEFAULT CHARSET=utf8mb4;

2. Buat tabel berisi breakdown order 
    a. struktur tabel 
    tabel_name : tp_breakdown_order_size
    id bigint autoincrement primary key, 
    tp_header_id : bigint, 
    color : varchar, 
    size_code : varchar, 
    quantity : varchar, 
    country_code : varchar, 
    shipment_date : date, 
    type : enum [main, breakdown], 
    status : varchar, 
    created_at : timestamp default current_timestamp(),
    updated_at : timestamp default current_timestamp()

3. Buat tabel berisi Material List 
    a. struktur tabel 
    tabel_name : tp_material_list
    id : bigint autoincrement primary key, 
    item_number : int, 
    style : varchar, 
    garmen_color : varchar, 
    material_color : varchar, 
    job_order : int, 
    item_material_description_1 : varchar,
    item_material_description_2 : varchar,
    consumption_yy_mt : decimal, 
    um : varchar, 
    status : varchar,
    created_at : timestamp default current_timestamp(), 
    updated_at : timestamp default current_timestamp(),

    B. Berdasarkan struktur tabel yang saya miliki : 
    -- Tabel --

    -- End Tabel --
    Buatkan modelnya simpan dalam folder Models>Marketing>TechPack

C. Buatkan Tampilan CRUD tp_header pada : marketing>tech-pack anda dapat melihat contoh template view seperti pada 
@resources\views\marketing\production-note\index.blade.php
element tersebut meliputi : 
1. modal filter
2. modall add / create 
3. sidebar 
4. tabel 
5. layout dasar dan lain sebagainya.
sesuaikan dengan model tp_header


Inputan user pada saat create hanay mengirimkan: 
1. Upload file Production Note. 
2. Jelaskan secara singkat bagian dan struktur isi file tersebut. 
3. Sebutkan halaman yang berisi rekap order, tulis dalam format: 1, 2, 3, ... 
4. Sebutkan halaman yang berisi Material List Fabric, tulis dalam format: 1, 2, 3, ... 
5. Sebutkan halaman yang berisi Material List Accessories, tulis dalam format: 1, 2, 3, ... 6. Sebutkan halaman yang berisi Material List Pack, tulis dalam format: 1, 2, 3, ...

C. Buatkan controller filenya di Marketing>TechPack

D. Buatkan Routenya modifikasi pada file : routes\routechunks\marketing.php








================= TODO RESULT ====================
CREATE TABLE tp_header (
    -- system
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tp_filename VARCHAR(255),
    helper_prompt TEXT,
    rekap_order_page VARCHAR(50),
    material_fabric_page VARCHAR(50),
    material_accessories_page VARCHAR(50),
    status ENUM(
        'waiting',
        'on progress ocr',
        'finish',
        'failed',
        'on progress analysis'
    ) DEFAULT 'waiting',
    stored_images TEXT,
    stored_markdown TEXT,
    stored_full_markdown VARCHAR(5000),
    readme_md TEXT,

    -- business
    contract_no VARCHAR(100),
    customer_buyer VARCHAR(255),
    style VARCHAR(100),
    order_date DATE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE tp_breakdown_order_size (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tp_header_id BIGINT UNSIGNED NOT NULL,
    color VARCHAR(100),
    size_code VARCHAR(50),
    quantity VARCHAR(50),
    country_code VARCHAR(10),
    shipment_date DATE,
    type ENUM('main', 'breakdown') NOT NULL,
    status VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_tp_breakdown_order_size_header
        FOREIGN KEY (tp_header_id)
        REFERENCES tp_header(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE tp_material_list (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    item_number INT,
    style VARCHAR(100),
    garmen_color VARCHAR(100),
    material_color VARCHAR(100),
    job_order INT,
    item_material_description_1 VARCHAR(255),
    item_material_description_2 VARCHAR(255),
    consumption_yy_mt DECIMAL(10,4),
    um VARCHAR(20),
    status VARCHAR(50),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
