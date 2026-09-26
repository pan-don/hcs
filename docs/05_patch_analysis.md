<div align="center">

# PANDUAN METODOLOGI ANALISIS PETAK KONSERVASI (PATCH ANALYSIS)
### Implementasi Pohon Keputusan HCSA Toolkit Modul 5 Berbasis Morfometri Kawasan Inti, Konektivitas Lanskap, dan Pemodelan Zonasi Kesesuaian Lahan
**Studi Kasus: Lanskap Hutan Kabupaten Bogor, Jawa Barat**

---

<img src="../assets/patch_decision_tree.png" alt="Bagan Alur Pohon Keputusan Patch Analysis HCSA Modul 5" width="850"/>

<p><em>Gambar 1: Bagan Alur Pohon Keputusan (Decision Tree) Patch Analysis Standar HCSA Toolkit Modul 5</em></p>

</div>

---

## 1. Landasan Ekologis Analisis Petak Konservasi

Keberlanjutan ekologis suatu bentang alam hutan tidak semata-mata ditentukan oleh luas kumulatif tutupan tajuk, melainkan sangat dipengaruhi oleh **konfigurasi spasial, derajat fragmentasi, bentuk geometri petak, dan keutuhan kawasan inti (*Core Area*)**. 

Dalam ekologi lanskap tropis, batas luar petak hutan mengalami fenomena degradasi mikroklimat yang dikenal sebagai **efek tepi (*Edge Effect*)**. Perubahan kondisi abiotik berupa peningkatan radiasi matahari langsung, kenaikan fluktuasi temperatur, penurunan kelembapan udara relatif, dan penetrasi hembusan angin kering dapat merambah sejauh **100 meter** dari batas terluar petak ke arah dalam. Efek tepi ini memicu mortalitas pohon klimaks dewasa, meningkatkan kerentanan terhadap kebakaran bawah tajuk, serta mempercepat invasi vegetasi herba dan tumbuhan merambat eksotis.

Oleh karena itu, **HCSA Toolkit Modul 5 (*HCS Forest Patch Analysis and Protection*)** menetapkan protokol analisis petak hutan berbasis pohon keputusan (*Patch Analysis Decision Tree*). Protokol ini mengklasifikasikan petak-petak hutan potensial HCS ke dalam kategori prioritas konservasi secara objektif, mengevaluasi konektivitas koridor ekologis, dan mengalokasikan ruang lanskap secara harmonis antara fungsi pelestarian keanekaragaman hayati dan kebutuhan pembangunan berkelanjutan.

---

## 2. Integrasi Data Masukan dan Lapisan Spasial Pendukung

Berdasarkan arsitektur yang diimplementasikan pada [hcs_patch_analysis.py](file:///e:/Mycourse/Magang%20Telkomsat/HCS/hcs_patch_analysis.py), analisis petak mengintegrasikan berkas raster dan vektor geospasial berikut:

1. **Raster Stratifikasi HCS Tahunan (`output/stratification/HCS_Stratification_{Tahun}_Final.tif`):**
   Lapisan masukan utama yang merepresentasikan distribusi spasial 6 strata vegetasi. Piksel kelas 3 s/d 6 (YRF, LDF, MDF, dan HDF) diekstraksi sebagai masker biner vegetasi hutan potensial HCS.
2. **Kawasan Lindung Resmi (*Protected Areas* - `data/vector/protected_area.shp`):**
   Lapisan batas resmi kawasan pelestarian alam dan suaka alam di Kabupaten Bogor, mencakup Taman Nasional Gunung Halimun Salak (TNGHS), Taman Nasional Gunung Gede Pangrango (TNGGP), Cagar Alam Yanlapa, Telaga Warna, serta kawasan Hutan Lindung Perum Perhutani. Lapisan ini berperan sebagai jangkar konservasi utama (*conservation anchors*).
3. **Batas Administrasi Wilayah (`data/vector/bogor_administrasi_kabkota.shp`):**
   Poligon batas yurisdiksi Kabupaten Bogor yang digunakan untuk pemotongan spasial (*spatial masking*) dan standardisasi kartografis.

---

## 3. Tahapan Komputasi Morfometri dan Analisis Spasial Petak

Analisis petak pada [hcs_patch_analysis.py](file:///e:/Mycourse/Magang%20Telkomsat/HCS/hcs_patch_analysis.py) dijalankan melalui 8 tahapan komputasi sekuensial yang terstruktur:

```
[Raster Stratifikasi HCS Final] + [Lapisan Vektor Kawasan Lindung]
                                │
                                ▼
  [1/8] Ekstraksi Masker Biner HCS (Kelas 3–6) & Pra-Pemrosesan Morfologis:
        ├── Penyaringan MMU Petak (Sieve Mask < 0,5 ha)
        └── Penutupan Celah Kanopi Internal (Fill Canopy Gaps <= 0,5 ha)
                                │
                                ▼
  [2/8] Pelabelan Petak Terhubung (8-Connectivity Patch Labeling)
                                │
                                ▼
  [3/8] Erosi Kawasan Inti (Inner Buffer 100 m / Radius Lingkaran)
        └── Ekstraksi Kawasan Inti (Core Area Mask)
                                │
                                ▼
  [4/8] Kuantifikasi Metrik Geometri Petak (Vektorisasi NumPy):
        ├── Luas Petak Total (A, ha) & Luas Inti (A_core, ha)
        ├── Keliling Petak (Perimeter - P, meter)
        └── Indeks Bentuk: SI = P / (2 * sqrt(pi * A_m2))
                                │
                                ▼
  [5/8] Klasifikasi Prioritas Berdasarkan Luas Inti (HPP, MPP, LPP)
                                │
                                ▼
  [6/8] Analisis Konektivitas Koridor (Jarak Euclidean EDT <= 200 m)
        └── Penapisan Risiko Fragmentasi Bentuk (SI > 2,5)
                                │
                                ▼
  [7/8] Penerapan Pohon Keputusan HCSA (Langkah 1 s/d 6):
        └── CONSERVE, CORRIDOR, ASSESS (Pre-RBA), atau DEVELOP
                                │
                                ▼
  [8/8] Pembangkitan Peta Keputusan Zonasi Lahan Lanskap (5 Kelas):
        ├── Penyaringan Derau Spasial MMU (Rasterio Sieve 6 piksel)
        ├── Ekspor GeoTIFF Berwarna (+ Simbologi QGIS .qml & ArcGIS .clr)
        ├── Penyusunan Rekapitulasi Statistik Tabel CSV
        └── Pembuatan Layout Peta Tematik Kartografis dan Dashboard
```

---

## 4. Parameter dan Formulasi Matematis Metrik Spasial

### 4.1 Penyaringan MMU dan Pengisian Celah Kanopi Internal
Sesuai panduan HCSA Modul 5, masker biner vegetasi hutan disaring sebelum pemisahan petak dilakukan:
- **Penyaringan Fragmen Sub-MMU (`sieve_patch_mask`):** Fragmen vegetasi yang berukuran $< 0,5\text{ ha}$ (kurang dari 6 piksel pada grid $30\text{ m}$) dieliminasi agar tidak menjadi artefak petak atau disalahartikan sebagai koridor.
- **Penutupan Lubang Celah Kanopi Internal (`fill_internal_canopy_gaps`):** Enklave non-hutan internal yang terkurung sepenuhnya di dalam matriks petak hutan dengan luas $\le 0,5\text{ ha}$ diisi secara otomatis menjadi vegetasi hutan. Hal ini mencegah lubang kanopi kecil memecah kawasan inti secara artifisial.

### 4.2 Erosi Kawasan Inti (*Core Area Buffer Erosion*)
Kawasan inti diisolasi dengan mereduksi batas luar petak sejauh **100 meter** ke arah dalam (`BUFFER_INNER_M = 100.0`):
- Pada resolusi $30\text{ m}$, radius erosi setara dengan $r = \lceil 100 / 30 \rceil = 4\text{ piksel}$.
- Diterapkan elemen penstruktur lingkaran (*circular structuring element*) menggunakan formula $x^2 + y^2 \le r^2$:
  $$\text{Core Mask} = \text{Patch Mask} \ominus B_{100\text{m}}$$
Piksel yang tetap bertahan pasca-erosi dikuantifikasi sebagai Luas Kawasan Inti ($A_{\text{core}}$).

### 4.3 Kategori Prioritas Petak Berdasarkan Kawasan Inti
1. **High Priority Patch (HPP):** Petak dengan luas kawasan inti $A_{\text{core}} > 100\text{ ha}$. Memiliki daya lenting ekologis tinggi, keanekaragaman genetik terjamin, dan **wajib dilindungi seutuhnya**.
2. **Medium Priority Patch (MPP):** Petak dengan luas kawasan inti $10\text{ ha} \le A_{\text{core}} \le 100\text{ ha}$. Berperan sebagai kawasan penyangga vital dan habitat perantara.
3. **Low Priority Patch (LPP):** Petak dengan luas kawasan inti $A_{\text{core}} < 10\text{ ha}$, termasuk petak-petak sempit yang kawasan intinya habis tereduksi oleh erosi penyangga 100 m.

### 4.4 Indeks Bentuk (*Shape Index* - SI) dan Penapisan Risiko Lanskap
Untuk mengidentifikasi petak yang mengalami fragmentasi ekstrem atau memiliki konfigurasi memanjang yang rentan, dihitung rasio kekompakan bentuk (*Shape Index*):
$$SI = \frac{P}{2 \sqrt{\pi \cdot A_{\text{m}^2}}}$$
- Nilai $SI = 1,0$ merepresentasikan bentuk lingkaran sempurna (rasio tepi-ke-luas paling minimum).
- Semakin tinggi nilai $SI$, semakin tidak teratur dan memanjang bentuk petak tersebut.
- Petak terisolasi dengan **$SI > 2,5$** (`SI_RISK_THRESHOLD = 2.5`) diklasifikasikan sebagai **Kandidat Berisiko Tinggi (*High Risk / Degraded Corridor*)** yang membutuhkan kajian keanekaragaman hayati cepat (*Rapid Biodiversity Assessment* - RBA).

### 4.5 Analisis Konektivitas Jarak Euclidean (EDT)
Lapisan jangkar konservasi (*anchor mask*) dibangun dari penggabungan kawasan lindung resmi (*Protected Areas*) dan petak berstatus HPP:
$$\text{Anchor Mask} = \text{Clip}(\text{Protected Area Mask} + \text{HPP Mask}, 0, 1)$$
Transformasi jarak Euclidean (*Euclidean Distance Transform* - EDT) dihitung terhadap piksel non-jangkar. Jarak minimum petak ke jangkar konservasi menentukan status keterhubungannya:
- **MPP:** Apabila jarak terdekat $< 30\text{ m}$ (bersinggungan langsung dengan kawasan lindung/HPP), petak berstatus `protect (MPP adjacent)`. Jika tidak, berstatus `assess`.
- **LPP:** Apabila jarak terdekat $\le 200\text{ m}$ (`CORRIDOR_DIST_M = 200.0`), petak dialokasikan sebagai `corridor`. Jika jarak $> 200\text{ m}$, petak berstatus `isolated`.

---

## 5. Implementasi Logika Pohon Keputusan HCSA (Langkah 1–6)

Keputusan akhir alokasi ruang bagi setiap petak vegetasi ditentukan melalui aturan pohon keputusan terstruktur pada fungsi `apply_hcsa_decision_tree()`:

| Kategori Prioritas Petak | Status Keterhubungan / Jarak | Karakteristik Bentuk Geometri | Keputusan HCSA (`final_decision`) | Kode Zonasi Akhir | Rekomendasi Aksi Pengelolaan Lanskap |
|:---|:---|:---:|:---:|:---:|:---|
| **High Priority Patch (HPP)** | Mandiri / Terhubung | Semua bentuk | **`CONSERVE`** | **1** | **Perlindungan Mutlak:** Kawasan inti luas (>100 ha) wajib dipertahankan; dilarang keras untuk konversi. |
| **Medium Priority Patch (MPP)** | Bersinggungan langsung dengan Kawasan Lindung / HPP | Semua bentuk | **`CONSERVE`** | **1** | **Perlindungan Penyangga:** Berfungsi memperluas kawasan inti ekologis terpadu. |
| **Medium Priority Patch (MPP)** | Terisolasi ($> 0\text{ m}$) | Semua bentuk | **`ASSESS`** | **3** | **Kaji Lapangan Pre-RBA:** Memiliki kawasan inti 10–100 ha; wajib dievaluasi nilai keanekaragaman hayati sebelum keputusan alokasi. |
| **Low Priority Patch (LPP)** | Berada dalam radius $\le 200\text{ m}$ dari Jangkar | Semua bentuk | **`CORRIDOR`** | **2** | **Konservasi Koridor:** Berfungsi sebagai batu loncatan (*stepping stone*) pergerakan satwa liar dan konektivitas lanskap. |
| **Low Priority Patch (LPP)** | Terisolasi ($> 200\text{ m}$) | Risiko Tinggi ($SI > 2,5$) | **`ASSESS`** | **3** | **Kaji Lapangan RBA:** Bentuk memanjang atau sempadan sungai terfragmentasi yang potensial bernilai konservasi tinggi. |
| **Low Priority Patch (LPP)** | Terisolasi ($> 200\text{ m}$) | Normal ($SI \le 2,5$) | **`DEVELOP`** | **4** | **Indikasi Layak Dikembangkan:** Petak terisolasi kecil yang diturunkan (*dropped*) sesuai HCSA Tahap 6 karena daya tahan ekologis rendah. |

---

## 6. Skema Klasifikasi Peta Keputusan Zonasi Lahan Lanskap

<div align="center">

<img src="../assets/hcs_patch_priority_map.png" alt="Peta Keputusan Zonasi HCSA dan Kelayakan Pembangunan" width="850"/>

<p><em>Gambar 2: Peta Hasil Zonasi Keputusan HCSA dan Kelayakan Pembangunan Lanskap Kabupaten Bogor</em></p>

</div>

Peta keputusan akhir mengintegrasikan keputusan tingkat petak, kawasan lindung legal, dan seluruh latar belakang lanskap non-HCS ke dalam **5 kelas zonasi komprehensif** (`HCSA_DECISION_CLASSES`):

| Kode | Nama Zona HCSA | Deskripsi Ekologis dan Operasional | Warna Representasi (HEX) | Komposisi Warna RGBA |
|:---:|:---|:---|:---:|:---:|
| **1** | **HCS Konservasi (*Conserve*)** | HPP, MPP Terhubung, dan Kawasan Lindung Resmi yang wajib dilindungi mutlak. | `#1B5E20` | `(27, 94, 32, 255)` |
| **2** | **HCS Koridor (*Corridor*)** | Petak LPP dalam jarak $\le 200\text{ m}$ dari kawasan konservasi sebagai koridor penghubung. | `#7CB342` | `(124, 179, 66, 255)` |
| **3** | **HCS Kaji Lapangan (*Pre-RBA / Assess*)** | MPP Terisolasi (inti 10–100 ha) dan LPP Terisolasi Berisiko Tinggi ($SI > 2,5$) yang mewajibkan survei lapangan. | `#FB8C00` | `(251, 140, 0, 255)` |
| **4** | **Indikasi Layak Dikembangkan (*Developable*)** | Areal Non-HCS (Lahan Terbuka dan Semak Belukar) serta fragmen LPP terisolasi yang telah di-drop secara formal. | `#FFEE58` | `(255, 238, 88, 255)` |
| **5** | **Non-Vegetasi / Non-Target** | Badan air permanen, permukiman pedesaan/perkotaan, dan infrastruktur terbangun. | `#B0BEC5` | `(176, 190, 197, 255)` |

### 6.1 Pembersihan Derau Pasca-Zonasi (*Zonation Sieve Filter*)
Peta zonasi akhir dibersihkan dari derau garam-merica menggunakan algoritma `clean_landscape_zonation()` berbasis `rasterio.features.sieve()` dengan ukuran jendela 6 piksel (`CLEAN_ZONATION_MMU = 6`). Pulau-pulau piksel terisolasi yang lebih kecil dari ambang batas tersebut secara otomatis dilebur ke dalam poligon kelas dominan di sekitarnya tanpa mengubah struktur kawasan inti utama.

---

## 7. Format Keluaran Data dan Produk Kartografis

Eksekusi [hcs_patch_analysis.py](file:///e:/Mycourse/Magang%20Telkomsat/HCS/hcs_patch_analysis.py) menghasilkan luaran geospasial dan dokumen analitis yang tersimpan di direktori `output/patch_analysis/{Tahun}/`:

1. **Raster Peta Keputusan Zonasi Lahan (`HCSA_Final_Decision_Map_{Tahun}.tif`):**
   Berkas GeoTIFF beresolusi 30 meter terproyeksi UTM 48S, dilengkapi metadata palet warna resmi HCSA. Disertai berkas pendukung *styling* otomatis untuk perangkat lunak SIG:
   - Berkas format QGIS Style XML (`.qml`)
   - Berkas format ArcGIS Color Table (`.clr`)
2. **Peta Tematik Kartografis Standar Publikasi (`HCSA_Land_Suitability_Map_{Tahun}.png`):**
   Tata letak kartografis resolusi tinggi (300 DPI) yang memuat batas administrasi resmi Kabupaten Bogor, garis kisi koordinat UTM (Easting/Northing dalam kilometer), legenda zonasi terstruktur, dan grafik batang vertikal distribusi luas wilayah per zona.
3. **Laporan Tabel Keputusan Petak (`HCSA_Decision_Summary_{Tahun}.csv`):**
   Rekapitulasi kuantitatif luas (hektare), jumlah piksel, dan persentase proporsi untuk setiap zona HCSA.
4. **Analisis Runtun Waktu Multi-Tahun (`HCSA_MultiYear_Decision_Summary.csv` & `HCSA_MultiYear_Decision_Dashboard.png`):**
   Mengkompilasi trayektori dinamika zonasi antar-tahun (misalnya 2021 hingga 2025), melacak fluktuasi luas kawasan lindung, laju pelepasan petak LPP yang di-drop, dan pergeseran alokasi ruang lanskap secara terpadu.

---

## 8. Daftar Pustaka

- **[1]** HCS Approach Steering Group, "HCSA Toolkit v2.0, Module 5: HCS forest patch analysis and protection," High Carbon Stock Approach, 2017.
- **[2]** HCS Approach Steering Group, "Advice Note 03: HCV–HCSA assessments: Defining patch boundaries and application of Decision Tree," High Carbon Stock Approach, 2020.
- **[3]** R. T. T. Forman, *Land Mosaics: The Ecology of Landscapes and Regions*, Cambridge University Press, 1995.
- **[4]** Pemerintah Republik Indonesia, "Keputusan Presiden No. 32 Tahun 1990 tentang Pengelolaan Kawasan Lindung," Lembaran Negara RI, 1990.
- **[5]** B. L. Turner et al., *Global Land Project: Science Plan and Implementation Strategy*, IGBP Report No. 53, 2005.
