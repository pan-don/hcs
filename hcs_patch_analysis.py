"""
hcs_patch_analysis.py
=====================
Analisis Petak HCS sesuai HCSA Toolkit Modul 5.

Pipeline:
  1. Label patch HCS (konektivitas 8-arah)
  2. Erosi penyangga 100 m -> kawasan inti
  3. Hitung atribut patch: luas, luas inti, keliling, Shape Index
  4. Klasifikasi: HPP (inti > 100 ha), MPP (10-100 ha), LPP (< 10 ha)
  5. Analisis konektivitas ke area konservasi dasar
  6. Tandai patch berisiko tinggi (SI > 2.5)
  7. Ekspor raster dan laporan CSV

Penggunaan:
  python hcs_patch_analysis.py
  (Konfigurasi input, output, dan parameter disesuaikan melalui variabel di bawah)

Input  : hcs_mask.tif         -- binary mask dari hcs_stratification.py
         conservation_layer   -- (opsional) shapefile/GeoJSON area konservasi
Output : hcs_patches.tif      -- raster ID patch (int32)
         hcs_core_areas.tif   -- raster kawasan inti setelah erosi 100 m (uint8)
         hcs_patch_priority.tif -- prioritas patch: 3=HPP, 2=MPP, 1=LPP (uint8)
         hcs_patch_report.csv -- tabel atribut lengkap tiap patch

Dependensi: rasterio, numpy, scipy, geopandas, pandas, pyproj
"""

from __future__ import annotations

import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize as rio_rasterize
from scipy.ndimage import binary_erosion, distance_transform_edt, label
from pyproj import CRS

warnings.filterwarnings("ignore", category=FutureWarning)


# ==============================================================================
# VARIABEL KONFIGURASI PENGGUNA (SESUAIKAN DI SINI)
# ==============================================================================

# Path file mask HCS input (hasil dari hcs_stratification.py)
# Contoh: Path("output/stratification/hcs_mask.tif")
# Atau jika memproses subfolder tahun: Path("output/stratification/AGBD_Carbon_2024/hcs_mask.tif")
INPUT_MASK_FILE = Path("output/stratification/hcs_mask.tif")

# Set True jika ingin memproses seluruh hasil batch di folder output/stratification
PROCESS_ALL_YEARS = False
STRAT_DIR = Path("output/stratification")

# Folder output hasil analisis petak
OUTPUT_DIR = Path("output/patch_analysis")

# Layer area konservasi dasar (opsional): path ke Shapefile (.shp) atau GeoJSON
# Contoh: Path("data/conservation_areas.shp") atau biarkan None jika belum ada
CONSERVATION_LAYER = None

# Parameter Patch Analysis HCSA Toolkit Modul 5
BUFFER_INNER_M    = 100.0   # Radius erosi kawasan inti (m)
HPP_CORE_HA       = 100.0   # Luas inti minimum High Priority Patch (ha)
MPP_CORE_HA       = 10.0    # Luas inti minimum Medium Priority Patch (ha)
CORRIDOR_DIST_M   = 200.0   # Jarak maks LPP ke konservasi untuk status koridor (m)
SI_RISK_THRESHOLD = 2.5     # Shape Index ambang batas risiko tinggi (kandidat RBA)
NODATA_IN         = 255     # Nilai NoData raster mask input

# ==============================================================================


CONFIG = {
    "buffer_inner_m":   BUFFER_INNER_M,
    "hpp_core_ha":      HPP_CORE_HA,
    "mpp_core_ha":      MPP_CORE_HA,
    "corridor_dist_m":  CORRIDOR_DIST_M,
    "si_risk_threshold": SI_RISK_THRESHOLD,
    "nodata_in":        NODATA_IN,
}

PRIORITY_LABELS = {0: "NoData", 1: "LPP", 2: "MPP", 3: "HPP"}
PRIORITY_DESC = {
    0: "-",
    1: "Low Priority Patch (inti < 10 ha)",
    2: "Medium Priority Patch (inti 10-100 ha)",
    3: "High Priority Patch (inti > 100 ha)",
}


# -- I/O

def read_raster(path: str | Path) -> tuple[np.ndarray, dict]:
    """Baca GeoTIFF band pertama; NoData diganti 0."""
    with rasterio.open(path) as src:
        data = src.read(1)
        meta = src.meta.copy()
        nd = src.nodata
    if nd is not None:
        data[data == int(nd)] = 0
    return data.astype(np.uint8), meta


def write_raster(
    path: str | Path,
    data: np.ndarray,
    meta: dict,
    dtype: str = "int32",
    nodata: int = 0,
) -> None:
    """Tulis ndarray ke GeoTIFF LZW-compressed."""
    out_meta = meta.copy()
    out_meta.update(dtype=dtype, count=1, nodata=nodata, compress="lzw", driver="GTiff")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **out_meta) as dst:
        dst.write(data.astype(dtype), 1)
    print(f"  [OK] Tersimpan: {path}")


# -- Utilitas spasial

def _pixel_area_m2(meta: dict) -> float:
    t = meta.get("transform")
    return abs(t[0]) * abs(t[4]) if t is not None else 900.0


def _pixel_area_ha(meta: dict) -> float:
    return _pixel_area_m2(meta) / 10_000.0


def _meters_to_pixels(meters: float, meta: dict) -> int:
    return max(1, int(round(meters / abs(meta["transform"][0]))))


def _is_projected(meta: dict) -> bool:
    crs_obj = meta.get("crs")
    if crs_obj is None:
        return False
    try:
        return CRS(crs_obj.to_wkt()).is_projected
    except Exception:
        return False


# -- Fungsi analisis

def label_patches(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Label tiap patch HCS dengan konektivitas 8-arah."""
    struct8 = np.ones((3, 3), dtype=int)
    labeled, n = label(mask.astype(bool), structure=struct8)
    return labeled.astype(np.int32), n


def erode_core_areas(mask: np.ndarray, buffer_pixels: int) -> np.ndarray:
    """
    Erosi mask sejauh buffer_pixels menggunakan structuring element lingkaran.
    Piksel yang tersisa adalah kawasan inti (jarak >= buffer dari tepi patch).
    """
    r = buffer_pixels
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    struct_circle = (x ** 2 + y ** 2 <= r ** 2).astype(int)
    core = binary_erosion(mask.astype(bool), structure=struct_circle, border_value=0)
    return core.astype(np.uint8)


def _estimate_perimeter_pixels(patch: np.ndarray) -> int:
    """Estimasi keliling patch: piksel yang hilang setelah erosi 4-arah."""
    struct4 = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=int)
    eroded = binary_erosion(patch, structure=struct4, border_value=0)
    return int(np.count_nonzero(patch & ~eroded))


def compute_patch_attributes(
    labeled: np.ndarray,
    core_mask: np.ndarray,
    n_patches: int,
    meta: dict,
) -> pd.DataFrame:
    """
    Hitung atribut geometri tiap patch: luas, luas inti, keliling, Shape Index.

    Shape Index SI = P / (2 * sqrt(pi * A)); SI = 1.0 untuk lingkaran sempurna.
    Dihitung secara ter-vektorisasi (vectorized) untuk efisiensi tinggi.
    """
    ha = _pixel_area_ha(meta)
    m2 = _pixel_area_m2(meta)
    px_m = abs(meta["transform"][0])

    # 1. Total area per patch
    area_counts = np.bincount(labeled.ravel(), minlength=n_patches + 1)

    # 2. Core area per patch (hanya piksel di mana core_mask > 0)
    core_pixels = labeled[core_mask.astype(bool)]
    core_counts = np.bincount(core_pixels.ravel(), minlength=n_patches + 1)

    # 3. Perimeter per patch (piksel batas yang bersebelahan dengan label berbeda atau 0)
    pad = np.pad(labeled, 1, mode="constant", constant_values=0)
    center = pad[1:-1, 1:-1]
    up     = pad[:-2, 1:-1]
    down   = pad[2:, 1:-1]
    left   = pad[1:-1, :-2]
    right  = pad[1:-1, 2:]
    is_boundary = (center > 0) & ((center != up) | (center != down) | (center != left) | (center != right))
    perim_counts = np.bincount(center[is_boundary].ravel(), minlength=n_patches + 1)

    pids = np.arange(1, n_patches + 1)
    areas_px = area_counts[1:n_patches + 1]
    cores_px = core_counts[1:n_patches + 1]
    perims_px = perim_counts[1:n_patches + 1]

    areas_ha = np.round(areas_px * ha, 2)
    cores_ha = np.round(cores_px * ha, 2)
    perims_m = np.round(perims_px * px_m, 1)

    areas_m2 = areas_px * m2
    valid_area = areas_m2 > 0
    si = np.zeros(n_patches, dtype=float)
    si[valid_area] = perims_m[valid_area] / (2.0 * np.sqrt(np.pi * areas_m2[valid_area]))
    si = np.round(si, 3)

    is_high_risk = si > CONFIG["si_risk_threshold"]

    df = pd.DataFrame({
        "patch_id": pids,
        "area_ha": areas_ha,
        "core_area_ha": cores_ha,
        "perimeter_m": perims_m,
        "shape_index": si,
        "priority": 0,
        "priority_label": "",
        "connectivity_status": "isolated",
        "is_high_risk": is_high_risk,
        "notes": "",
    })

    return df


def classify_priority(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Klasifikasi HPP/MPP/LPP berdasarkan luas kawasan inti."""
    conditions = [
        df["core_area_ha"] > cfg["hpp_core_ha"],
        (df["core_area_ha"] >= cfg["mpp_core_ha"]) & (df["core_area_ha"] <= cfg["hpp_core_ha"]),
    ]
    df["priority"] = np.select(conditions, [3, 2], default=1)
    df["priority_label"] = df["priority"].map(PRIORITY_LABELS)
    return df


def analyze_connectivity(
    df: pd.DataFrame,
    labeled: np.ndarray,
    meta: dict,
    conservation_layer: str | Path | None,
    cfg: dict,
) -> pd.DataFrame:
    """
    Analisis konektivitas patch ke area konservasi dasar (Modul 5).

    Aturan:
    - HPP -> selalu 'protect (HPP)'
    - MPP bersinggungan langsung dengan HPP/konservasi -> 'protect (MPP adjacent)'
    - LPP jarak <= corridor_dist_m ke konservasi -> 'corridor'
    - Sisanya -> 'isolated'
    """
    if conservation_layer is None:
        print("      [INFO] Layer konservasi tidak disediakan; semua patch = 'isolated'")
        df["connectivity_status"] = "isolated"
        return df

    print(f"      Membaca layer konservasi: {conservation_layer}")
    cons_gdf = gpd.read_file(conservation_layer)
    cons_mask = rio_rasterize(
        [(geom, 1) for geom in cons_gdf.geometry if geom is not None],
        out_shape=(meta["height"], meta["width"]),
        transform=meta["transform"],
        fill=0,
        dtype=np.uint8,
    )

    hpp_ids = df.loc[df["priority"] == 3, "patch_id"].tolist()
    hpp_mask = np.isin(labeled, hpp_ids).astype(np.uint8)
    anchor_mask = np.clip(cons_mask + hpp_mask, 0, 1)

    px_m = abs(meta["transform"][0])
    dist_m = distance_transform_edt(anchor_mask == 0) * px_m

    for idx, row in df.iterrows():
        patch_px = labeled == row["patch_id"]
        if row["priority"] == 3:
            df.at[idx, "connectivity_status"] = "protect (HPP)"
            continue

        min_dist = float(dist_m[patch_px].min()) if patch_px.any() else np.inf

        if row["priority"] == 2:
            status = "protect (MPP adjacent)" if min_dist < px_m else "assess"
        else:
            status = "corridor" if min_dist <= cfg["corridor_dist_m"] else "isolated"
        df.at[idx, "connectivity_status"] = status

    return df


def flag_high_risk(df: pd.DataFrame) -> pd.DataFrame:
    """Tandai patch terisolasi dengan SI tinggi sebagai kandidat RBA lapangan."""
    mask = df["is_high_risk"] & (df["connectivity_status"] == "isolated")
    df.loc[mask, "notes"] = "Kandidat RBA lapangan (SI tinggi, terisolasi)"
    return df


def render_priority_raster(
    labeled: np.ndarray,
    core_mask: np.ndarray,
    df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray]:
    """Render raster prioritas patch dan raster kawasan inti."""
    max_label = int(labeled.max())
    prio_lookup = np.zeros(max_label + 1, dtype=np.uint8)
    prio_lookup[df["patch_id"].values] = df["priority"].values.astype(np.uint8)
    priority_raster = prio_lookup[labeled]
    core_raster = (core_mask & (labeled > 0)).astype(np.uint8)
    return priority_raster, core_raster


# -- Reporting

def _print_priority_summary(df: pd.DataFrame, ha: float) -> None:
    print(f"      {'Prioritas':<30} {'Jumlah':>8} {'Total Luas (ha)':>15} {'Luas Inti (ha)':>15}")
    print(f"      {'-'*70}")
    for prio in [3, 2, 1]:
        sub = df[df["priority"] == prio]
        print(f"      {PRIORITY_LABELS[prio]} ({PRIORITY_DESC[prio][:28]:<28}) "
              f"{len(sub):>8,} {sub['area_ha'].sum():>15,.1f} {sub['core_area_ha'].sum():>15,.1f}")


def _print_final_summary(df: pd.DataFrame, total_hcs_px: int, ha: float) -> None:
    total_ha = total_hcs_px * ha
    protect  = df[df["connectivity_status"].str.startswith("protect")]["area_ha"].sum()
    corridor = df[df["connectivity_status"] == "corridor"]["area_ha"].sum()
    isolated = df[df["connectivity_status"] == "isolated"]["area_ha"].sum()
    n_risk   = int(df["is_high_risk"].sum())

    print(f"\n{'='*62}")
    print(f"  RINGKASAN AKHIR PATCH ANALYSIS")
    print(f"{'='*62}")
    print(f"  Total luas HCS           : {total_ha:>12,.1f} ha")
    print(f"  Dilindungi (HPP+MPP adj) : {protect:>12,.1f} ha")
    print(f"  Zona koridor (<= 200 m)  : {corridor:>12,.1f} ha")
    print(f"  Terisolasi               : {isolated:>12,.1f} ha")
    print(f"  Patch berisiko tinggi    : {n_risk:>12} patch (kandidat RBA)")
    print(f"{'='*62}\n")


# -- Pipeline utama

def run_patch_analysis(
    mask_path: str | Path,
    output_dir: str | Path,
    conservation_layer: str | Path | None = None,
    cfg: dict = CONFIG,
) -> dict[str, Path]:
    """
    Jalankan pipeline patch analysis HCSA Modul 5 lengkap.

    Returns dict { 'patches', 'core_areas', 'priority', 'report' } -> Path.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 62)
    print("  PATCH ANALYSIS HCS  (HCSA Toolkit Modul 5)")
    print("=" * 62)

    print(f"\n[1/7] Membaca HCS mask: {mask_path}")
    mask, meta = read_raster(mask_path)
    ha = _pixel_area_ha(meta)

    if not _is_projected(meta):
        print("  [PERINGATAN] CRS geografis terdeteksi. "
              "Reproject ke sistem proyeksi setara-luas untuk akurasi luas dan buffer.")

    n_hcs = int(np.count_nonzero(mask))
    print(f"      Piksel HCS : {n_hcs:,} ({n_hcs * ha:,.1f} ha)")

    print(f"\n[2/7] Labeling patch (konektivitas 8-arah)")
    labeled, n_patches = label_patches(mask)
    patches_path = out / "hcs_patches.tif"
    write_raster(patches_path, labeled, meta, dtype="int32", nodata=0)
    print(f"      Patch teridentifikasi: {n_patches:,}")

    buf_px = _meters_to_pixels(cfg["buffer_inner_m"], meta)
    print(f"\n[3/7] Erosi penyangga {cfg['buffer_inner_m']:.0f} m ({buf_px} piksel) -> kawasan inti")
    core_mask = erode_core_areas(mask, buf_px)
    core_path = out / "hcs_core_areas.tif"
    write_raster(core_path, core_mask, meta, dtype="uint8", nodata=255)
    n_core = int(np.count_nonzero(core_mask))
    print(f"      Luas kawasan inti : {n_core:,} piksel ({n_core * ha:,.1f} ha)")

    print(f"\n[4/7] Menghitung atribut patch")
    df = compute_patch_attributes(labeled, core_mask, n_patches, meta)

    print(f"\n[5/7] Klasifikasi prioritas HPP/MPP/LPP")
    df = classify_priority(df, cfg)
    _print_priority_summary(df, ha)

    print(f"\n[6/7] Analisis konektivitas (koridor <= {cfg['corridor_dist_m']:.0f} m)")
    df = analyze_connectivity(df, labeled, meta, conservation_layer, cfg)
    df = flag_high_risk(df)

    print(f"\n[7/7] Menyimpan output")
    priority_raster, _ = render_priority_raster(labeled, core_mask, df)
    priority_path = out / "hcs_patch_priority.tif"
    write_raster(priority_path, priority_raster, meta, dtype="uint8", nodata=0)

    report_path = out / "hcs_patch_report.csv"
    df.to_csv(report_path, index=False, encoding="utf-8")
    print(f"  [OK] Laporan: {report_path}  ({len(df)} patch)")

    _print_final_summary(df, n_hcs, ha)

    return {
        "patches":    patches_path,
        "core_areas": core_path,
        "priority":   priority_path,
        "report":     report_path,
    }


if __name__ == "__main__":
    cfg = {
        "buffer_inner_m":   BUFFER_INNER_M,
        "hpp_core_ha":      HPP_CORE_HA,
        "mpp_core_ha":      MPP_CORE_HA,
        "corridor_dist_m":  CORRIDOR_DIST_M,
        "si_risk_threshold": SI_RISK_THRESHOLD,
        "nodata_in":        NODATA_IN,
    }

    if PROCESS_ALL_YEARS:
        mask_files = sorted(list(STRAT_DIR.glob("**/hcs_mask.tif")))
        if not mask_files:
            print(f"[ERROR] Tidak ditemukan file 'hcs_mask.tif' di dalam subdirektori '{STRAT_DIR}'")
        else:
            print(f"[INFO] Ditemukan {len(mask_files)} mask HCS. Memproses analisis petak secara batch...")
            for idx, mask_file in enumerate(mask_files, 1):
                parent_name = mask_file.parent.name
                sub_out = OUTPUT_DIR / parent_name
                print(f"\n>>> [{idx}/{len(mask_files)}] Patch Analysis: {mask_file} -> {sub_out}")
                run_patch_analysis(
                    mask_path=mask_file,
                    output_dir=sub_out,
                    conservation_layer=CONSERVATION_LAYER,
                    cfg=cfg,
                )
            print("\n[SELESAI] Seluruh analisis petak berhasil dijalankan!")
    else:
        target_mask = Path(INPUT_MASK_FILE)
        if not target_mask.exists():
            print(f"[ERROR] File mask input '{target_mask}' tidak ditemukan.")
            print("Tips: Jalankan 'python hcs_stratification.py' terlebih dahulu untuk menghasilkan 'hcs_mask.tif',")
            print("atau sesuaikan variabel INPUT_MASK_FILE di atas.")
        else:
            outputs = run_patch_analysis(
                mask_path=target_mask,
                output_dir=OUTPUT_DIR,
                conservation_layer=CONSERVATION_LAYER,
                cfg=cfg,
            )
            print("Output files:")
            for k, v in outputs.items():
                print(f"  {k:<14}: {v}")
