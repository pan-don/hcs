<div align="center">

# PANDUAN METODOLOGI PENGUMPULAN DATA DAN REKAYASA FITUR MULTIMODAL
### Integrasi Sensor Optik (Sentinel-2 MSI), Radar Apertur Sintesis (Sentinel-1 SAR C-Band), Model Elevasi Digital (Copernicus GLO-30 DEM), Tutupan Lahan Probabilistik (Dynamic World), dan Spaceborne LiDAR (GEDI L4A/L2A)
**Studi Kasus: Pemodelan Biomassa dan Stratifikasi HCS Kabupaten Bogor, Jawa Barat**

---

<img src="../assets/data_pipeline_flowchart.png" alt="Diagram Alir Pipeline Akuisisi dan Fusi Multimodal" width="850"/>

<p><em>Gambar 1: Alur Kerja Fusi Citra Satelit Multimodal dan Ekstraksi Sampel GEDI pada Google Earth Engine</em></p>

</div>

---

## 1. Pendahuluan dan Latar Belakang

Pemetaan stok karbon di atas permukaan (*Aboveground Biomass Density* - AGBD) dan tinggi kanopi (*Canopy Height*) pada lanskap tropis menghadapi tantangan biofisik yang kompleks. Kabupaten Bogor memiliki topografi heterogen—mulai dari dataran aluvial di bagian utara hingga kawasan pegunungan curam di lereng Gunung Salak dan Gunung Gede Pangrango di bagian selatan—serta persistensi tutupan awan yang sangat tinggi sepanjang tahun.

Pendekatan berbasis sensor tunggal memiliki kelemahan inheren:
1. **Sensor Optik Pasif:** Mengalami kejenuhan spektral (*spectral saturation*) pada tutupan tajuk rapat dan biomassa tinggi (>150–200 Mg/ha), serta sangat rentan terhadap kontaminasi awan dan bayangan awan.
2. **Sensor Radar Apertur Sintesis (SAR):** Memiliki kemampuan menembus awan dan peka terhadap hamburan volume kanopi (*volume scattering*), namun terdistorsi oleh efek geometri lereng (*layover*, *foreshortening*, dan *shadowing*).
3. **Sensor LiDAR Antariksa (GEDI):** Menyediakan estimasi struktur vertikal dan biomassa berkepresisian tinggi, tetapi distribusinya bersifat diskret (*footprint sampling* berjarak) dan tidak menghasilkan citra spasial kontinu.

Untuk mengatasi limitasi tersebut, dirancang metodologi fusi data multimodal terdistribusi berbasis **Google Earth Engine (GEE)**. Pipeline ini mengintegrasikan data *spaceborne* LiDAR GEDI (L4A dan L2A) sebagai target label referensi, citra optik multispektral Sentinel-2 MSI, citra radar Sentinel-1 SAR C-band, data elevasi topografi Copernicus GLO-30 DEM, dan produk tutupan lahan Dynamic World. Seluruh data diselaraskan ke dalam resolusi spasial standar 30 meter pada sistem proyeksi Universal Transverse Mercator (UTM) Zona 48S (EPSG:32648).

---

## 2. Spesifikasi dan Sumber Data Akuisisi

Data mentah yang digunakan bersumber dari katalog data geospasial terbuka yang diakses melalui antarmuka komputasi awan Google Earth Engine:

| No | Misi / Sensor Satelit | Produk Data | Domain Spektral / Sensor | Resolusi Spasial Asli | Penyedia / Katalog Google Earth Engine |
|:--:|:---|:---|:---|:---:|:---|
| **1** | **GEDI (ISS)** | L4A Footprint AGBD (v002) & L2A RH98 | Full-Waveform Spaceborne LiDAR (1.064 nm) | Footprint diameter ~25 m | NASA ORNL DAAC / `LARSE/GEDI/GEDI04_A_002_MONTHLY` & `LARSE/GEDI/GEDI02_A_002_MONTHLY` |
| **2** | **Sentinel-2 MSI** | Level-2A Surface Reflectance (Harmonized) | Multispektral Optik (VNIR, Red Edge, SWIR) | 10 m, 20 m | ESA Copernicus / `COPERNICUS/S2_SR_HARMONIZED` |
| **3** | **Cloud Score Plus** | S2_HARMONIZED Cloud Score+ (v1) | Model Penilaian Kualitas Piksel dan Awan | 10 m | Google / `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` |
| **4** | **Sentinel-1** | C-SAR Level-1 GRD (Interferometric Wide) | Radar Gelombang Mikro C-Band (5,405 GHz) | 10 m (pixel spacing) | ESA Copernicus / `COPERNICUS/S1_GRD` |
| **5** | **Copernicus DEM** | GLO-30 Global Digital Elevation Model | Radar Interferometri X-Band (Topografi) | 30 m | ESA Copernicus / `COPERNICUS/DEM/GLO30` |
| **6** | **Dynamic World** | V1 Near Real-Time Land Cover | Deep Learning Probabilistic Land Cover | 10 m | Google & WRI / `GOOGLE/DYNAMICWORLD/V1` |

---

## 3. Matriks Fitur Prediktor Model (34 Fitur)

Berdasarkan arsitektur ekstraksi fitur pada repositori (`src/inference_agbd.js`, `src/inference_canopy_height.js`, dan `src/modelling_agbd.js`), sebanyak **34 variabel prediktor kontinu** diekstraksi pada resolusi spasial 30 meter untuk menyusun dataset pelatihan dan inferensi spasial:

| No | Kategori Fitur | Variabel Prediktor | Sumber Sensor | Resolusi Spasial | Signifikansi Biofisik dan Peran dalam Prediksi |
|:--:|:---|:---|:---|:---:|:---|
| **1–9** | **Pita Spektral Dasar** | `b2`, `b3`, `b4`, `b5`, `b6`, `b7`, `b8`, `b11`, `b12` | Sentinel-2 MSI | 10–20 m | Reflektansi permukaan dasar (Biru, Hijau, Merah, 3 Red Edge, NIR, SWIR-1, dan SWIR-2). Menangkap spektrum penyerapan klorofil, transisi kanopi berkayu, dan kadar air dedaunan. |
| **10** | **Indeks Vegetasi** | `ndvi` | Sentinel-2 | 10 m | *Normalized Difference Vegetation Index* ($(\text{NIR} - \text{Red}) / (\text{NIR} + \text{Red})$): Mengukur kehijauan kanopi dan biomassa pada tingkat kerapatan rendah hingga menengah. |
| **11** | **Indeks Vegetasi** | `gndvi` | Sentinel-2 | 10 m | *Green Normalized Difference Vegetation Index* ($(\text{NIR} - \text{Green}) / (\text{NIR} + \text{Green})$): Lebih sensitif terhadap konsentrasi klorofil pada fase kanopi lebat dibandingkan NDVI. |
| **12** | **Indeks Vegetasi** | `evi` | Sentinel-2 | 10 m | *Enhanced Vegetation Index*: Mereduksi pengaruh reflektansi latar belakang tanah dan hamburan aerosol atmosferik; menunda saturasi pada kanopi berkerapatan tinggi. |
| **13** | **Indeks Red Edge** | `ireci` | Sentinel-2 | 20 m | *Inverted Red-Edge Chlorophyll Index* ($(\text{RE3} - \text{Red}) / (\text{RE1} / \text{RE2})$): Peka terhadap kandungan klorofil total dan indeks luas daun (*Leaf Area Index* - LAI). |
| **14** | **Indeks Rasio** | `rvi` | Sentinel-2 | 10 m | *Ratio Vegetation Index* ($\text{NIR} / \text{Red}$): Responsif terhadap kepadatan biomassa dan struktur tegakan berkayu. |
| **15** | **Indeks Kelembapan** | `gao_ndwi` | Sentinel-2 | 20 m | *Gao Normalized Difference Water Index* ($(\text{NIR} - \text{SWIR1}) / (\text{NIR} + \text{SWIR1})$): Mengukur kadar air cairan kanopi dan status turgiditas tajuk hutan. |
| **16–17** | **Hamburan Balik Radar** | `vv`, `vh` | Sentinel-1 SAR | 10 m | Koefisien hamburan balik terkoreksi lereng ($\gamma^0$) dalam skala desibel (dB). Polarisasi silang VH sangat responsif terhadap hamburan volume kanopi pohon. |
| **18–20** | **Tekstur Spasial SAR (VV)** | `vv_cont`, `vv_ent`, `vv_corr` | Sentinel-1 SAR (GLCM 5×5) | 10 m | Tekstur *Gray-Level Co-occurrence Matrix* (kontras, entropi, korelasi) pada kanal VV. Mengukur kekasaran permukaan tajuk dan struktur tegakan atas. |
| **21–23** | **Tekstur Spasial SAR (VH)** | `vh_cont`, `vh_ent`, `vh_corr` | Sentinel-1 SAR (GLCM 5×5) | 10 m | Tekstur GLCM pada kanal VH. Membedakan heterogenitas internal kanopi hutan primer dari formasi hutan sekunder dan semak homogen. |
| **24** | **Topografi** | `dem` | Copernicus GLO-30 | 30 m | Elevasi permukaan absolut (meter di atas permukaan laut). Menentukan gradien iklim mikro pegunungan dan zonasi vegetasi tropis. |
| **25** | **Topografi** | `slope` | Copernicus GLO-30 | 30 m | Kemiringan lereng permukaan (derajat). Mempengaruhi retensi kelembapan tanah, ketebalan solum, dan potensi erosi lahan. |
| **26** | **Topografi** | `aspect` | Copernicus GLO-30 | 30 m | Arah hadap lereng (derajat radian). Merefleksikan insolasi penyinaran radiasi matahari harian dan dinamika evapotranspirasi lokal. |
| **27–34** | **Probabilitas Tutupan Lahan** | `water`, `trees`, `grass`, `flooded_veg`, `crops`, `shrub_scrub`, `built`, `bareland` | Dynamic World V1 | 10 m | Probabilitas keanggotaan kontinu (0,0–1,0) untuk 8 kelas ekosistem. Memberikan batasan probabilitas numerik terhadap non-vegetasi dan tipe tutupan lahan terbuka. |

---

## 4. Metodologi Pra-Pemrosesan Citra Satelit

<div align="center">

<img src="../assets/data_fusion_diagram.png" alt="Skema Fusi Data Sentinel-1, Sentinel-2, dan GEDI" width="800"/>

<p><em>Gambar 2: Skema Koreksi Radiometrik SAR C-Band dan Masking Awan Multispektral</em></p>

</div>

### 4.1 Pemulihan Batas Geometri dan Wilayah Kajian
1. **Rekonstruksi Koordinat:** Geometri titik sampel direkonstruksi dari atribut numerik bujur (*longitude*) dan lintang (*latitude*) menggunakan fungsi `ee.Geometry.Point()`.
2. **Pembatasan Batas Spasial (*Spatial Bounding Box*):** Menggabungkan seluruh geometri titik target ke dalam poligon pembatas tunggal (*overall bounds*) guna mengoptimasi komputasi kueri katalog citra di server Google Earth Engine secara terindeks.

### 4.2 Pra-Pemrosesan Citra Optik Sentinel-2 MSI
1. **Penapisan Awal Tutupan Awan:** Memilih scene citra dengan persentase tutupan awan keseluruhan di bawah 70% (`CLOUDY_PIXEL_PERCENTAGE < 70`).
2. **Penapisan Piksel Berkualitas Tinggi (Cloud Score Plus):** Mengintegrasikan koleksi `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`. Hanya piksel dengan skor bebas awan dan bebas bayangan awan $\ge 0,60$ (`cs >= 0.60`) yang dipertahankan.
3. **Harmonisasi Skala Reflektansi:** Nilai reflektansi digital dikalikan faktor skala $0,0001$ untuk mengembalikan rentang fisik reflektansi permukaan ($0,0 - 1,0$).
4. **Transformasi Indeks Spektral:** Menghitung 6 indeks biofisik (NDVI, GNDVI, EVI, IRECI, RVI, dan Gao-NDWI) secara serentak pada setiap scene citra.
5. **Komposisi Temporal Kuartalan:** Membentuk komposit median pada setiap kuartal observasi (*quarterly median composite*) untuk mengisi kekosongan akibat penapisan awan (*unmasking* dengan komposit tahunan/baseline). Citra diinterpolasi menggunakan teknik *bilinear resampling* pada resolusi 30 meter.

### 4.3 Pra-Pemrosesan Radar Sentinel-1 SAR C-Band
1. **Penapisan Mode Instrumen dan Orbit:** Menggunakan mode instrumen *Interferometric Wide* (IW) dengan polarisasi ganda (VV dan VH). Penapisan dibatasi khusus pada lintasan orbit **`DESCENDING`** guna menyeragamkan geometri penyinaran sudut datang (*incident look angle*) dan menghindari variasi temporal antar-orbit.
2. **Koreksi Efek Lereng Topografi (*Radiometric Terrain Flattening*):** Mengimplementasikan algoritma Mullissa et al. (2021) dengan memanfaatkan model elevasi digital SRTM/GLO-30 DEM. Sudut pandang satelit dikorelasikan dengan sudut kemiringan (*slope*) dan arah lereng (*aspect*) permukaan untuk menghitung *Local Incidence Angle* (LIA). Hasil koreksi ditransformasikan menjadi koefisien hamburan balik bebas distorsi lereng ($\gamma^0$).
3. **Optimasi Domain Daya Linier:** Mereduksi eror komputasi desibel dengan mengonversi nilai desibel ke daya linier (*linear power*) sebelum agregasi temporal:
   $$\text{Power}_{\text{lin}} = 10^{(\gamma^0_{\text{dB}} / 10)}$$
4. **Pereduksian Derau Bintik (*Speckle Filtering*):** Derau bintik diredam melalui reduksi agregasi median kuartalan pada domain linier, dilanjutkan dengan konvolusi spasial *boxcar* $3 \times 3$ yang dieksekusi **satu kali** sebelum dikembalikan ke skala logaritmik desibel (dB).
5. **Ekstraksi Tekstur Spasial GLCM:** Citra kanal VV dan VH diskalakan ke rentang 6-bit (0–63) tipe *byte*, kemudian diekstraksi tekstur *Gray-Level Co-occurrence Matrix* berukuran jendela $5 \times 5$ piksel untuk menghitung parameter kontras (*contrast*), entropi (*entropy*), dan korelasi (*correlation*).

### 4.4 Integrasi Data Topografi dan Dynamic World
1. **Variabel Medan Copernicus GLO-30 DEM:** Nilai ketinggian absolut (`dem`) diselaraskan ke proyeksi target EPSG:32648 resolusi 30 meter. Algoritma Horn (1981) diterapkan melalui `ee.Terrain.products()` untuk mengekstraksi nilai kemiringan lereng (`slope`) dalam derajat dan arah hadap lereng (`aspect`) dalam derajat radian.
2. **Komposisi Multitemporal Dynamic World:** Mengagregasi 8 pita probabilitas kontinu tutupan lahan Dynamic World melalui rata-rata kuartalan/tahunan (*temporal mean composite*) dengan interpolasi bilinear pada grid 30 meter.

---

## 5. Protokol Penapisan Kualitas GEDI dan Strategi Pengambilan Sampel

<div align="center">

<img src="../assets/gedi_filtering_hexgrid.png" alt="Ilustrasi Penapisan GEDI dan Partisi Grid Heksagonal" width="850"/>

<p><em>Gambar 3: Skema Penapisan Kualitas Footprint GEDI L4A/L2A dan Penyeimbangan Sampel Grid Heksagonal</em></p>

</div>

Untuk memastikan integritas data latih dan mencegah perambatan bias pada model pembelajaran mesin (*machine learning*), titik sampel footprint LiDAR GEDI disaring secara ketat melalui tahapan sistematis berikut (diimplementasikan pada `src/data_collection/gedi.js`):

### 5.1 Kriteria Penapisan Kualitas Sinyal Laser (Signal Quality Flags)
1. **Penapisan GEDI L4A (AGBD):**
   - `l4_quality_flag == 1`: Menjamin algoritma pemodelan biomassa GEDI L4A berjalan konvergen tanpa eror penjejakan permukaan tanah.
   - `degrade_flag == 0`: Memastikan tidak terjadi degradasi akurasi navigasi satelit ISS atau ketidakstabilan posisi sensor pada orbit.
   - `l2_quality_flag == 1`: Memastikan profil waveform kanopi vertikal dari produk L2A berstatus valid.
   - `sensitivity >= 0.90`: Memastikan sensitivitas penetrasi pulsa laser mampu menembus tajuk vegetasi hingga permukaan tanah dengan tingkat keyakinan minimal 90%.
   - `agbd > 0`: Mengeliminasi nilai biomassa kosong atau tidak terdefinisi.
2. **Penapisan GEDI L2A (RH98 - Tinggi Kanopi):**
   - `quality_flag == 1`: Menjamin akurasi deteksi puncak kanopi dan pantulan tanah.
   - `degrade_flag == 0`: Bebas dari gangguan orbit atau atenuasi atmosferik.
   - `sensitivity >= 0.90`: Tingkat sensitivitas penetrasi gelombang laser $\ge 90\%$.
   - `rh98 > 0`: Memastikan ketinggian relatif persentil ke-98 bernilai positif.

### 5.2 Penapisan Tutupan Lahan Vegetasi (Dynamic World Masking)
- Sampel GEDI disaring silang menggunakan peta tutupan lahan Dynamic World. Hanya titik sampel yang berada pada kelas vegetasi (`dw_label` antara kelas 1 hingga 5: *trees*, *grass*, *flooded_vegetation*, *crops*, dan *shrub_and_scrub*) yang dipertahankan.
- Piksel non-vegetasi (badan air, kawasan terbangun, lahan terbuka ekstrem, salju/es) dimasker secara otomatis untuk menghindari kontaminasi spektral pada dataset pemodelan vegetasi berkayu.

### 5.3 Penyeimbangan Spasial Menggunakan Kisi Heksagonal (Spatial Grid Balancing)
- Jalur orbit stasiun luar angkasa ISS menyebabkan penumpukan footprint GEDI yang sangat rapat di sepanjang lintasan sensor (*along-track clustering*), sementara area antar-lintasan (*across-track*) memiliki kerapatan sampel yang lebih renggang.
- Untuk mengeliminasi bias autokorelasi spasial dan *oversampling* lokal, seluruh wilayah Kabupaten Bogor dipartisi ke dalam kisi heksagonal berukuran 5.000 meter.
- Jumlah sampel acak per sel heksagonal dibatasi secara proporsional (`MAX_SAMPLES_PER_HEX = 100`, `RANDOM_SEED = 42`) menggunakan algoritma `limitSamplesPerGrid()`. Metode ini menjamin representasi spasial yang seragam di seluruh bentang alam Kabupaten Bogor.

---

## 6. Daftar Pustaka

- **[1]** L. Duncanson et al., "Aboveground biomass density models for NASA's Global Ecosystem Dynamics Investigation (GEDI) lidar mission," *Remote Sensing of Environment*, vol. 270, p. 112845, 2022.
- **[2]** A. Mullissa et al., "Sentinel-1 SAR Backscatter Analysis Ready Data Preparation in Google Earth Engine," *Remote Sensing*, vol. 13, no. 10, p. 1954, 2021.
- **[3]** C. F. Brown et al., "Dynamic World, Near real-time global 10 m land use land cover mapping," *Scientific Data*, vol. 9, no. 1, p. 251, 2022.
- **[4]** R. Dubayah et al., "The Global Ecosystem Dynamics Investigation: High-resolution laser ranging of the Earth's forests and topography," *Science of Remote Sensing*, vol. 1, p. 100002, 2020.
- **[5]** B. K. P. Horn, "Hill shading and the reflectance map," *Proceedings of the IEEE*, vol. 69, no. 1, pp. 14–47, 1981.
- **[6]** N. Lang et al., "A high-resolution canopy height model of the Earth," *Nature Ecology & Evolution*, vol. 7, pp. 1778–1789, 2023.
