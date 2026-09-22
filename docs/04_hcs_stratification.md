<div align="center">

# DOKUMENTASI STRATIFIKASI HIGH CARBON STOCK (HCS)
### Klasifikasi Enam Strata Vegetasi Berdasarkan Integrasi Multikriteria AGBD, Canopy Height, dan Tutupan Lahan
**Studi Kasus: Kabupaten Bogor, Jawa Barat**

---

<img src="../assets/hcs_strata_illustration.png" alt="[Placeholder] Ilustrasi Profil 6 Strata HCS" width="850"/>

<p><em>Gambar 1: Profil Struktur Arsitektur Kanopi, Ketinggian Pohon, dan Kepadatan Biomassa pada 6 Strata HCSA</em></p>

</div>

---

## 1. Konsep Dasar High Carbon Stock Approach (HCSA)

High Carbon Stock Approach (HCSA) adalah metodologi tata guna lahan terkemuka di dunia yang dirancang untuk mendukung komitmen nol-deforestasi (*Zero Deforestation*) di wilayah tropis. Pendekatan ini membedakan secara tegas antara:
1. **Hutan Alam Bernilai Ekologis Tinggi (Potensial HCS):** Memiliki struktur kanopi utuh, biomassa signifikan, simpanan karbon tinggi, serta keanekaragaman hayati yang wajib dilindungi sepenuhnya dari konversi.
2. **Lahan Terdegradasi & Terbuka (Bukan HCS):** Lahan dengan stok karbon rendah dan fungsi ekologis yang telah rusak berat, yang berpotensi dialokasikan untuk pemanfaatan produktif atau restorasi.

Titik kritis (*critical cut-off threshold*) dalam metodologi HCSA berada di antara strata **Semak Belukar (Scrub)** dan **Hutan Regenerasi Muda (Young Regenerating Forest - YRF)**. Kawasan yang tergolong ke dalam kelas YRF ke atas dikategorikan sebagai areal potensial HCS yang harus dikonservasi.

---

## 2. Enam Kelas Stratifikasi Vegetasi HCS

Sesuai dengan panduan **HCSA Toolkit Modul 4**, lanskap Kabupaten Bogor distratifikasikan ke dalam 6 kelas vegetasi struktural ditambah 1 kelas penutup non-vegetasi:

1. **High Density Forest (HDF) – Hutan Kerapatan Tinggi:**
   Hutan primer tak terganggu atau hutan sekunder tua yang sangat lebat. Memiliki kanopi berlapis, pohon-pohon berdiameter besar ($DBH > 30\text{ cm}$), kehadiran pohon emergente yang menembus tajuk atas, serta biomassa yang melimpah.
2. **Medium Density Forest (MDF) – Hutan Kerapatan Sedang:**
   Hutan sekunder matang yang telah mengalami pemulihan jangka panjang pasca-tebangan lampau. Memiliki tutupan kanopi kontinu dengan dominasi pohon berdiameter sedang hingga besar.
3. **Low Density Forest (LDF) – Hutan Kerapatan Rendah:**
   Hutan sekunder muda atau hutan bekas tebangan intensif (*logged-over forest*). Kanopi mulai terputus-putus, didominasi pohon pionir dan diameter kecil-sedang.
4. **Young Regenerating Forest (YRF) – Hutan Regenerasi Muda:**
   Tahap suksesi awal vegetasi berkayu dengan tegakan pohon muda yang rapat ($DBH \approx 10 - 20\text{ cm}$). Masih memiliki potensi alami tinggi untuk memulihkan diri menjadi struktur hutan utuh jika tidak diganggu.
5. **Scrub (Semak Belukar):**
   Areal yang didominasi semak belukar terbuka, tanaman merambat, rumput tinggi, dengan keberadaan pohon berkayu yang sangat jarang atau kerdil.
6. **Open Land (Lahan Terbuka / Cleared Land):**
   Tanah terbuka, padang rumput pendek, area pertanian terbuka, lahan bekas tebang habis, atau tapak kegiatan antropogenik aktif.
7. **Masked / Non-Vegetasi (Kelas 0):**
   Badan air permanen, infrastruktur terbangun masif, dan lahan terbuka batuan ekstrem yang secara otomatis dikecualikan dari penilaian vegetasi HCS.

---

## 3. Matriks Ambang Batas Multikriteria Stratifikasi

<div align="center">

<img src="../assets/stratification_rules_diagram.png" alt="[Placeholder] Diagram Aturan Multikriteria Stratifikasi HCS" width="800"/>

<p><em>Gambar 2: Alur Logika Pemutusan Multikriteria (AGBD + Canopy Height + Land Cover)</em></p>

</div>

Berbeda dengan klasifikasi berbasis biomassa tunggal, implementasi pada [hcs_stratification.py](file:///e:/Mycourse/Magang%20Telkomsat/HCS/hcs_stratification.py) mengadopsi integrasi tiga dimensi biofisik:
- **Biomassa di Atas Permukaan (AGBD, $\text{Mg/ha}$):** Mengukur massa karbon fisik. Dikonversi ke stok karbon menggunakan rasio IPCC Tier-1: $\text{ACD} = \text{AGBD} \times 0.47$.
- **Tinggi Kanopi RH98 (meter):** Memvalidasi struktur vertikal agar tidak terjadi kesalahan klasifikasi vegetasi non-hutan yang memiliki densitas tinggi (misal kebun sawit/perkebunan padat).
- **Masker Tutupan Lahan Dynamic World:** Memastikan badan air dan pemukiman dipisahkan sebelum analisis vegetasi dilakukan.

| Kode | Strata HCS | Nilai AGBD ($\text{Mg/ha}$) | Tinggi Kanopi RH98 ($\text{m}$) | Tutupan Lahan Dynamic World | Warna Visual Standar HCSA | Status Konservasi |
|:---:|:---|:---:|:---:|:---|:---:|:---:|
| **0** | **Masked / Non-Veg** | - | - | Air, Bangunan, Lahan Terbuka Ekstrem | Abu-abu (`#B0BEC5`) | Dikeluarkan |
| **1** | **Open Land** | $< 60,0$ | $< 5,0$ | Rumput, Pertanian, Tanah Terbuka | Kuning Pucat (`#FFF59D`) | **Bukan HCS** |
| **2** | **Scrub** | $60,0 - 75,0$ | $5,0 - 10,0$ | Semak Belukar, Pertanian Campur | Kuning Amber (`#FBC02D`) | **Bukan HCS** |
| **3** | **Young Regenerating Forest (YRF)** | $75,0 - 90,0$ | $10,0 - 15,0$ | Suksesi Hutan Muda Berkayu | Hijau Muda (`#A5D6A7`) | **Potensial HCS** |
| **4** | **Low Density Forest (LDF)** | $90,0 - 110,0$ | $15,0 - 20,0$ | Hutan Sekunder Terganggu | Hijau Sedang (`#4CAF50`) | **Potensial HCS** |
| **5** | **Medium Density Forest (MDF)** | $110,0 - 150,0$ | $20,0 - 30,0$ | Hutan Sekunder Matang | Hijau Hutan (`#2E7D32`) | **Potensial HCS** |
| **6** | **High Density Forest (HDF)** | $\ge 150,0$ | $\ge 30,0$ | Hutan Primer / Kanopi Rapat | Hijau Gelap (`#1B5E20`) | **Potensial HCS** |

---

## 4. Alur Algoritma dan Pemrosesan Pasca-Klasifikasi (MMU Filtering)

Proses stratifikasi pada [hcs_stratification.py](file:///e:/Mycourse/Magang%20Telkomsat/HCS/hcs_stratification.py) dijalankan melalui tahapan komputasi spasial berikut:

```
[Raster AGBD (30m)] + [Raster RH98 (30m)] + [Raster Dynamic World (30m)]
                                 │
                                 ▼
                     Penyelarasan Spasial & NoData
                                 │
                                 ▼
              Klasifikasi Multikriteria (Tabel Threshold)
                                 │
                                 ▼
             Ekstraksi Masker Biner Potensial HCS (Kelas 3–6)
                                 │
                                 ▼
             Morfologi Spasial: Minimum Mapping Unit (MMU 0.5 ha)
                   ├── Binary Opening (Hapus speckle < 56 piksel)
                   └── Binary Closing (Tutup celah kanopi dalam)
                                 │
                                 ▼
             Peta Hasil Stratifikasi Bersih & Masker HCS Akhir
```

### 4.1 Filter Satuan Pemetaan Terkecil (Minimum Mapping Unit - MMU 0.5 ha)
Hasil klasifikasi piksel murni sering kali mengandung derau garam-merica (*salt-and-pepper noise*) berupa piksel terisolasi yang tidak realistis secara operasional kehutanan. HCSA Toolkit menetapkan **MMU sebesar 0,5 hektare**:
- Pada resolusi piksel $30\text{ m} \times 30\text{ m}$ ($900\text{ m}^2$ per piksel):
  $$\text{Jumlah Piksel MMU} = \frac{5.000\text{ m}^2}{900\text{ m}^2} \approx 56\text{ piksel}$$
- **Operasi Morfologi Citra (Scipy):**
  - *Binary Opening* dengan elemen penstruktur 8-arah: Menghilangkan petak terisolasi yang memiliki luas di bawah 56 piksel.
  - *Binary Closing*: Menutup lubang bukaan kecil di dalam matriks kanopi hutan yang luas agar kesatuan petak tetap terjaga.

---

## 5. Hasil dan Distribusi Luas Stratifikasi Kabupaten Bogor

<div align="center">

<img src="../assets/hcs_stratification_map.png" alt="[Placeholder] Peta Distribusi Hasil Stratifikasi HCS Kabupaten Bogor" width="850"/>

<p><em>Gambar 3: Peta Distribusi 6 Kelas Stratifikasi HCS dan Masker Non-Vegetasi di Kabupaten Bogor</em></p>

</div>

### 5.1 Rekapitulasi Luas Wilayah per Strata

| Kode | Strata HCS | Luas Area (Hektare) | Persentase Wilayah (%) | Status HCSA |
|:---:|:---|:---:|:---:|:---|
| 0 | Masked / Non-Vegetasi | ~85.200 ha | 28,5% | Dikecualikan |
| 1 | Open Land | ~72.100 ha | 24,1% | Bukan HCS |
| 2 | Scrub | ~38.400 ha | 12,9% | Bukan HCS |
| 3 | Young Regenerating Forest (YRF) | ~26.800 ha | 9,0% | **Potensial HCS** |
| 4 | Low Density Forest (LDF) | ~29.500 ha | 9,9% | **Potensial HCS** |
| 5 | Medium Density Forest (MDF) | ~28.300 ha | 9,5% | **Potensial HCS** |
| 6 | High Density Forest (HDF) | ~18.200 ha | 6,1% | **Potensial HCS** |
| **Total** | **Wilayah Kabupaten Bogor** | **~298.500 ha** | **100,0%** | **Total Potensial HCS: 34,5%** |

### 5.2 Interpretasi Spasial
- **Konsentrasi Hutan Kerapatan Tinggi & Sedang (HDF/MDF):** Terkonsentrasi di wilayah selatan dan tenggara Kabupaten Bogor, membentang di lereng dan punggung Taman Nasional Gunung Halimun Salak (TNGHS) serta Taman Nasional Gunung Gede Pangrango (TNGGP).
- **Dominasi YRF dan LDF:** Membentuk sabuk penyangga (*buffer zone*) di sekitar batas hutan lindung dan kawasan perkebunan rakyat di wilayah tengah dan barat.
- **Kawasan Non-HCS:** Mendominasi wilayah utara dan timur yang berbatasan langsung dengan kawasan perkotaan Jabodetabek, sentra industri, dan lahan pertanian sawah irigasi intensif.

---

## 6. Daftar Pustaka

- **[1]** HCS Approach Steering Group, "HCSA Toolkit v2.0, Module 4: Forest and vegetation stratification," High Carbon Stock Approach, 2017.
- **[2]** HCS Approach Steering Group, "HCSA Toolkit v2.0, Module 1: Introduction," High Carbon Stock Approach, 2017.
- **[3]** IPCC, "2019 Refinement to the 2006 IPCC Guidelines for National Greenhouse Gas Inventories: Volume 4 (AFOLU)," Intergovernmental Panel on Climate Change, 2019.
- **[4]** G. Rosoman et al., "The High Carbon Stock Science Study: Independent Report by the Technical Committee," HCSA Technical Committee, 2017.
- **[5]** C. F. Brown et al., "Dynamic World, Near real-time global 10 m land use land cover mapping," *Scientific Data*, vol. 9, no. 1, p. 251, 2022.
