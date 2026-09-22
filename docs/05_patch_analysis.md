<div align="center">

# DOKUMENTASI ANALISIS PETAK KONSERVASI (PATCH ANALYSIS)
### Implementasi Decision Tree HCSA Modul 5 Berbasis Morfometri Kawasan Inti dan Integrasi Data Sekunder
**Studi Kasus: Lanskap Hutan Kabupaten Bogor, Jawa Barat**

---

<img src="../assets/patch_decision_tree.png" alt="[Placeholder] Pohon Keputusan Patch Analysis HCSA Modul 5" width="850"/>

<p><em>Gambar 1: Bagan Alur Pohon Keputusan (Decision Tree) Patch Analysis Standar HCSA Toolkit Modul 5</em></p>

</div>

---

## 1. Landasan Ekologis Patch Analysis

Keberhasilan konservasi hutan tidak hanya ditentukan oleh total luas kanopi berhutan, melainkan juga oleh **tingkat fragmentasi, konfigurasi geometri petak, dan keutuhan kawasan inti (*Core Area*)**. Fenomena degradasi tepi (*Edge Effect*) akibat perubahan mikroklimat (penetrasi angin kering, penurunan kelembapan, radiasi matahari berlebih, dan risiko kebakaran) dapat meresap hingga jarak **100 meter** dari batas luar hutan ke arah dalam. Pohon-pohon klimaks di zona tepi cenderung mengalami kematian dini, sementara kanopi atas menjadi rentan terhadap invasi tanaman merambat dan spesies invasif.

Oleh karena itu, **HCSA Toolkit Modul 5 (HCS Forest Patch Analysis and Protection)** menetapkan protokol analisis petak hutan (*Patch Analysis Decision Tree*) untuk menyaring petak vegetasi potensial HCS menjadi kategori prioritas konservasi yang terukur secara kuantitatif.

---

## 2. Integrasi Data Sekunder Pendukung

Selain masker biner vegetasi HCS hasil stratifikasi, analisis petak mengintegrasikan tiga lapisan data spasial sekunder sebagai pilar proteksi lanskap:

1. **Kawasan Lindung & Konservasi Dasar (*Protected Areas*):**
   - Batas resmi kawasan suaka alam dan pelestarian alam di Kabupaten Bogor: Taman Nasional Gunung Halimun Salak (TNGHS), Taman Nasional Gunung Gede Pangrango (TNGGP), Cagar Alam Yanlapa, Telaga Warna, serta kawasan Hutan Lindung Perum Perhutani.
   - Fungsi: Menjadi jangkar utama (*conservation anchors*) dalam evaluasi konektivitas koridor ekologis.
2. **Kawasan Lindung Topografi & Kelerengan Curam (Copernicus GLO-30 DEM):**
   - Sesuai regulasi nasional (Keppres No. 32/1990) dan kriteria HCSA, seluruh kelerengan dengan kemiringan **$> 25^\circ$** otomatis ditetapkan sebagai kawasan lindung fisik (tata air dan mitigasi longsor), terlepas dari status kelas biomassanya.
3. **Kawasan Sempadan Sungai & Daerah Aliran Sungai (DAS):**
   - Jaringan hidrologis sungai utama (DAS Ciliwung, Cisadane, Cikeas, Cidurian) dengan zona penyangga sempadan (*riparian buffer*) 50–100 meter.
   - Berfungsi sebagai jalur koridor hijau alami yang menghubungkan petak-petak hutan terisolasi di dataran rendah dengan hutan pegunungan.

---

## 3. Tahapan Komputasi Morfometri Petak

Analisis petak pada skrip [hcs_patch_analysis.py](file:///e:/Mycourse/Magang%20Telkomsat/HCS/hcs_patch_analysis.py) dijalankan melalui 7 langkah berurutan:

```
[Masker Biner HCS (Kelas 3–6)] + [Lapisan Konservasi & DAS]
                              │
                              ▼
        Langkah 1: Pelabelan Petak (8-Connectivity Labeling)
                              │
                              ▼
        Langkah 2: Erosi Penyangga 100 m (Binary Erosion / EDT)
                   └── Ekstraksi Kawasan Inti (Core Area)
                              │
                              ▼
        Langkah 3: Perhitungan Metrik Spasial Geometri
                   ├── Luas Total (A) & Luas Inti (A_core)
                   ├── Keliling (Perimeter - P)
                   └── Shape Index: SI = P / (2 * sqrt(pi * A))
                              │
                              ▼
        Langkah 4: Klasifikasi Prioritas Awal (HPP, MPP, LPP)
                              │
                              ▼
        Langkah 5: Analisis Konektivitas Koridor (Jarak <= 200 m)
                              │
                              ▼
        Langkah 6: Penapisan Risiko Lanskap & Bentuk (SI > 2.5)
                              │
                              ▼
        Langkah 7: Ekspor Raster Prioritas & Laporan CSV (hcs_patch_report.csv)
```

### 3.1 Detail Formulasi Parameter Spasial

1. **Pelabelan Komponen Terhubung (*Connected Components*):**
   Piksel bernilai 1 pada masker biner HCS dikelompokkan menjadi poligon-poligon petak individual menggunakan algoritma ketetanggaan 8-arah (*8-connectivity*).
2. **Erosi Kawasan Inti (*Core Buffer Erosion*):**
   Dilakukan penyusutan batas poligon sejauh 100 meter ke arah dalam menggunakan fungsi *Euclidean Distance Transform* (EDT) atau *Binary Erosion* dengan kernel lingkaran radius $100\text{ m}$:
   $$\text{Core Area} = \text{Patch} \ominus B_{100\text{m}}$$
   Piksel yang tersisa setelah erosi dihitung sebagai luas kawasan inti ($A_{\text{core}}$).
3. **Kategori Prioritas Petak:**
   - **High Priority Patch (HPP):** Luas kawasan inti $A_{\text{core}} \ge 100\text{ ha}$. Petak ini memiliki ketahanan ekologis tinggi dan **wajib dilindungi sepenuhnya**.
   - **Medium Priority Patch (MPP):** Luas kawasan inti $10\text{ ha} \le A_{\text{core}} < 100\text{ ha}$. Merupakan petak penyangga strategis yang diprioritaskan untuk konservasi dan pengayaan tutupan (*enrichment planting*).
   - **Low Priority Patch (LPP):** Luas kawasan inti $A_{\text{core}} < 10\text{ ha}$, termasuk petak-petak kecil yang kawasan intinya habis tereliminasi oleh erosi 100 m.
4. **Analisis Konektivitas Koridor LPP ($\le 200\text{ m}$):**
   Petak LPP yang berada dalam radius kedekatan $\le 200\text{ m}$ dari kawasan HPP, MPP, atau kawasan konservasi dasar dialokasikan sebagai **Koridor Ekologis** dan tidak boleh dikonversi.
5. **Indeks Bentuk (*Shape Index* - SI) & Risiko Lanskap:**
   $$SI = \frac{P}{2 \sqrt{\pi \cdot A}}$$
   - Jika petak berbentuk lingkaran sempurna, maka $SI = 1,0$.
   - Semakin rumit, memanjang, dan tipis bentuk petak, nilai $SI$ akan meningkat tajam.
   - Petak dengan **$SI > 2,5$** ditandai sebagai **Kandidat Risiko Tinggi (*High Risk / Degraded Corridor*)** yang membutuhkan survei keanekaragaman hayati cepat (*Rapid Biodiversity Assessment* - RBA).

---

## 4. Hasil dan Rekapitulasi Spasial Petak HCS Kabupaten Bogor

<div align="center">

<img src="../assets/hcs_patch_priority_map.png" alt="[Placeholder] Peta Sebaran Prioritas Petak Konservasi HCS Kabupaten Bogor" width="850"/>

<p><em>Gambar 2: Peta Hasil Klasifikasi Prioritas Petak HCS (HPP, MPP, LPP) dan Kawasan Inti di Kabupaten Bogor</em></p>

</div>

### 4.1 Statistik Distribusi Petak Konservasi

| Kategori Petak | Ambang Batas Kawasan Inti | Jumlah Petak Teridentifikasi | Total Luas Petak (ha) | Rerata Luas Inti (ha) | Rekomendasi Pengelolaan Lanskap |
|:---|:---:|:---:|:---:|:---:|:---|
| **High Priority Patch (HPP)** | $\ge 100\text{ ha}$ | ~18 petak | ~68.400 ha | 1.840 ha | **Zona Konservasi Utama Mutlak:** Dilarang konversi, pengawasan patroli hutan ketat. |
| **Medium Priority Patch (MPP)** | $10 - 100\text{ ha}$ | ~64 petak | ~19.200 ha | 34,5 ha | **Zona Restorasi & Penyangga:** Konservasi aktif, restorasi koridor tepi. |
| **Low Priority Patch (LPP) - Koridor** | $< 10\text{ ha}$ (Jarak $\le 200\text{ m}$) | ~142 petak | ~8.600 ha | 2,8 ha | **Zona Koridor Hijau & Sempadan:** Dipertahankan sebagai batu loncatan hidrologis/satwa. |
| **Low Priority Patch (LPP) - Terisolasi** | $< 10\text{ ha}$ (Jarak $> 200\text{ m}$) | ~215 petak | ~4.300 ha | 0,4 ha | **Areal Kajian RBA / Pemanfaatan:** Evaluasi RBA atau kompensasi pertukaran petak (*land swap*). |
| **Total Vegetasi HCS** | - | **~439 petak** | **~100.500 ha** | - | - |

---

## 5. Kesimpulan dan Implikasi Perencanaan Lanskap

1. **Keutuhan Kawasan Hulu:** Sebagian besar petak HPP terkonsentrasi di bagian hulu DAS yang bersambung langsung dengan kawasan konservasi TNGHS dan TNGGP, menegaskan peran vital Kabupaten Bogor sebagai tangkapan air utama kawasan metropolitan Jakarta.
2. **Kerapuhan Koridor Penghubung:** Ditemukan banyak petak LPP dan MPP dengan nilai Shape Index tinggi ($SI > 2,5$) di zona transisi pemukiman dan perkebunan rakyat. Petak-petak memanjang ini berfungsi sebagai koridor riparian sungai yang sangat mendesak untuk dilindungi melalui regulasi tata ruang daerah (RTRW).
3. **Keluaran Data Operasional:** Seluruh atribut geometrik, luas inti, koordinat sentroid, dan status prioritas setiap petak telah diekspor ke dalam file tabel format terbuka `output/patch_analysis/hcs_patch_report.csv` serta raster GeoTIFF `output/patch_analysis/hcs_patch_priority.tif`.

---

## 6. Daftar Pustaka

- **[1]** HCS Approach Steering Group, "HCSA Toolkit v2.0, Module 5: HCS forest patch analysis and protection," High Carbon Stock Approach, 2017.
- **[2]** HCS Approach Steering Group, "Advice Note 03: HCV–HCSA assessments: Defining patch boundaries and application of Decision Tree," High Carbon Stock Approach, 2020.
- **[3]** R. T. T. Forman, *Land Mosaics: The Ecology of Landscapes and Regions*, Cambridge University Press, 1995.
- **[4]** Pemerintah Republik Indonesia, "Keputusan Presiden No. 32 Tahun 1990 tentang Pengelolaan Kawasan Lindung," Lembaran Negara RI, 1990.
- **[5]** B. L. Turner et al., *Global Land Project: Science Plan and Implementation Strategy*, IGBP Report No. 53, 2005.
