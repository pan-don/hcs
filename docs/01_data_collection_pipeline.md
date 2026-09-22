<div align="center">

# DOKUMENTASI PENGUMPULAN DATA DAN REKAYASA FITUR MULTIMODAL
### Integrasi Sensor Optik (Sentinel-2), SAR (Sentinel-1), Topografi (GLO-30), Tutupan Lahan (Dynamic World), dan Spaceborne LiDAR (GEDI L4A)
**Studi Kasus: Pemetaan HCS Kabupaten Bogor, Jawa Barat**

---

<img src="../assets/data_pipeline_flowchart.png" alt="[Placeholder] Diagram Alir Pipeline Akuisisi dan Fusi Multimodal" width="850"/>

<p><em>Gambar 1: Alur Pemrosesan Fusi Citra Satelit Multimodal dan Ekstraksi Sampel GEDI pada Google Earth Engine</em></p>

</div>

---

## 1. Gambaran Umum

Pipeline data collection ini dirancang untuk mengatasi tantangan karakteristik lanskap tropis di Kabupaten Bogor—seperti tingginya persistensi tutupan awan sepanjang tahun serta variasi kelerengan curam di kawasan hulu Gunung Salak dan Gunung Gede Pangrango. Keterbatasan sensor optik tunggal yang cepat mengalami kejenuhan spektral (*spectral saturation*) pada tutupan kanopi lebat (>150–200 Mg/ha) diatasi dengan menyinergikan data radar gelombang mikro (Sentinel-1 SAR C-band), metrik struktur kanopi LiDAR (GEDI L4A/L2A), topografi digital (Copernicus GLO-30 DEM), dan probabilitas tutupan lahan berbasis deep learning (Dynamic World).

Seluruh tahapan pra-pemrosesan citra, koreksi radiometrik, penyelarasan resolusi spasial (30 meter), komposit kuartalan, hingga ekstraksi sampel geospasial dieksekusi secara terdistribusi di cloud platform **Google Earth Engine (GEE)**.

---

## 2. Karakteristik dan Sumber Data Mentah

| No | Sensor / Misi Satelit | Produk Data | Domain / Tipe Sensor | Resolusi Asli | Penyedia / Katalog GEE |
|:--:|:---|:---|:---|:---:|:---|
| **1** | **GEDI (ISS)** | L4A Footprint AGBD & L2A RH Metrics | Spaceborne LiDAR Gelombang Penuh (1064 nm) | Titik sampel footprint 25 m | NASA ORNL DAAC / `LARSE/GEDI/GEDI04_A_002_MONTHLY` |
| **2** | **Sentinel-2 MSI** | Level-2A Surface Reflectance (Harmonized) | Multispektral Optik (VNIR, Red Edge, SWIR) | 10 m, 20 m | ESA / `COPERNICUS/S2_SR_HARMONIZED` |
| **3** | **Sentinel-1** | C-SAR Level-1 GRD (Interferometric Wide) | Radar Apertur Sintesis Gelombang Mikro C-band | 10 m (spacing) | ESA / `COPERNICUS/S1_GRD` |
| **4** | **Copernicus DEM** | GLO-30 Digital Elevation Model | Radar Interferometri X-band / Topografi | 30 m | ESA / `COPERNICUS/DEM/GLO30` |
| **5** | **Dynamic World** | V1 Near Real-Time Land Cover | Deep Learning Probabilistic Land Cover (10m) | 10 m | Google / WRI / `GOOGLE/DYNAMICWORLD/V1` |
| **6** | **Cloud Score Plus** | S2_HARMONIZED Cloud Score+ V1 | Masking Awan dan Bayangan Kualitas Tinggi | 10 m | Google / `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` |

---

## 3. Matriks Fitur Prediktor (38 Fitur)

Sebanyak 38 variabel prediktor diekstraksi untuk setiap piksel 30 m di Kabupaten Bogor guna menangkap aspek biokimiawi daun, geometri struktur vertikal pohon, kekasaran tajuk, elevasi mikro, dan komposisi tutupan lahan.

| No | Nama Fitur | Sumber Data | Resolusi | Fungsi Biofisik & Signifikansi dalam Prediksi |
|:--:|:---|:---|:---:|:---|
| 1–9 | `s2_b2`, `s2_b3`, `s2_b4`, `s2_b5`, `s2_b6`, `s2_b7`, `s2_b8`, `s2_b11`, `s2_b12` | Sentinel-2 MSI | 10–20 m | Reflektansi spektral dasar (Biru, Hijau, Merah, 3 Red Edge, NIR, 2 SWIR). Mengukur absorpsi klorofil, transisi kanopi, dan kadar air daun. |
| 10 | `ndvi` | Sentinel-2 | 10 m | *Normalized Difference Vegetation Index*: Mengukur kehijauan vegetasi pada biomassa rendah hingga sedang. |
| 11 | `evi` | Sentinel-2 | 10 m | *Enhanced Vegetation Index*: Mereduksi pengaruh reflektansi latar tanah dan aerosol atmosfer; menunda saturasi optik kanopi lebat. |
| 12 | `ndre` | Sentinel-2 | 20 m | *Normalized Difference Red Edge*: Sangat peka terhadap akumulasi klorofil dan biomassa tahap lanjut tanpa cepat jenuh. |
| 13 | `ireci` | Sentinel-2 | 20 m | *Inverted Red-Edge Chlorophyll Index* ($(\text{RE3} - \text{Red}) / (\text{RE1}/\text{RE2})$): Indikator ketebalan lapisan daun dan luas kanopi; fitur optik peringkat teratas. |
| 14 | `gao_ndwi` | Sentinel-2 | 20 m | *Gao Normalized Difference Water Index* ($(\text{NIR} - \text{SWIR1})/(\text{NIR} + \text{SWIR1})$): Mengukur kadar air kanopi cairan dan kelembapan tajuk. |
| 15–17 | `ireci_contrast`, `ireci_ent`, `ireci_corr` | Sentinel-2 GLCM | 20 m | Tekstur spasial *Gray-Level Co-occurrence Matrix* (ukuran kernel 5 piksel) pada pita IRECI. Menangkap heterogenitas struktural kanopi dan bukaan tajuk. |
| 18–20 | `swir_contrast`, `swir_ent`, `swir_corr` | Sentinel-2 GLCM | 20 m | Tekstur GLCM pada saluran SWIR1 (B11). Mengkuantifikasi bayangan antar-pohon dan variasi fraksi kayu tidak berfotosintesis. |
| 21–22 | `vv`, `vh` | Sentinel-1 SAR | 10 m | Koefisien hamburan balik radar dalam skala decibel (dB). Saluran silang-polarisasi VH sangat peka terhadap hamburan volume (*volume scattering*) ranting dan kanopi. |
| 23–25 | `vv_contrast`, `vv_ent`, `vv_corr` | Sentinel-1 GLCM | 10 m | Tekstur spasial GLCM polarisasi ko-polarisasi VV. Mengukur kekasaran permukaan tajuk hutan dan arsitektur tanah/tegakan. |
| 26–28 | `vh_contrast`, `vh_ent`, `vh_corr` | Sentinel-1 GLCM | 10 m | Tekstur spasial GLCM polarisasi silang VH. Membedakan gradasi kerapatan tutupan hutan primer dari hutan sekunder muda. |
| 29 | `dem` | GLO-30 | 30 m | Elevasi absolut (meter dpl). Mengontrol zonasi iklim mikro pegunungan dan komposisi floristik hutan tropis basah. |
| 30 | `slope` | GLO-30 | 30 m | Kemiringan lereng (derajat). Mempengaruhi retensi kelembapan tanah, erosi substrat, dan batasan operasional LiDAR. |
| 31 | `aspect` | GLO-30 | 30 m | Arah hadap lereng (derajat radian). Merefleksikan insolasi radiasi matahari dan rezim penguapan lokal. |
| 32–39 | `water`, `trees`, `grass`, `flooded_veg`, `crops`, `shrub_scrub`, `built`, `bareland` | Dynamic World | 10 m | Probabilitas keanggotaan piksel untuk 8 kelas tutupan lahan. Memberikan batas probabilitas kontinu terhadap tipe ekosistem non-hutan. |

---

## 4. Alur Kerja Pengumpulan dan Pra-Pemrosesan Citra

<div align="center">

<img src="../assets/data_fusion_diagram.png" alt="[Placeholder] Skema Fusi Data Sentinel-1, Sentinel-2, dan GEDI" width="800"/>

<p><em>Gambar 2: Skema Koreksi Radiometrik SAR dan Masking Awan Multispektral</em></p>

</div>

### 4.1 Pemulihan Batas Geometri & Indeks Wilayah
- Rekonstruksi geometri titik sampel dari atribut tabular (`longitude`, `latitude`) pada Google Earth Engine.
- Pembentukan batas kawasan (*overall bounding box*) dari seluruh titik target untuk mengoptimasi query spatial katalog citra satelit secara terindeks.

### 4.2 Pra-Pemrosesan Sentinel-2 Multispektral
- **Filtrasi Tutupan Awan:** Memilih citra dengan persentase awan di bawah 70% (`CLOUDY_PIXEL_PERCENTAGE < 70`).
- **Masking Kualitas Piksel:** Menggunakan `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` dengan ambang `cs >= 0.60` untuk menyaring awan tipis, awan tebal, dan bayangan awan secara ketat.
- **Harmonisasi Reflektansi:** Skalar reflektansi dikalikan dengan faktor $0.0001$.
- **Perhitungan Indeks Spektral:** NDVI, EVI, NDRE, IRECI, dan Gao-NDWI dihitung pada setiap scene.

### 4.3 Pra-Pemrosesan Sentinel-1 SAR C-Band
- **Filtrasi Metadata:** Menggunakan mode instrumen *Interferometric Wide* (IW), polarisasi ganda (VV + VH), dan membatasi pada lintasan orbit **`DESCENDING`** guna menyeragamkan geometri penembakan sudut datang (*look angle*) serta memotong separuh volume tumpukan data.
- **Radiometric Terrain Flattening (Mullissa et al., 2021):** Mengoreksi variasi geometri lereng topografi menggunakan model SRTM/GLO-30 DEM. Menghitung sudut orientasi lokal (*Local Incidence Angle* - LIA) terhadap normal lereng permukaan untuk menghasilkan koefisien hamburan balik bebas distorsi lereng ($\gamma^0$).
- **Optimasi Konversi Skala Linier:** Menghindari konversi bolak-balik berulang antara Decibel (dB) dan Power Linier. Komposit multi-temporal dihitung pada domain daya linier:
  $$\text{Power}_{\text{lin}} = 10^{(\gamma^0_{\text{dB}} / 10)}$$
- **Speckle Filtering Multi-Temporal:** Reduksi derau *speckle* dilakukan melalui agregasi temporal median kuartalan, diikuti filter konvolusi spasial boxcar $3 \times 3$ yang dieksekusi **hanya 1 kali** pada citra komposit kuartalan.

### 4.4 Integrasi Topografi dan Dynamic World
- Ekstraksi kemiringan lereng (*slope*) dan arah lereng (*aspect*) menggunakan algoritma Horn dari Copernicus GLO-30 DEM.
- Agregasi probabilitas 8 kelas Dynamic World yang telah difilter bebas awan ke dalam rentang waktu observasi.

---

## 5. Strategi Penapisan Kualitas GEDI L4A dan Sampling Geospasial

<div align="center">

<img src="../assets/gedi_filtering_hexgrid.png" alt="[Placeholder] Ilustrasi Penapisan GEDI dan Partisi Grid Heksagonal" width="850"/>

<p><em>Gambar 3: Penapisan Footprint GEDI L4A dan Stratifikasi Partisi Heksagonal 5 km</em></p>

</div>

Untuk menjamin kualitas label target dan mencegah kesalahan propagasi ke model pembelajaran mesin, titik-titik sampel GEDI L4A melewati protokol penapisan berlapis:

1. **Penapisan Integritas Laser:**
   - `quality_flag == 1`: Menjamin keberhasilan algoritma penjejakan elevasi tanah dan profil vertikal.
   - `degrade_flag == 0`: Memastikan tidak ada degradasi kualitas transmisi akibat orientasi satelit ISS atau getaran wahana.
2. **Penyaringan Waktu Akuisisi (Solar Elevation):**
   - Hanya mempertahankan data yang diambil pada kondisi malam hari (`solar_elevation < 0` derajat). Hal ini meminimalkan derau latar belakang radiasi matahari (*solar background noise*) dan meningkatkan *Signal-to-Noise Ratio* (SNR) waveform.
3. **Penyaringan Lereng Ekstrem:**
   - Menolak titik observasi dengan kemiringan lereng $\text{slope} > 35^\circ$. Pada lereng yang sangat curam, footprint laser selebar 25 m mengalami pelebaran waveform semu (*waveform broadening*) yang menghasilkan estimasi biomassa over-estimasi.
4. **Pembangkitan Hexagonal Spatial Grid:**
   - Membangkitkan kisi-kisi heksagonal dengan diameter 5.000 meter di atas wilayah Kabupaten Bogor (`create_hexgrid.py`).
   - Setiap titik GEDI diasosiasikan dengan atribut pengenal blok spasial (`hex_id`). Skema ini digunakan sebagai dasar partisi data training-testing bebas autokorelasi spasial.

---

## 6. Daftar Pustaka

- **[1]** L. Duncanson et al., "Aboveground biomass density models for NASA's Global Ecosystem Dynamics Investigation (GEDI) lidar mission," *Remote Sensing of Environment*, vol. 270, p. 112845, 2022.
- **[2]** A. Mullissa et al., "Sentinel-1 SAR Backscatter Analysis Ready Data Preparation in Google Earth Engine," *Remote Sensing*, vol. 13, no. 10, p. 1954, 2021.
- **[3]** C. F. Brown et al., "Dynamic World, Near real-time global 10 m land use land cover mapping," *Scientific Data*, vol. 9, no. 1, p. 251, 2022.
- **[4]** R. Dubayah et al., "The Global Ecosystem Dynamics Investigation: High-resolution laser ranging of the Earth's forests and topography," *Science of Remote Sensing*, vol. 1, p. 100002, 2020.
- **[5]** N. Lang et al., "A high-resolution canopy height model of the Earth," *Nature Ecology & Evolution*, vol. 7, pp. 1778–1789, 2023.
