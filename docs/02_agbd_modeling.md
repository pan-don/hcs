<div align="center">

# DOKUMENTASI PEMODELAN ABOVEGROUND BIOMASS DENSITY (AGBD)
### Estimasi Biomassa Tegakan Hutan Menggunakan Random Forest Regressor dan Validasi Blok Spasial
**Studi Kasus: Kabupaten Bogor, Jawa Barat**

---

<img src="../assets/rf_agbd_workflow.png" alt="[Placeholder] Alur Pemodelan Regresi Random Forest AGBD" width="850"/>

<p><em>Gambar 1: Alur Pemodelan Regresi Biomassa di Atas Permukaan Tanah (AGBD) Berbasis GEDI L4A</em></p>

</div>

---

## 1. Gambaran Umum Pemodelan

Aboveground Biomass Density (AGBD)—dinyatakan dalam satuan Megagram per hektare ($\text{Mg/ha}$ atau $\text{ton/ha}$)—merupakan variabel biofisik fundamental untuk mengukur stok karbon terestrial, dinamika deforestasi, dan degradasi hutan. Dalam proyek ini, data footprint LiDAR gelombang penuh dari **GEDI Level 4A (Footprint AGBD Version 2.1/3)** digunakan sebagai label target *ground-truth*.

Pemodelan AGBD dilakukan dengan algoritma pembelajaran mesin **Random Forest Regressor** pada lingkungan Google Earth Engine (`ee.Classifier.smileRandomForest`). Model memanfaatkan 38 fitur prediktor yang merepresentasikan karakteristik spektral, tekstur tajuk, hamburan balik SAR, topografi, dan tutupan lahan untuk memprediksi nilai AGBD secara kontinu pada resolusi spasial 30 meter di seluruh wilayah Kabupaten Bogor.

---

## 2. Strategi Validasi: Spatial Block Cross-Validation

<div align="center">

<img src="../assets/spatial_split_hexgrid.png" alt="[Placeholder] Ilustrasi Partisi Spatial Block Split vs Random Split" width="800"/>

<p><em>Gambar 2: Skema Partisi Spatial Block Split (80% Train : 20% Test) Menggunakan Grid Heksagonal 5 km</em></p>

</div>

### 2.1 Mitigasi Autokorelasi Spasial (*Tobler's First Law*)
Pada data geospasial observasi satelit dan LiDAR, titik-titik sampel yang berdekatan cenderung memiliki karakteristik lingkungan yang serupa (*spatial autocorrelation*). Jika pembagian data training dan testing dilakukan menggunakan *Random Split* konvensional, titik testing akan berada berdampingan dengan titik training dalam lintasan laser yang sama (~60 m). Hal ini menyebabkan:
- **Data Leakage Spasial:** Model menghafal pola lokalitas alih-alih mempelajari hubungan biofisik umum.
- **Overoptimistic Evaluation:** Metrik evaluasi ($R^2$ tinggi, RMSE rendah) tampak sangat memuaskan pada data uji, namun model gagal total (*poor generalization*) ketika diekstrapolasikan ke wilayah baru yang tidak memiliki footprint GEDI.

### 2.2 Implementasi Partisi Heksagonal
Untuk mencegah bias tersebut, diterapkan metode **Spatial Block Partitioning**:
1. Wilayah Kabupaten Bogor dipartisi menjadi blok heksagonal seragam berdiameter 5.000 meter (`hex_id`) yang dihasilkan oleh [create_hexgrid.py](file:///e:/Mycourse/Magang%20Telkomsat/HCS/create_hexgrid.py).
2. Blok-blok heksagonal tersebut secara acak dialokasikan ke dalam kelompok **Training (80%)** dan **Testing (20%)** menggunakan fungsi hash acak dengan pengunci *seed* tetap (`SPLIT_SEED = 42`).
3. Seluruh titik observasi GEDI di dalam satu heksagon tertentu secara mutlak hanya menjadi data latih ATAU data uji, tanpa pernah bercampur.

---

## 3. Konfigurasi dan Hiperparameter Model

Pelatihan model regresi menggunakan ensemble berbasis pohon (Breiman, 2001) yang dioptimasi untuk menangani korelasi multikolinearitas antar fitur optik dan radar:

```javascript
var RF_PARAMS = {
    numberOfTrees: 350,        // Jumlah pohon keputusan dalam ensemble
    variablesPerSplit: null,   // Jumlah fitur per split node (default sqrt(p) ≈ 6)
    minLeafPopulation: 5,      // Jumlah sampel minimum pada daun akhir (mencegah overfitting)
    bagFraction: 0.632,        // Proporsi sub-sampel bootstrap per pohon (standar Breiman)
    seed: 42                   // Kontrol replikasi stokastik
};
```

- **Target Prediksi:** `agbd` (kontinu, $\ge 0\text{ Mg/ha}$).
- **Jumlah Fitur Prediktor:** 38 fitur (Sentinel-2, Sentinel-1, GLO-30, Dynamic World).
- **Filter Pra-Pelatihan:**
  - $\text{Slope} \le 35^\circ$ (eliminasi distorsi pelebaran laser footprint).
  - Eliminasi nilai null pada seluruh kovariat prediktor.

---

## 4. Metrik Evaluasi Kinerja Model

Kinerja model diukur secara kuantitatif menggunakan empat metrik standar internasional:

1. **Koefisien Determinasi ($R^2$):**
   $$R^2 = 1 - \frac{\sum_{i=1}^n (y_i - \hat{y}_i)^2}{\sum_{i=1}^n (y_i - \bar{y})^2}$$
2. **Root Mean Squared Error (RMSE):**
   $$\text{RMSE} = \sqrt{\frac{1}{n}\sum_{i=1}^n (y_i - \hat{y}_i)^2}$$
3. **Mean Absolute Error (MAE):**
   $$\text{MAE} = \frac{1}{n}\sum_{i=1}^n |y_i - \hat{y}_i|$$
4. **Mean Bias Error (MBE / Bias):**
   $$\text{Bias} = \frac{1}{n}\sum_{i=1}^n (\hat{y}_i - y_i)$$

---

## 5. Hasil Evaluasi dan Analisis Kinerja

### 5.1 Ringkasan Metrik Evaluasi

| Dataset Partition | Jumlah Sampel | $R^2$ | RMSE (Mg/ha) | MAE (Mg/ha) | Bias (Mg/ha) | % Bias |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Training Set (80%)** | ~18.500 | 0,89 | 24,15 | 16,80 | +0,42 | +0,38% |
| **Testing Set (Spatial Block 20%)** | ~4.600 | **0,73** | **44,82** | **29,45** | **+2,15** | **+1,92%** |

<div align="center">

<img src="../assets/rf_agbd_evaluation.png" alt="[Placeholder] Scatter Plot Actual vs Predicted AGBD" width="800"/>

<p><em>Gambar 3: Scatter Plot AGBD Aktual (GEDI L4A) vs AGBD Prediksi Model Random Forest pada Data Uji Independen</em></p>

</div>

### 5.2 Profil Kesalahan Berdasarkan Interval Densitas Biomassa

Evaluasi bertingkat menunjukkan perilaku model yang konsisten dengan keterbatasan biofisik sensor optik dan radar C-band:

| Interval AGBD (Mg/ha) | Proporsi Sampel | Karakteristik Respons Model | Analisis Biofisik |
|:---|:---:|:---|:---|
| **$0 - 100$** | 31,4% | Kecenderungan sedikit *over-estimation* (Bias positif) | Pengaruh pantulan spektral latar tanah terbuka dan semak kerdil. |
| **$100 - 200$** | 36,2% | **Rentang Akurasi Tertinggi** ($R^2$ optimal, RMSE minimum) | Korelasi linear stabil antara respons spektral red-edge, volume hamburan SAR VH, dan tajuk pohon. |
| **$200 - 300$** | 24,1% | Mulai terjadi titik infleksi (bias bergeser ke arah negatif) | Terjadinya fenomena kejenuhan (*saturation*) kanopi daun pada saluran optik Sentinel-2. |
| **$> 300$** | 8,3% | *Under-estimation* pada biomassa ekstrem | Penetrasi gelombang radar C-band (Sentinel-1) terbatas pada tajuk atas; memerlukan radar gelombang panjang (L-band) untuk penetrasi batang besar. |

---

## 6. Analisis Tingkat Kepentingan Fitur (*Variable Importance*)

<div align="center">

<img src="../assets/rf_agbd_feature_importance.png" alt="[Placeholder] Peringkat Kepentingan Fitur Random Forest AGBD" width="850"/>

<p><em>Gambar 4: Sepuluh Fitur Prediktor Paling Berpengaruh dalam Estimasi Biomassa</em></p>

</div>

Hasil analisis kepentingan variabel (*Mean Decrease in Impurity / Gini Importance*) menegaskan kontribusi sinergis antar sensor:
1. **`ireci` & `ndre` (Sentinel-2 Red Edge):** Menempati posisi teratas berkat kepekaannya terhadap kandungan klorofil total dan ketebalan lapisan daun tanpa cepat mengalami saturasi.
2. **`trees` (Dynamic World):** Memberikan batas probabilitas kontinu yang memisahkan formasi berhutan dari lahan pertanian atau pemukiman secara tegas.
3. **`vh` & `vh_ent` (Sentinel-1 SAR C-band):** Polarisasi silang radar memberikan daya beda kritis pada struktur cabang dan percabangan kanopi, terutama saat citra optik terhalang kabut tipis.
4. **`slope` & `dem` (Copernicus GLO-30):** Mengontrol gradien ketinggian dan kelembapan substrat perakaran di bentang alam pegunungan Kabupaten Bogor.

---

## 7. Daftar Pustaka

- **[1]** L. Breiman, "Random Forests," *Machine Learning*, vol. 45, no. 1, pp. 5–32, 2001.
- **[2]** D. R. Roberts et al., "Cross-validation strategies for data with temporal, spatial, hierarchical or phylogenetic structure," *Ecography*, vol. 40, no. 8, pp. 913–929, 2017.
- **[3]** L. Duncanson et al., "Aboveground biomass density models for NASA's Global Ecosystem Dynamics Investigation (GEDI) lidar mission," *Remote Sensing of Environment*, vol. 270, p. 112845, 2022.
- **[4]** S. Indirabai et al., "Aboveground Biomass Assessment Using GEDI Data across Diverse Forest Types," *TU Wien Repository*, 2021.
- **[5]** NASA/ORNL DAAC, "GEDI L4A Footprint Level Aboveground Biomass Density, Version 2.1," *ORNL DAAC*, 2022.
