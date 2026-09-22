from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject
from scipy.ndimage import binary_closing, binary_opening, label


# ==============================================================================
# VARIABEL KONFIGURASI PENGGUNA
# ==============================================================================

# Folder dataset
DATA_DIR = Path("data")

# File input default
INPUT_FILE = DATA_DIR / "agbd" / "AGBD_Carbon_2021.tif"
INPUT_LC_FILE = DATA_DIR / "landcover" / "Landcover_DW9_2021.tif"
INPUT_CH_FILE = DATA_DIR / "canopy_height" / "Canopy_Height_RH98_2021.tif"

# Set True jika ingin memproses seluruh file AGBD di folder data/agbd secara batch
PROCESS_ALL = False

# Folder output hasil stratifikasi
OUTPUT_DIR = Path("output/stratification")

# Parameter Stratifikasi HCSA Toolkit
CARBON_FRACTION = 0.47      # Faktor konversi AGBD -> ACD (IPCC Tier-1)
AGBD_MAX_VALID  = 500.0     # Ambang batas atas AGBD valid (Mg/ha)
MMU_PIXELS      = 56        # MMU 0.5 ha (56 piksel @ 30 m)
HCS_CLASS_MIN   = 3         # Kelas minimum HCS (3=YRF, 4=LDF, 5=MDF, 6=HDF)
NODATA_IN       = -9999.0   # Nilai NoData fallback jika tidak ada di metadata raster

# Ambang batas AGBD (Mg/ha) untuk 6 kelas stratifikasi HCS pada wilayah vegetasi
# [60.0, 75.0, 90.0, 110.0, 150.0]
AGBD_THRESHOLDS = [60.0, 75.0, 90.0, 110.0, 150.0]

# Ambang batas tinggi kanopi / RH98 (m) untuk stratifikasi / validasi struktural HCS (HCSA Modul 4)
# [5.0, 10.0, 15.0, 20.0, 30.0]
CANOPY_HEIGHT_THRESHOLDS = [5.0, 10.0, 15.0, 20.0, 30.0]

# ==============================================================================


CONFIG = {
    "carbon_fraction": CARBON_FRACTION,
    "agbd_thresholds": AGBD_THRESHOLDS,
    "canopy_height_thresholds": CANOPY_HEIGHT_THRESHOLDS,
    "agbd_max_valid":  AGBD_MAX_VALID,
    "hcs_class_min":   HCS_CLASS_MIN,
    "mmu_pixels":      MMU_PIXELS,
    "nodata_in":       NODATA_IN,
}

CLASS_LABELS = {
    0: "Masking / Non-Vegetasi",
    1: "Open Land",
    2: "Scrub",
    3: "YRF (Hutan Regenerasi Muda)",
    4: "LDF (Hutan Kerapatan Rendah)",
    5: "MDF (Hutan Kerapatan Sedang)",
    6: "HDF (Hutan Kerapatan Tinggi)",
}

HCS_STATUS = {
    0: "Masked / Non-Veg",
    1: "Bukan HCS",
    2: "Bukan HCS",
    3: "Potensial HCS",
    4: "Potensial HCS",
    5: "Potensial HCS",
    6: "Potensial HCS",
}

# Palet warna resmi HCSA (RGBA)
HCS_COLORMAP = {
    0: (176, 190, 197, 255),  # Abu-abu: Masking / Non-Vegetasi (#B0BEC5)
    1: (255, 245, 157, 255),  # Kuning Pucat: Open Land (#FFF59D)
    2: (251, 192, 45, 255),   # Kuning Amber: Scrub (#FBC02D)
    3: (165, 214, 167, 255),  # Hijau Muda: YRF (#A5D6A7)
    4: (76, 175, 80, 255),    # Hijau Sedang: LDF (#4CAF50)
    5: (46, 125, 50, 255),    # Hijau Hutan: MDF (#2E7D32)
    6: (27, 94, 32, 255),     # Hijau Gelap: HDF (#1B5E20)
}


# ==============================================================================
# FUNGSI I/O & ALIGNMENT RASTER
# ==============================================================================

def read_raster(path: str | Path) -> tuple[np.ndarray, dict]:
    """Baca GeoTIFF band pertama sebagai float32; NoData diganti NaN."""
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float32)
        meta = src.meta.copy()
        nodata = src.nodata if src.nodata is not None else CONFIG["nodata_in"]
    data[data == nodata] = np.nan
    return data, meta


def align_landcover(lc_path: str | Path, target_meta: dict) -> np.ndarray:
    """Reproyeksi dan selaraskan grid tutupan lahan ke grid raster target AGBD."""
    aligned = np.zeros((target_meta["height"], target_meta["width"]), dtype=np.uint8)
    with rasterio.open(lc_path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=aligned,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=target_meta["transform"],
            dst_crs=target_meta["crs"],
            resampling=Resampling.nearest,
        )
    return aligned


def align_canopy_height(ch_path: str | Path, target_meta: dict) -> np.ndarray:
    """Reproyeksi dan selaraskan grid tinggi kanopi (RH98) ke grid raster target AGBD."""
    aligned = np.full((target_meta["height"], target_meta["width"]), np.nan, dtype=np.float32)
    with rasterio.open(ch_path) as src:
        nodata = src.nodata if src.nodata is not None else CONFIG["nodata_in"]
        src_data = src.read(1).astype(np.float32)
        src_data[src_data == nodata] = np.nan
        reproject(
            source=src_data,
            destination=aligned,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=target_meta["transform"],
            dst_crs=target_meta["crs"],
            resampling=Resampling.bilinear,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
    aligned[aligned < 0] = 0.0
    return aligned


def write_raster(
    path: str | Path,
    data: np.ndarray,
    meta: dict,
    dtype: str = "float32",
    nodata: float | int = -9999,
) -> None:
    """Tulis ndarray ke GeoTIFF LZW-compressed dengan metadata asli."""
    out_meta = meta.copy()
    out_meta.update(dtype=dtype, count=1, nodata=nodata, compress="lzw", driver="GTiff")
    fill_val = nodata if not np.isnan(float(nodata)) else 0
    out_data = np.where(np.isnan(data.astype(float)), fill_val, data).astype(dtype)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **out_meta) as dst:
        dst.write(out_data, 1)
    print(f"  [OK] Tersimpan: {path}")


def write_discrete_geotiff(
    path: str | Path,
    data: np.ndarray,
    meta: dict,
    class_labels: dict[int, str],
    hcs_status: dict[int, str],
    colormap: dict[int, tuple[int, int, int, int]],
    nodata: int = 255,
) -> None:
    """
    Tulis raster diskrit uint8 dengan embedded Colormap dan XML PAM Raster Attribute Table (VAT)
    agar ArcGIS otomatis menampilkannya sebagai Unique Values (Diskrit) dengan nama kelas dan warna resmi.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out_meta = meta.copy()
    out_meta.update(
        dtype="uint8",
        count=1,
        nodata=nodata,
        compress="lzw",
        driver="GTiff",
    )

    clean_data = np.nan_to_num(data, nan=nodata).astype(np.uint8)

    with rasterio.open(out_path, "w", **out_meta) as dst:
        dst.write(clean_data, 1)
        dst.write_colormap(1, colormap)

    # Buat file pendamping .aux.xml (Raster Attribute Table PAM GDAL/ArcGIS)
    t = meta.get("transform")
    ha_per_px = abs(t[0]) * abs(t[4]) / 10_000.0 if t is not None else 0.09

    rows_xml = []
    for val in range(7):
        cnt = int(np.count_nonzero(clean_data == val))
        name = class_labels.get(val, f"Class {val}")
        st = hcs_status.get(val, "-")
        area = round(cnt * ha_per_px, 2)
        rows_xml.append(
            f"      <Row index=\"{val}\">\n"
            f"        <F>{val}</F>\n"
            f"        <F>{cnt}</F>\n"
            f"        <F>{name}</F>\n"
            f"        <F>{st}</F>\n"
            f"        <F>{area}</F>\n"
            f"      </Row>"
        )

    aux_xml = (
        "<PAMDataset>\n"
        "  <PAMRasterBand band=\"1\">\n"
        "    <GDALRasterAttributeTable>\n"
        "      <FieldDefn index=\"0\">\n"
        "        <Name>Value</Name>\n"
        "        <Type>0</Type>\n"
        "        <Usage>0</Usage>\n"
        "      </FieldDefn>\n"
        "      <FieldDefn index=\"1\">\n"
        "        <Name>Count</Name>\n"
        "        <Type>0</Type>\n"
        "        <Usage>1</Usage>\n"
        "      </FieldDefn>\n"
        "      <FieldDefn index=\"2\">\n"
        "        <Name>ClassName</Name>\n"
        "        <Type>2</Type>\n"
        "        <Usage>2</Usage>\n"
        "      </FieldDefn>\n"
        "      <FieldDefn index=\"3\">\n"
        "        <Name>HCS_Status</Name>\n"
        "        <Type>2</Type>\n"
        "        <Usage>0</Usage>\n"
        "      </FieldDefn>\n"
        "      <FieldDefn index=\"4\">\n"
        "        <Name>Area_Ha</Name>\n"
        "        <Type>1</Type>\n"
        "        <Usage>0</Usage>\n"
        "      </FieldDefn>\n"
        + "\n".join(rows_xml) + "\n"
        "    </GDALRasterAttributeTable>\n"
        "  </PAMRasterBand>\n"
        "</PAMDataset>\n"
    )

    aux_path = out_path.with_name(out_path.name + ".aux.xml")
    aux_path.write_text(aux_xml, encoding="utf-8")
    print(f"  [OK] Tersimpan (Raster Diskrit + Tabel Atribut ArcGIS): {out_path}")


def write_multiband_raster(
    path: str | Path,
    bands: list[np.ndarray],
    band_names: list[str],
    meta: dict,
    dtype: str = "float32",
    nodata: float | int = -9999,
) -> None:
    """Tulis multi-band GeoTIFF LZW-compressed dengan deskripsi tiap band."""
    out_meta = meta.copy()
    out_meta.update(dtype=dtype, count=len(bands), nodata=nodata, compress="lzw", driver="GTiff")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **out_meta) as dst:
        for idx, (b_data, b_name) in enumerate(zip(bands, band_names), start=1):
            fill_val = nodata if not np.isnan(float(nodata)) else 0
            clean_b = np.where(np.isnan(b_data.astype(float)), fill_val, b_data).astype(dtype)
            dst.write(clean_b, idx)
            dst.set_band_description(idx, b_name)
    print(f"  [OK] Tersimpan (Multi-Band Pelengkap): {path}")


# =============================================================
# FUNGSI STRATIFIKASI & MASKING
# =============================================================

def classify_agbd_with_masking(
    agbd: np.ndarray,
    lc: np.ndarray | None,
    thresholds: list[float],
) -> tuple[np.ndarray, np.ndarray]:
    """
    Klasifikasi AGBD ke dalam:
      - Nilai 0 : Masking / Non-Vegetasi (Badan Air, Lahan Terbangun, Lahan Terbuka, AGBD <= 0)
      - Nilai 1-6 : 6 Kelas Stratifikasi HCS pada wilayah vegetasi.
    """
    clean_agbd = np.nan_to_num(agbd, nan=0.0)

    if lc is not None:
        # Dynamic World: 0=Water, 6=Built, 7=Bare, 8=Snow
        non_veg_mask = (lc == 0) | (lc == 6) | (lc == 7) | (lc == 8) | (clean_agbd <= 0)
    else:
        non_veg_mask = clean_agbd <= 0

    veg_mask = ~non_veg_mask

    hcs = np.zeros(agbd.shape, dtype=np.uint8)

    # Hanya wilayah vegetasi yang diklasifikasikan ke dalam 6 kelas HCS (1 s/d 6)
    if np.any(veg_mask):
        veg_classes = np.digitize(clean_agbd[veg_mask], bins=thresholds, right=False) + 1
        hcs[veg_mask] = np.clip(veg_classes, 1, 6).astype(np.uint8)

    # Wilayah non-vegetasi dipastikan bernilai 0 (Masking)
    hcs[non_veg_mask] = 0

    return hcs, veg_mask


def make_hcs_mask(hcs_class: np.ndarray, hcs_class_min: int) -> np.ndarray:
    """Kelas >= hcs_class_min -> 1 (Potensial HCS); selain itu -> 0."""
    return np.where((hcs_class >= hcs_class_min) & (hcs_class > 0), 1, 0).astype(np.uint8)


def sieve_filter(mask: np.ndarray, mmu_pixels: int) -> np.ndarray:
    """
    Hapus patch HCS < MMU (0.5 ha = 56 piksel @ 30 m).
    Diikuti morphological closing dan opening untuk merapikan batas kawasan petak.
    """
    struct8 = np.ones((3, 3), dtype=int)
    binary = mask.astype(bool)

    labeled, _ = label(binary, structure=struct8)
    sizes = np.bincount(labeled.ravel())

    # Pertahankan hanya patch yang >= mmu_pixels
    keep_mask = sizes >= mmu_pixels
    keep_mask[0] = False  # Label 0 adalah background
    binary = keep_mask[labeled]

    binary = binary_closing(binary, structure=struct8, iterations=1)
    binary = binary_opening(binary, structure=struct8, iterations=1)
    return binary.astype(np.uint8)


def apply_sieve_to_hcs_classes(hcs_class: np.ndarray, sieved_mask: np.ndarray, hcs_class_min: int) -> np.ndarray:
    """
    Patch yang awalnya >= hcs_class_min tetapi tidak lolos MMU
    didowngrade menjadi Scrub (kelas 2) / Bukan HCS sesuai standar HCSA Toolkit.
    Area masking (kelas 0) tetap tidak berubah.
    """
    final_class = hcs_class.copy()
    downgraded = (hcs_class >= hcs_class_min) & (sieved_mask == 0)
    final_class[downgraded] = 2
    return final_class


# ==============================================================================
# FUNGSI REPORTING
# ==============================================================================

def _pixel_area_ha(meta: dict) -> float:
    t = meta.get("transform")
    return abs(t[0]) * abs(t[4]) / 10_000.0 if t is not None else 0.09


def _print_stats(label_str: str, arr: np.ndarray) -> None:
    v = arr[~np.isnan(arr)]
    if v.size == 0:
        print(f"      {label_str}: tidak ada data valid")
        return
    print(f"      {label_str}: min={v.min():.2f}  mean={v.mean():.2f}  max={v.max():.2f}")


def _print_class_table(
    hcs_class: np.ndarray,
    meta: dict,
    ch: np.ndarray | None = None,
    title: str = "Tabel Kelas HCS",
) -> None:
    ha = _pixel_area_ha(meta)
    print(f"\n      --- {title} ---")
    if ch is not None:
        print(f"      {'ID':<4} {'Nama Kelas':<32} {'Piksel':>9} {'Luas (ha)':>11}  {'Mean CH (m)':>12}  Status HCSA")
        print(f"      {'-'*86}")
    else:
        print(f"      {'ID':<4} {'Nama Kelas':<38} {'Piksel':>10} {'Luas (ha)':>12}  Status HCSA")
        print(f"      {'-'*76}")

    for cls_id in range(7):
        name = CLASS_LABELS[cls_id]
        status = HCS_STATUS[cls_id]
        mask = (hcs_class == cls_id)
        n = int(np.count_nonzero(mask))
        pct = (n / hcs_class.size) * 100.0
        if ch is not None:
            ch_vals = ch[mask & ~np.isnan(ch) & (ch > 0)]
            ch_mean_str = f"{ch_vals.mean():.1f} m" if ch_vals.size > 0 else "-"
            print(f"      [{cls_id}]  {name:<30} {n:>9,} {n*ha:>11,.1f}  {ch_mean_str:>12}  {status:<14} ({pct:>5.1f}%)")
        else:
            print(f"      [{cls_id}]  {name:<36} {n:>10,} {n*ha:>12,.1f}  {status:<14} ({pct:>5.1f}%)")


# ==============================================================================
# PIPELINE UTAMA STRATIFIKASI
# ==============================================================================

def run_stratification(
    agbd_path: str | Path,
    lc_path: str | Path | None,
    output_dir: str | Path,
    ch_path: str | Path | None = None,
    cfg: dict = CONFIG,
) -> Path:
    """
    Jalankan pipeline stratifikasi HCSA lengkap dengan output diskrit untuk ArcGIS.
    Mendukung integrasi peta Canopy Height (RH98) untuk validasi struktural strata HCS.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 68)
    print("  PIPELINE STRATIFIKASI HCS DENGAN MASKING NON-VEGETASI")
    print("  (HCSA Toolkit Modul 3-4 | Output Diskrit uint8 untuk ArcGIS)")
    print("=" * 68)

    # 1. Baca AGBD
    print(f"\n[1/6] Membaca Raster AGBD: {agbd_path}")
    agbd, meta = read_raster(agbd_path)
    ha = _pixel_area_ha(meta)
    print(f"      Resolusi : {abs(meta['transform'][0]):.1f} m")
    print(f"      Dimensi  : {meta['width']} x {meta['height']} piksel")
    print(f"      CRS      : {meta.get('crs', 'tidak diketahui')}")
    _print_stats("AGBD (Mg/ha)", agbd)

    # 2. Baca & Selaraskan Tutupan Lahan
    lc = None
    if lc_path is not None and Path(lc_path).exists():
        print(f"\n[2/6] Membaca & Menyelaraskan Tutupan Lahan: {lc_path}")
        lc = align_landcover(lc_path, meta)
        print(f"      Dimensi LC aligned: {lc.shape[1]} x {lc.shape[0]} piksel")
    else:
        print("\n[2/6] Peringatan: File tutupan lahan tidak ditemukan, stratifikasi menggunakan masking AGBD <= 0.")

    # 2b. Baca & Selaraskan Canopy Height jika tersedia
    ch = None
    if ch_path is not None and Path(ch_path).exists():
        print(f"\n[2b/6] Membaca & Menyelaraskan Canopy Height (RH98): {ch_path}")
        ch = align_canopy_height(ch_path, meta)
        print(f"       Dimensi CH aligned: {ch.shape[1]} x {ch.shape[0]} piksel")
        _print_stats("Canopy Height RH98 (m)", ch[ch > 0])
    else:
        print("\n[2b/6] Informasi: Raster Canopy Height tidak disediakan (opsional).")

    # 3. Hitung ACD (tC/ha)
    print(f"\n[3/6] Konversi AGBD -> ACD (Faktor Konversi IPCC = {cfg['carbon_fraction']})")
    acd = (np.nan_to_num(agbd, nan=0.0) * cfg["carbon_fraction"]).astype(np.float32)
    _print_stats("ACD (tC/ha)", acd[acd > 0])

    # 4. Reklasifikasi AGBD -> Nilai 0 (Masking) dan 6 Kelas HCS (1-6)
    print("\n[4/6] Reklasifikasi AGBD -> Masking Non-Vegetasi [0] & 6 Kelas HCS [1-6]")
    print(f"      Thresholds AGBD: {cfg['agbd_thresholds']} Mg/ha")
    hcs_class_raw, veg_mask = classify_agbd_with_masking(agbd, lc, cfg["agbd_thresholds"])
    _print_class_table(hcs_class_raw, meta, ch=ch, title="Kelas HCS Sebelum Sieve Filter")

    # 5. Sieve Filter (MMU 0.5 ha = 56 piksel)
    print(f"\n[5/6] Sieve Filter (MMU = {cfg['mmu_pixels']} piksel / {cfg['mmu_pixels'] * ha:.2f} ha)")
    mask_raw = make_hcs_mask(hcs_class_raw, cfg["hcs_class_min"])
    hcs_mask_sieved = sieve_filter(mask_raw, cfg["mmu_pixels"])
    
    # Terapkan hasil sieve ke peta kelas HCS final (patch < MMU diturunkan ke Scrub)
    hcs_final = apply_sieve_to_hcs_classes(hcs_class_raw, hcs_mask_sieved, cfg["hcs_class_min"])
    _print_class_table(hcs_final, meta, ch=ch, title="Kelas HCS Final (Setelah Sieve Filter & Downgrade MMU)")

    # 6. Simpan Hasil dalam 1 File GeoTIFF Final Diskrit untuk ArcGIS
    print(f"\n[6/6] Menyimpan Hasil Stratifikasi Final (Diskrit)")
    year_tag = Path(agbd_path).stem.replace("AGBD_Carbon_", "").replace("AGBD_Prediction_", "")
    final_output_path = out / f"HCS_Stratification_{year_tag}_Final.tif"

    # Simpan sebagai single-band uint8 dengan colormap dan tabel atribut ArcGIS
    write_discrete_geotiff(
        path=final_output_path,
        data=hcs_final,
        meta=meta,
        class_labels=CLASS_LABELS,
        hcs_status=HCS_STATUS,
        colormap=HCS_COLORMAP,
        nodata=255,
    )

    # Simpan file data pelengkap multi-band kontinu (AGBD, ACD, LC, Canopy Height)
    multiband_path = out / f"HCS_Multiband_Data_{year_tag}.tif"
    bands_to_export = [
        hcs_final.astype(np.float32),
        hcs_mask_sieved.astype(np.float32),
        np.nan_to_num(agbd, nan=0.0).astype(np.float32),
        acd,
    ]
    band_names = [
        "HCS_Stratification_Class_0to6",
        "HCS_Binary_Mask_Sieved",
        "AGBD_Mg_per_ha",
        "ACD_tC_per_ha",
    ]
    if lc is not None:
        bands_to_export.append(lc.astype(np.float32))
        band_names.append("Dynamic_World_Landcover_9Class")

    if ch is not None:
        bands_to_export.append(np.nan_to_num(ch, nan=0.0).astype(np.float32))
        band_names.append("Canopy_Height_RH98_m")
        # Simpan juga file canopy height yang telah diselaraskan ke resolusi dan grid target
        write_raster(out / f"Canopy_Height_{year_tag}_Aligned.tif", ch, meta, dtype="float32", nodata=-9999.0)

    write_multiband_raster(
        path=multiband_path,
        bands=bands_to_export,
        band_names=band_names,
        meta=meta,
        dtype="float32",
        nodata=-9999.0,
    )

    # Simpan juga layer standar untuk kompatibilitas script patch analysis
    write_raster(out / "hcs_mask.tif", hcs_mask_sieved, meta, dtype="uint8", nodata=255)
    write_raster(out / "hcs_class.tif", hcs_final, meta, dtype="uint8", nodata=255)

    n_hcs = int(np.count_nonzero(hcs_mask_sieved))
    hcs_area_ha = n_hcs * ha
    print(f"\n{'='*68}")
    print(f"  HASIL AKHIR STRATIFIKASI HCS:")
    print(f"  • Peta Final Diskrit : {final_output_path.resolve()}")
    print(f"  • Data Multi-Band    : {multiband_path.resolve()}")
    if ch is not None:
        print(f"  • Canopy Height (CH) : {(out / f'Canopy_Height_{year_tag}_Aligned.tif').resolve()}")
    print(f"  • Total Luas HCS     : {hcs_area_ha:>12,.1f} ha ({n_hcs:,} piksel)")
    print(f"{'='*68}\n")

    return final_output_path


if __name__ == "__main__":
    target_agbd = Path(INPUT_FILE)
    target_lc = Path(INPUT_LC_FILE)
    target_ch = Path(INPUT_CH_FILE)

    if not target_agbd.exists() and (DATA_DIR / target_agbd.name).exists():
        target_agbd = DATA_DIR / target_agbd.name

    if not target_agbd.exists():
        print(f"[ERROR] File input AGBD '{target_agbd}' tidak ditemukan.")
    else:
        year_tag = target_agbd.stem.replace("AGBD_Carbon_", "").replace("AGBD_Prediction_", "")
        
        # Cari file canopy height yang sesuai jika default path belum ada
        if not target_ch.exists():
            candidate_ch_paths = [
                DATA_DIR / "canopy_height" / f"Canopy_Height_RH98_{year_tag}.tif",
                DATA_DIR / "canopy_height" / f"Canopy_Height_Prediction_{year_tag}.tif",
                DATA_DIR / "canopy_height" / f"Canopy_Height_{year_tag}.tif",
                DATA_DIR / f"Canopy_Height_RH98_{year_tag}.tif",
                DATA_DIR / f"Canopy_Height_{year_tag}.tif",
            ]
            for p in candidate_ch_paths:
                if p.exists():
                    target_ch = p
                    break

        final_file = run_stratification(
            agbd_path=target_agbd,
            lc_path=target_lc if target_lc.exists() else None,
            ch_path=target_ch if target_ch.exists() else None,
            output_dir=OUTPUT_DIR,
            cfg=CONFIG,
        )
