<div align="center">

# PANDUAN METODOLOGI STRATIFIKASI HIGH CARBON STOCK (HCS)
### Klasifikasi Enam Strata Vegetasi Berdasarkan Integrasi Kepadatan Biomassa di Atas Permukaan (AGBD), Penapisan Tutupan Lahan, dan Protokol *Downgrading* MMU
**Studi Kasus: Lanskap Hutan Kabupaten Bogor, Jawa Barat**

---

<img src="../assets/hcs_strata_illustration.png" alt="Ilustrasi Profil Enam Strata HCS" width="850"/>

<p><em>Gambar 1: Profil Struktur Arsitektur Kanopi, Kerapatan Vegetasi, dan Kepadatan Biomassa pada Enam Strata HCSA</em></p>

</div>

---

## 1. Konsep Dasar Pendekatan Stok Karbon Tinggi (*High Carbon Stock Approach*)

*High Carbon Stock Approach* (HCSA) merupakan metodologi tata guna lahan global yang dirancang untuk mendukung implementasi komitmen nol-deforestasi (*Zero Deforestation*) di kawasan tropis. Metodologi ini menyediakan kerangka kerja praktis dan terstandarisasi untuk membedakan:
1. **Hutan Bernilai Konservasi Tinggi (Potensial HCS):** Kawasan bervegetasi hutan alami yang memiliki simpanan karbon signifikan, struktur kanopi berlapis, serta keanekaragaman hayati tinggi yang wajib dipertahankan dan dilindungi sepenuhnya dari deforestasi maupun konversi lahan.
2. **Lahan Terdegradasi dan Rendah Karbon (Bukan HCS):** Kawasan semak belukar muda atau lahan terbuka dengan biomassa dan nilai ekologis rendah, yang berpotensi dialokasikan untuk kegiatan budidaya terencana atau program restorasi ekosistem.

Garis pemisah kritis (*critical cut-off threshold*) dalam metodologi HCSA berada di antara strata **Semak Belukar (*Scrub*)** dan **Hutan Regenerasi Muda (*Young Regenerating Forest* - YRF)**. Seluruh area vegetasi yang memenuhi kriteria kelas YRF ke atas diklasifikasikan sebagai areal potensial HCS yang diprioritaskan untuk tahapan analisis petak konservasi (*patch analysis*).

---

## 2. Definisi Enam Kelas Strata Vegetasi HCS

Mengacu pada panduan resmi **HCSA Toolkit Modul 4 (*Forest and Vegetation Stratification*)**, lanskap Kabupaten Bogor distratifikasikan ke dalam 6 kelas vegetasi struktural ditambah 1 kelas non-vegetasi:

1. **High Density Forest (HDF) – Hutan Kerapatan Tinggi:**
   Hutan primer tak terganggu atau hutan sekunder tua dengan tutupan kanopi sangat rapat dan struktur tegakan berlapis. Memiliki dominasi pohon-pohon berdiameter besar ($DBH > 30\text{ cm}$) dan keberadaan pohon emergente yang menonjol di atas kanopi rata-rata.
2. **Medium Density Forest (MDF) – Hutan Kerapatan Sedang:**
   Hutan sekunder matang yang telah mengalami proses regenerasi lanjutan setelah gangguan masa lampau. Kanopi kontinu dan relatif tertutup, didominasi tegakan berdiameter sedang hingga besar.
3. **Low Density Forest (LDF) – Hutan Kerapatan Rendah:**
   Hutan sekunder muda atau hutan bekas tebangan intensif (*logged-over forest*). Tutupan kanopi mulai berongga atau terputus-putus, didominasi oleh jenis-jenis pohon pionir berdiameter kecil hingga sedang.
4. **Young Regenerating Forest (YRF) – Hutan Regenerasi Muda:**
   Tahap suksesi vegetasi berkayu pasca-penebangan atau perladangan berpindah. Didominasi tegakan pohon muda yang rapat ($DBH \approx 10 - 20\text{ cm}$) dengan potensi tinggi untuk pulih secara alami menjadi hutan sekunder matang.
5. **Scrub – Semak Belukar:**
   Areal yang didominasi oleh semak belukar terbuka, rumput tinggi, paku-pakuan, dan tanaman merambat. Keberadaan pohon berkayu sangat terbatas atau kerdil dengan tutupan kanopi renggang.
6. **Open Land – Lahan Terbuka:**
   Lahan dengan tutupan vegetasi berkayu yang sangat minim atau tidak ada, mencakup padang rumput pendek, lahan pertanian terbuka, area bekas tebang habis, dan lahan terbuka yang mengalami degradasi parah.
7. **Masking / Non-Vegetasi (Kelas 0):**
   Objek permukaan non-vegetasi, meliputi badan air permanen, permukiman, kawasan terbangun, infrastruktur, dan lahan terbuka batuan ekstrem yang dikeluarkan sebelum analisis stratifikasi vegetasi.

---

## 3. Matriks Ambang Batas Klasifikasi dan Penapisan Lahan

<div align="center">

<img src="../assets/stratification_rules_diagram.png" alt="Diagram Logika Stratifikasi Multikriteria HCS" width="800"/>

<p><em>Gambar 2: Skema Alur Pemutusan Stratifikasi Berdasarkan Prediksi AGBD dan Masking Tutupan Lahan</em></p>

</div>

Implementasi stratifikasi pada skrip [hcs_stratification.py](file:///e:/Mycourse/Magang%20Telkomsat/HCS/hcs_stratification.py) didasarkan pada integrasi estimasi Kepadatan Biomassa di Atas Permukaan (*Aboveground Biomass Density* - AGBD) hasil pemodelan multimodal dengan lapisan masker tutupan lahan Dynamic World.

### 3.1 Parameter Penapisan Non-Vegetasi
Piksel yang memenuhi setidaknya salah satu dari kriteria berikut secara otomatis dimasker ke dalam **Kelas 0 (Masking / Non-Vegetasi)**:
- Teridentifikasi sebagai kelas non-vegetasi pada peta tutupan lahan Dynamic World, yaitu: Kelas 0 (*Water*), Kelas 6 (*Built*), Kelas 7 (*Bare*), atau Kelas 8 (*Snow and Ice*).
- Memiliki nilai biomassa non-positif ($\text{AGBD} \le 0\text{ Mg/ha}$).

### 3.2 Matriks Ambang Batas Biomassa AGBD
Untuk seluruh piksel vegetasi yang valid, klasifikasi dilakukan menggunakan ambang batas numerik `AGBD_THRESHOLDS = [60.0, 75.0, 90.0, 110.0, 130.0]` melalui fungsi `np.digitize()`:

| Kode Kelas | Strata HCS | Rentang AGBD ($\text{Mg/ha}$) | Estimasi Stok Karbon ACD ($\text{Mg C/ha}$)* | Warna Representasi Peta (RGBA) | Status Konservasi HCSA |
|:---:|:---|:---:|:---:|:---:|:---:|
| **0** | **Masking / Non-Vegetasi** | - | - | Abu-abu (`#B0BEC5`) | Dikecualikan |
| **1** | **Open Land** | $< 60,0$ | $< 28,2$ | Kuning Pucat (`#FFF59D`) | **Bukan HCS** |
| **2** | **Scrub (Semak Belukar)** | $60,0 \le \text{AGBD} < 75,0$ | $28,2 - 35,3$ | Kuning Amber (`#FBC02D`) | **Bukan HCS** |
| **3** | **Young Regenerating Forest (YRF)** | $75,0 \le \text{AGBD} < 90,0$ | $35,3 - 42,3$ | Hijau Muda (`#A5D6A7`) | **Potensial HCS** |
| **4** | **Low Density Forest (LDF)** | $90,0 \le \text{AGBD} < 110,0$ | $42,3 - 51,7$ | Hijau Sedang (`#4CAF50`) | **Potensial HCS** |
| **5** | **Medium Density Forest (MDF)** | $110,0 \le \text{AGBD} < 130,0$ | $51,7 - 61,1$ | Hijau Rimba (`#2E7D32`) | **Potensial HCS** |
| **6** | **High Density Forest (HDF)** | $\ge 130,0$ | $\ge 61,1$ | Hijau Gelap (`#1B5E20`) | **Potensial HCS** |

*\*Catatan: Estimasi simpanan karbon di atas permukaan (Aboveground Carbon Density - ACD) dikonversi menggunakan faktor fraksi karbon standar IPCC Tier-1: $\text{ACD} = \text{AGBD} \times 0,47$.*

---

## 4. Alur Pemrosesan Pasca-Klasifikasi dan Protokol *Downgrading* MMU

Stratifikasi piksel murni sering kali menghasilkan derau bintik spasial (*salt-and-pepper noise*) berupa petak-petak terisolasi kecil yang secara ekologis dan operasional kehutanan tidak layak dipertahankan sebagai unit tegakan hutan mandiri. Oleh sebab itu, diimplementasikan prosedur penyaringan Satuan Pemetaan Terkecil (*Minimum Mapping Unit* - MMU) sesuai kaidah standar HCSA.

```
[Raster Prediksi AGBD (30 m)] + [Raster Tutupan Lahan Dynamic World (30 m)]
                                     │
                                     ▼
                   Penyelarasan Spasial & Reproyeksi Raster
                                     │
                                     ▼
                     Penapisan Non-Vegetasi (Masker Kelas 0)
                                     │
                                     ▼
                 Klasifikasi Ambang Batas AGBD (Kelas 1 s/d 6)
                                     │
                                     ▼
             Ekstraksi Masker Biner Potensial HCS (Kelas 3, 4, 5, 6)
                                     │
                                     ▼
            Pelabelan Komponen Terhubung 8-Arah (8-Connectivity)
                                     │
                                     ▼
           Penyaringan Ukuran MMU 0,5 Hektare (Ambang Batas 56 Piksel)
                                     │
                                     ▼
               Morfologi Spasial Citra (Kernel Penstruktur 3×3):
                     ├── Binary Closing (Penutupan celah mikro kanopi)
                     └── Binary Opening (Pembersihan derau tepi)
                                     │
                                     ▼
        Protokol Penurunan Strata (Downgrading) Sub-MMU:
        Piksel HCS (≥ Kelas 3) dengan Luas < 56 Piksel → Diturunkan ke Kelas 2 (Scrub)
                                     │
                                     ▼
                 Penyimpanan Raster Final GeoTIFF Berwarna
                                     │
                                     ▼
          Ekstraksi Rekapitulasi Statistik CSV & Dashboard Time Series
```

### 4.1 Formulasi Perhitungan Satuan Pemetaan Terkecil (MMU 0,5 Hektare)
HCSA Toolkit menetapkan bahwa petak vegetasi hutan yang dapat diakui memiliki batas luas minimal **0,5 hektare**:
- Pada sistem kisi piksel beresolusi $30\text{ m} \times 30\text{ m}$ (luas per piksel = $900\text{ m}^2 = 0,09\text{ ha}$):
  $$\text{Jumlah Piksel MMU} = \left\lceil \frac{0,5\text{ ha} \times 10.000\text{ m}^2/\text{ha}}{900\text{ m}^2} \right\rceil = \lceil 55,56 \rceil = 56\text{ piksel}$$

### 4.2 Prosedur Morfologi Spasial dan Penurunan Strata (*Downgrading*)
Berbeda dengan penghapusan piksel (*pixel deletion*) konvensional yang dapat menciptakan lubang kosong tanpa data, modul `filter_mmu_and_downgrade()` menjalankan aturan konservatif HCSA:
1. **Pelabelan Komponen (*Connected Component Labeling*):** Seluruh piksel potensial HCS (kelas 3 s/d 6) dikelompokkan menggunakan konektivitas 8-arah (*8-connectivity*).
2. **Penyaringan Ukuran Petak:** Petak-petak terhubung yang memiliki ukuran di bawah 56 piksel disaring.
3. **Penyempurnaan Struktur Morfologis:** Diterapkan operasi *Binary Closing* (1 iterasi) untuk menjembatani celah sempit di dalam tegakan, diikuti *Binary Opening* (1 iterasi) dengan elemen penstruktur $3 \times 3$ untuk menstabilkan batas petak.
4. **Penurunan Strata ke Kelas Semak (*Downgrading to Scrub*):** Seluruh piksel yang awalnya terklasifikasi sebagai potensial HCS namun gagal memenuhi ambang batas keutuhan spasial MMU (fragmen $< 0,5\text{ ha}$) diturunkan kelasnya menjadi **Kelas 2 (Scrub)**:
   $$\text{Final\_HCS}[\text{HCS} \ge 3 \land \neg \text{Sieved}] = 2$$
   Hal ini mencerminkan kondisi lapangan nyata di mana tegakan pohon berkayu yang terlalu kecil dan terfragmentasi secara ekologis berperilaku setara dengan semak belukar terbuka karena terdegradasi oleh efek tepi.

---

## 5. Pemrosesan Runtun Waktu (*Time Series*) dan Visualisasi Analitis

Skrip [hcs_stratification.py](file:///e:/Mycourse/Magang%20Telkomsat/HCS/hcs_stratification.py) dirancang untuk memproses data runtun waktu multithun (*multi-year trajectory*) secara otomatis, dengan struktur keluaran sebagai berikut:

### 5.1 Format Keluaran Data Spasial dan Tabel
1. **Raster GeoTIFF Diskret:** Disimpan pada `output/stratification/HCS_Stratification_{Tahun}_Final.tif` dengan metadata *colormap* RGBA resmi HCSA yang tertanam langsung pada header berkas.
2. **Tabel Statistik Agregat:** Disimpan pada `output/stratification/HCS_TimeSeries_Statistics.csv`, menyajikan jumlah piksel dan luas wilayah (hektare) untuk setiap kelas strata di setiap tahun analisis.

### 5.2 Dashboard Analitis Multipanel
Visualisasi dinamika tutupan HCS disintesis ke dalam dashboard 4-panel beresolusi tinggi (300 DPI) pada berkas `output/stratification/HCS_TimeSeries_Dashboard.png`:
- **Panel 1 (Kiri Atas - *Stacked Area*):** Menampilkan dinamika absolut luas masing-masing dari 7 kelas stratifikasi per tahun.
- **Panel 2 (Kanan Atas - *Dual Y-Axis Trend*):** Membandingkan tren perubahan kawasan Potensial HCS (kelas 3–6) terhadap kawasan Non-HCS (kelas 1–2) dan area *Masked/Non-Vegetasi* (kelas 0).
- **Panel 3 (Kiri Bawah - *Normalized 100% Stacked Bar*):** Menggambarkan proporsi komposisi relatif setiap strata terhadap total lanskap wilayah per tahun.
- **Panel 4 (Kanan Bawah - *Waterfall Bar Chart*):** Mengkuantifikasi perubahan bersih tahunan (*Year-over-Year Delta*) dari luas total kawasan potensial HCS, dengan pembedaan visual tegas antara laju penambahan (*gain*) dan penyusutan (*loss*).

---

## 6. Daftar Pustaka

- **[1]** HCS Approach Steering Group, "HCSA Toolkit v2.0, Module 4: Forest and vegetation stratification," High Carbon Stock Approach, 2017.
- **[2]** HCS Approach Steering Group, "HCSA Toolkit v2.0, Module 1: Introduction," High Carbon Stock Approach, 2017.
- **[3]** IPCC, "2019 Refinement to the 2006 IPCC Guidelines for National Greenhouse Gas Inventories: Volume 4 (AFOLU)," Intergovernmental Panel on Climate Change, 2019.
- **[4]** G. Rosoman et al., "The High Carbon Stock Science Study: Independent Report by the Technical Committee," HCSA Technical Committee, 2017.
- **[5]** C. F. Brown et al., "Dynamic World, Near real-time global 10 m land use land cover mapping," *Scientific Data*, vol. 9, no. 1, p. 251, 2022.
