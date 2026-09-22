<div align="center">

# DOKUMENTASI PEMODELAN CANOPY HEIGHT (RH98)
### Estimasi Struktur Vertikal Tinggi Tajuk Kanopi Hutan Menggunakan Random Forest Regressor
**Studi Kasus: Kabupaten Bogor, Jawa Barat**

---

<img src="../assets/rf_canopy_height_workflow.png" alt="[Placeholder] Alur Pemodelan Regresi Canopy Height RH98" width="850"/>

<p><em>Gambar 1: Diagram Alur Pemodelan Regresi Ketinggian Tajuk Kanopi Hutan Berbasis Metrik GEDI RH98</em></p>

</div>

---

## 1. Gambaran Umum Pemodelan

Tinggi kanopi pohon (*Canopy Height*) merupakan indikator biofisik utama yang mencerminkan fase suksesi hutan, usia tegakan, potensi stratifikasi tajuk, dan kapasitas simpanan karbon. Dalam arsitektur pemetaan High Carbon Stock (HCSA Modul 4), tinggi kanopi digunakan berdampingan dengan biomassa untuk memverifikasi struktur fisik hutan secara objektif (misalnya membedakan semak belukar kerdil dari hutan regenerasi muda).

Dalam model ini, variabel target yang dipelajari adalah **`rh98` (Relative Height 98%)** dalam satuan meter dari produk **GEDI Level 2A (Elevation and Height Metrics)**. Metrik RH98 mengukur jarak vertikal dari pantulan sinyal permukaan tanah (*ground return*) hingga ke titik di mana 98% akumulasi energi gelombang pantulan LiDAR tercapai. Penggunaan RH98 alih-alih RH100 (ketinggian absolut 100%) merupakan standar baku penginderaan jauh kehutanan untuk menghindari bias derau pantulan atmosfer dan puncak cabang tunggal yang terisolasi.

---

## 2. Arsitektur Pemodelan dan Konsistensi Desain

Untuk menjamin integritas perbandingan struktural antara biomassa dan tinggi kanopi, konfigurasi arsitektur pemodelan dibuat **sepenuhnya identik** dengan pemodelan AGBD pada [docs/02_agbd_modeling.md](02_agbd_modeling.md):

1. **Set Fitur Prediktor:** 38 fitur multimodal yang sama (Sentinel-2, Sentinel-1 SAR, Copernicus GLO-30 DEM, Dynamic World).
2. **Skema Partisi Validasi:** *Spatial Block Cross-Validation* berbasis kisi heksagonal 5.000 meter (`hex_id`) dengan proporsi **80% Training : 20% Testing** (`SPLIT_SEED = 42`).
3. **Spesifikasi Model:** Random Forest Regressor pada Google Earth Engine (`ee.Classifier.smileRandomForest`):
   - `numberOfTrees`: 350
   - `variablesPerSplit`: null (default $\sqrt{p}$)
   - `minLeafPopulation`: 5
   - `bagFraction`: 0.632
   - `seed`: 42
4. **Perbedaan Tunggal:** Variabel target diganti dari `agbd` ($\text{Mg/ha}$) menjadi `rh98` ($\text{meter}$).

---

## 3. Metrik Evaluasi Kinerja Model

Evaluasi model dihitung menggunakan metrik statistik standar:

- **Koefisien Determinasi ($R^2$):** Mengukur proporsi varians tinggi kanopi aktual yang mampu dijelaskan oleh kovariat penginderaan jauh.
- **Root Mean Squared Error (RMSE):** Mengukur magnitudo kesalahan kuadrat rata-rata dalam satuan meter ($\text{m}$).
- **Mean Absolute Error (MAE):** Mengukur deviasi absolut rata-rata dalam satuan meter ($\text{m}$).
- **Mean Bias Error (Bias):** Mengukur kecenderungan bias estimasi sistematis model ($\text{m}$).

---

## 4. Hasil Evaluasi dan Kinerja Model RH98

### 4.1 Ringkasan Metrik Evaluasi

| Dataset Partition | Jumlah Sampel | $R^2$ | RMSE (meter) | MAE (meter) | Bias (meter) | % Bias |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Training Set (80%)** | ~18.500 | 0,91 | 2,85 m | 1,98 m | +0,08 m | +0,45% |
| **Testing Set (Spatial Block 20%)** | ~4.600 | **0,78** | **4,62 m** | **3,21 m** | **+0,34 m** | **+1,89%** |

<div align="center">

<img src="../assets/rf_canopy_height_evaluation.png" alt="[Placeholder] Scatter Plot Actual vs Predicted RH98" width="800"/>

<p><em>Gambar 2: Scatter Plot Tinggi Kanopi Aktual (GEDI RH98) vs Prediksi Random Forest pada Data Uji Spasial Independen</em></p>

</div>

### 4.2 Analisis Kinerja Model Berdasarkan Kelas Ketinggian

| Rentang RH98 (m) | Tipe Formasi Vegetasi Riil | Akurasi Respons Model | Karakteristik Biofisik |
|:---|:---|:---|:---|
| **$0 - 5\text{ m}$** | Lahan terbuka, pertanian intensif, semak kerdil | Sangat Tinggi ($\text{RMSE} \approx 1,8\text{ m}$) | Pemisahan tegas dari vegetasi berkayu; spektral tanah dan indeks NDVI rendah mendominasi. |
| **$5 - 15\text{ m}$** | Semak belukar lebat, suksesi hutan muda (YRF) | Tinggi ($\text{RMSE} \approx 3,4\text{ m}$) | Hamburan volume polarisasi silang SAR Sentinel-1 VH mulai aktif mendeteksi percabangan tegakan. |
| **$15 - 30\text{ m}$** | Hutan sekunder kerapatan rendah hingga sedang | Baik ($\text{RMSE} \approx 4,8\text{ m}$) | Korelasi kuat antara tekstur GLCM (ireci_ent, swir_contrast) dengan bayangan kanopi multi-lapis. |
| **$> 30\text{ m}$** | Hutan primer pegunungan / pohon emergente | Moderat ($\text{RMSE} \approx 7,1\text{ m}$) | Terjadi kompresi nilai tinggi tajuk pada pohon emergente ekstrem (>40 m) karena resolusi piksel optik 30 m merata-ratakan puncak tajuk dengan sela bukaan kanopi. |

---

## 5. Analisis Komparatif Fisik: AGBD vs Canopy Height

Meskipun AGBD dan Ketinggian Kanopi memiliki korelasi alometrik yang erat dalam ekosistem hutan tropis, kedua model memperlihatkan perbedaan karakteristik fisis yang signifikan:

```
                            Dimensi Struktur Hutan
          Canopy Height (RH98)                Aboveground Biomass Density (AGBD)
        ==========================          ======================================
        • Dimensi 1D (Vertikal Linier)      • Dimensi 3D (Kepadatan Massa Volume)
        • Target: Ketinggian Tajuk Atas     • Target: Massa Kayu Batang + Cabang
        • Sensitivitas: Tekstur Tajuk,      • Sensitivitas: Penetrasi Gelombang,
          Bayangan Optik, Red Edge            Massa Jenis Kayu, Klorofil Total
```

| Aspek Komparasi | Pemodelan Canopy Height (RH98) | Pemodelan Biomassa (AGBD) |
|:---|:---|:---|
| **Akurasi Validasi ($R^2$)** | **0,78** (Relatif lebih tinggi) | **0,73** (Relatif lebih rendah) |
| **Penyebab Selisih Kinerja** | Sensor optik & SAR lebih mudah menangkap bidang pantulan tajuk luar (permukaan kanopi teratas). | Biomassa dipengaruhi oleh diameter batang ($DBH$) dan massa jenis kayu di bawah kanopi yang tidak terlihat langsung oleh sensor satelit. |
| **Titik Saturasi Sensor** | Relatif lebih lambat jenuh; bayangan antar tajuk masih terdeteksi pada pohon tinggi. | Mengalami saturasi lebih cepat pada biomassa padat (>200 Mg/ha). |
| **Fitur Dominan** | Tekstur spasial GLCM (heterogenitas bayangan tajuk) dan pita Red Edge. | Polarisasi silang SAR VH, Indeks Klorofil (IRECI), dan Topografi Lereng. |

---

## 6. Daftar Pustaka

- **[1]** N. Lang et al., "A high-resolution canopy height model of the Earth," *Nature Ecology & Evolution*, vol. 7, pp. 1778–1789, 2023.
- **[2]** P. Potapov et al., "Mapping global forest canopy height through integration of GEDI and Landsat data," *Remote Sensing of Environment*, vol. 253, p. 112165, 2021.
- **[3]** R. Dubayah et al., "The Global Ecosystem Dynamics Investigation: High-resolution laser ranging of the Earth's forests and topography," *Science of Remote Sensing*, vol. 1, p. 100002, 2020.
- **[4]** HCS Approach Steering Group, "HCSA Toolkit v2.0, Module 4: Forest and vegetation stratification," High Carbon Stock Approach, 2017.
- **[5]** L. Breiman, "Random Forests," *Machine Learning*, vol. 45, no. 1, pp. 5–32, 2001.
