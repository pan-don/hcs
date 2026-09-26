from __future__ import annotations

import os
import re
import warnings
import matplotlib
from pathlib import Path
import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize as rio_rasterize, sieve as rio_sieve
from scipy.ndimage import binary_erosion, distance_transform_edt, label
from pyproj import CRS

matplotlib.use('Agg')
os.environ["GDAL_DRIVER_PATH"] = "" 
warnings.filterwarnings("ignore", category=FutureWarning)


# ------------------------------------------------------------------------------
# Konvigurasi
# ------------------------------------------------------------------------------

PROCESS_ALL_YEARS = True # Set True untuk memproses semua tahun
STRAT_DIR = Path("output/stratification")
INPUT_STRAT_FILE = Path("output/stratification/HCS_Stratification_2025_Final.tif") # Path file raster stratifikasi HCS input
OUTPUT_DIR = Path("output/patch_analysis")
CONSERVATION_LAYER = Path("data/vector/protected_area.shp")
ADMIN_BOUNDARY = Path("data/vector/bogor_administrasi_kabkota.shp")

# Parameter Analisis Petak HCSA Toolkit Modul 5
BUFFER_INNER_M    = 100.0   # Radius erosi kawasan inti (m)
HPP_CORE_HA       = 100.0   # Luas inti minimum High Priority Patch (ha)
MPP_CORE_HA       = 10.0    # Luas inti minimum Medium Priority Patch (ha)
CORRIDOR_DIST_M   = 200.0   # Jarak maks LPP ke konservasi untuk status koridor (m)
SI_RISK_THRESHOLD = 2.5     # Ambang batas Shape Index patch berisiko tinggi (kandidat RBA)
NODATA_IN         = 255     # Nilai NoData raster input

# Parameter Standar HCSA Modul 5: MMU & Penutupan Celah Kanopi
MMU_MIN_PATCH_HA   = 0.5    # Ambang batas MMU petak HCS minimum (ha)
MAX_HOLE_FILL_HA   = 0.5    # Ambang batas penutupan celah kanopi internal non-hutan (ha)
CLEAN_ZONATION_MMU = 6      # Ambang batas filter MMU pembersihan derau peta zonasi akhir (piksel)

# Opsi Kebijakan HCSA: Drop LPP Terisolasi
DROP_ISOLATED_LPP = True    # True: LPP terisolasi normal dialokasikan untuk pembangunan (HCSA Step 6)

CONFIG = {
    "buffer_inner_m":     BUFFER_INNER_M,
    "hpp_core_ha":        HPP_CORE_HA,
    "mpp_core_ha":        MPP_CORE_HA,
    "corridor_dist_m":    CORRIDOR_DIST_M,
    "si_risk_threshold":  SI_RISK_THRESHOLD,
    "nodata_in":          NODATA_IN,
    "drop_isolated_lpp":  DROP_ISOLATED_LPP,
    "mmu_min_patch_ha":   MMU_MIN_PATCH_HA,
    "max_hole_fill_ha":   MAX_HOLE_FILL_HA,
    "clean_zonation_mmu": CLEAN_ZONATION_MMU,
}

PRIORITY_LABELS = {0: "NoData", 1: "LPP", 2: "MPP", 3: "HPP"}
PRIORITY_DESC = {
    0: "-",
    1: "Low Priority Patch",
    2: "Medium Priority Patch",
    3: "High Priority Patch",
}

# Skema Klasifikasi Zonasi Akhir Keputusan HCSA
HCSA_DECISION_CLASSES = {
    1: {
        "name": "HCS Konservasi (Conserve)",
        "desc": "HPP, MPP Terhubung, & Kawasan Lindung Resmi - Wajib Dilindungi",
        "color": "#1b5e20",  # Hijau tua
        "rgba": (27, 94, 32, 255),
    },
    2: {
        "name": "HCS Koridor (Corridor)",
        "desc": "LPP dalam jarak <= 200 m dari Kawasan Lindung - Konektivitas Ekologis",
        "color": "#7cb342",  # Hijau muda / lime
        "rgba": (124, 179, 66, 255),
    },
    3: {
        "name": "HCS Kaji Lapangan / Pre-RBA (Assess)",
        "desc": "MPP Terisolasi (inti 10-100 ha) & LPP Terisolasi Risiko Tinggi (SI > 2.5)",
        "color": "#fb8c00",  # Amber / Oranye
        "rgba": (251, 140, 0, 255),
    },
    4: {
        "name": "Indikasi Layak Dikembangkan (Developable)",
        "desc": "Non-HCS (Lahan Terbuka & Belukar Muda) + LPP Terisolasi yang Di-drop",
        "color": "#ffee58",  # Kuning lembut
        "rgba": (255, 238, 88, 255),
    },
    5: {
        "name": "Non-Vegetasi / Non-Target",
        "desc": "Badan Air, Permukiman, dan Lahan Terbangun",
        "color": "#b0bec5",  # Abu-abu kebiruan
        "rgba": (176, 190, 197, 255),
    },
}

# ------------------------------------------------------------------------------
# FUNGSI I/O & ALIGNMENT
# ------------------------------------------------------------------------------

def read_raster(path: str | Path) -> tuple[np.ndarray, dict]:
    """Baca GeoTIFF band pertama; NoData diganti 0."""
    with rasterio.open(path) as src:
        data = src.read(1)
        meta = src.meta.copy()
        nd = src.nodata if src.nodata is not None else NODATA_IN
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
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    out_meta = meta.copy()
    out_meta.update(dtype=dtype, count=1, nodata=nodata, compress="lzw", driver="GTiff")
    with rasterio.open(p, "w", **out_meta) as dst:
        dst.write(data.astype(dtype), 1)


def _meters_to_pixels(meters: float, meta: dict) -> int:
    px_size = abs(meta["transform"][0])
    return max(1, int(round(meters / px_size)))


def _pixel_area_ha(meta: dict) -> float:
    t = meta["transform"]
    return (abs(t[0]) * abs(t[4])) / 10_000.0


def _pixel_area_m2(meta: dict) -> float:
    t = meta["transform"]
    return abs(t[0]) * abs(t[4])


def _is_projected(meta: dict) -> bool:
    try:
        return CRS.from_user_input(meta["crs"]).is_projected
    except Exception:
        return False


# ------------------------------------------------------------------------------
# Analisis Morfologi & Penyaringan Derau Petak HCS
# ------------------------------------------------------------------------------

def sieve_patch_mask(
    mask: np.ndarray,
    mmu_ha: float,
    meta: dict,
) -> tuple[np.ndarray, int]:
    """
    Saring masker HCS sebelum analisis petak sesuai standar HCSA Toolkit Modul 5 (MMU Filter).
    Fragmen vegetasi terisolasi di bawah MMU (default 0.5 ha = ~6 piksel pada 30 m) dieliminasi
    sehingga tidak menjadi artefak petak atau salah diklasifikasikan sebagai koridor.
    Mengembalikan (sieved_mask, n_removed_patches).
    """
    ha_px = _pixel_area_ha(meta)
    min_pixels = max(2, int(np.ceil(mmu_ha / ha_px)))
    struct8 = np.ones((3, 3), dtype=int)
    labeled, n_initial = label(mask.astype(bool), structure=struct8)
    if n_initial == 0:
        return mask.copy(), 0

    counts = np.bincount(labeled.ravel())
    keep_mask = counts >= min_pixels
    keep_mask[0] = False
    sieved = keep_mask[labeled].astype(np.uint8)
    n_removed = int(np.count_nonzero((counts[1:] < min_pixels) & (counts[1:] > 0)))
    return sieved, n_removed


def fill_internal_canopy_gaps(
    mask: np.ndarray,
    max_hole_ha: float,
    meta: dict,
) -> tuple[np.ndarray, int]:
    """
    Tutup lubang kanopi non-hutan internal (in-forest canopy gaps / small enclaves)
    yang terkurung di dalam petak hutan HCS sesuai kaidah HCSA Modul 5.
    Hanya lubang tertutup dengan ukuran <= max_hole_ha (default 0.5 ha) yang diisi.
    Mengembalikan (filled_mask, n_filled_pixels).
    """
    ha_px = _pixel_area_ha(meta)
    max_pixels = int(np.ceil(max_hole_ha / ha_px))
    struct8 = np.ones((3, 3), dtype=int)
    holes = (mask == 0)
    lab_h, n_h = label(holes, structure=struct8)
    if n_h == 0:
        return mask.copy(), 0

    cnts_h = np.bincount(lab_h.ravel())
    # Identifikasi piksel latar belakang tepi (background yang menyentuh margin citra)
    edge_px = np.concatenate([lab_h[0, :], lab_h[-1, :], lab_h[:, 0], lab_h[:, -1]])
    bg_labels = set(np.unique(edge_px))

    small_hole_ids = [lbl for lbl in range(1, n_h + 1) if lbl not in bg_labels and cnts_h[lbl] <= max_pixels]
    if not small_hole_ids:
        return mask.copy(), 0

    fill_mask = np.isin(lab_h, small_hole_ids)
    filled = mask.copy()
    filled[fill_mask] = 1
    return filled, int(np.count_nonzero(fill_mask))


def clean_landscape_zonation(
    decision_raster: np.ndarray,
    mmu_pixels: int = 6,
    nodata: int = 255,
) -> np.ndarray:
    """
    Pembersihan derau spasial (salt-and-pepper noise 1-3 piksel) pada peta keputusan zonasi akhir.
    Menggunakan algoritma GDAL/Rasterio Sieve teroptimasi untuk menggabungkan pulau-pulau piksel
    terisolasi di bawah ukuran MMU (< mmu_pixels) ke dalam kelas poligon tetangga terbesarnya.
    """
    valid_mask = decision_raster != nodata
    cleaned = rio_sieve(decision_raster, size=mmu_pixels, connectivity=8)
    cleaned[~valid_mask] = nodata
    return cleaned


def label_patches(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Identifikasi petak HCS terhubung (8-arah)."""
    struct8 = np.ones((3, 3), dtype=int)
    labeled, n = label(mask.astype(bool), structure=struct8)
    return labeled.astype(np.int32), int(n)


def erode_core_areas(mask: np.ndarray, buffer_px: int) -> np.ndarray:
    """Erosi morfologis untuk mengisolasi kawasan inti (Core Area)."""
    r = buffer_px
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    struct_circle = (x ** 2 + y ** 2 <= r ** 2).astype(int)
    core = binary_erosion(mask.astype(bool), structure=struct_circle, border_value=0)
    return core.astype(np.uint8)


def compute_patch_attributes(
    labeled: np.ndarray,
    core_mask: np.ndarray,
    n_patches: int,
    meta: dict,
) -> pd.DataFrame:
    """Hitung metrik geometri patch (vektorisasi penuh)."""
    ha = _pixel_area_ha(meta)
    m2 = _pixel_area_m2(meta)
    px_m = abs(meta["transform"][0])

    area_counts = np.bincount(labeled.ravel(), minlength=n_patches + 1)
    core_pixels = labeled[core_mask.astype(bool)]
    core_counts = np.bincount(core_pixels.ravel(), minlength=n_patches + 1)

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
    Analisis konektivitas patch ke area konservasi dasar & HPP anchor (Modul 5).
    """
    if conservation_layer is None or not Path(conservation_layer).exists():
        print("      [INFO] Layer konservasi eksternal tidak ditemukan; mengandalkan anchor HPP.")
        cons_mask = np.zeros((meta["height"], meta["width"]), dtype=np.uint8)
    else:
        print(f"      Membaca layer konservasi: {conservation_layer}")
        cons_gdf = gpd.read_file(conservation_layer)
        if cons_gdf.crs != meta["crs"]:
            cons_gdf = cons_gdf.to_crs(meta["crs"])
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


# ------------------------------------------------------------------------------
# Decision Tree HCSA & Kelayakan Pengembangan
# ------------------------------------------------------------------------------

def apply_hcsa_decision_tree(df: pd.DataFrame, drop_isolated_lpp: bool = True) -> pd.DataFrame:
    """
    Eksekusi Pohon Keputusan HCSA Toolkit Modul 5 (Langkah 1 - 6):
      - HPP (inti > 100 ha) -> 'CONSERVE' (Lindungi)
      - MPP (inti 10-100 ha):
          * Adjacent / terhubung -> 'CONSERVE' (Lindungi)
          * Terisolasi -> 'ASSESS' (Kaji Lapangan / Pre-RBA) -> TIDAK di-drop langsung!
      - LPP (inti < 10 ha):
          * Dalam zona koridor <= 200 m -> 'CORRIDOR' (Konektivitas Ekologis)
          * Terisolasi (> 200 m):
              - Jika Shape Index tinggi (is_high_risk) -> 'ASSESS' (Kaji RBA Lapangan)
              - Jika normal -> 'DEVELOP' (DI-DROP dari HCS Konservasi -> Indikasi Layak Dikembangkan)
    """
    decisions = []
    actions = []
    dropped = []

    for _, row in df.iterrows():
        prio = row["priority"]
        conn = str(row["connectivity_status"])
        high_risk = bool(row.get("is_high_risk", False))

        if prio == 3:
            dec = "CONSERVE"
            act = "Lindungi: HPP dengan kawasan inti > 100 ha"
            is_drop = False
        elif prio == 2:
            if "protect" in conn:
                dec = "CONSERVE"
                act = "Lindungi: MPP terhubung langsung ke kawasan inti/lindung"
                is_drop = False
            else:
                dec = "ASSESS"
                act = "Kaji Lapangan RBA: MPP terisolasi (inti 10-100 ha memerlukan penilaian keanekaragaman hayati)"
                is_drop = False
        else:  # LPP
            if conn == "corridor":
                dec = "CORRIDOR"
                act = "Konservasi Koridor: LPP berjarak <= 200 m (stepping stone konektivitas ekologis)"
                is_drop = False
            else:  # isolated
                if high_risk:
                    dec = "ASSESS"
                    act = "Kaji Lapangan RBA: LPP terisolasi risiko tinggi (Shape Index > 2.5)"
                    is_drop = False
                elif drop_isolated_lpp:
                    dec = "DEVELOP"
                    act = "Dapat Dikembangkan (Di-drop): LPP terisolasi inti < 10 ha tidak memenuhi kelayakan ekologis"
                    is_drop = True
                else:
                    dec = "ASSESS"
                    act = "Kaji Lapangan: LPP terisolasi"
                    is_drop = False

        decisions.append(dec)
        actions.append(act)
        dropped.append(is_drop)

    df["final_decision"] = decisions
    df["action_recommendation"] = actions
    df["is_dropped_hcs"] = dropped
    return df


def generate_hcsa_land_suitability_map(
    labeled: np.ndarray,
    df: pd.DataFrame,
    strat_raster_path: str | Path | None,
    conservation_layer: str | Path | None,
    meta: dict,
    output_tif: str | Path,
    clean_mmu_pixels: int = 6,
) -> tuple[np.ndarray, pd.DataFrame]:
    """
    Hasilkan Raster Peta Zonasi Akhir Keputusan HCSA & Kelayakan Pembangunan.
    Menggabungkan seluruh lanskap (HCS + Non-HCS + Kawasan Lindung):
      1: HCS Konservasi (Conserve)
      2: HCS Koridor (Corridor)
      3: HCS Kaji Lapangan / Pre-RBA (Assess)
      4: Indikasi Layak Dikembangkan (Developable)
      5: Non-Vegetasi / Non-Target (Air & Bangunan)
    """
    ha_px = _pixel_area_ha(meta)
    p_tif = Path(output_tif)
    p_tif.parent.mkdir(parents=True, exist_ok=True)

    # 1. Lookup array keputusan patch
    dec_to_code = {
        "CONSERVE": 1,
        "CORRIDOR": 2,
        "ASSESS": 3,
        "DEVELOP": 4,
    }
    max_label = int(labeled.max())
    lut = np.zeros(max_label + 1, dtype=np.uint8)
    for _, r in df.iterrows():
        lut[int(r["patch_id"])] = dec_to_code.get(r["final_decision"], 4)
    patch_dec = lut[labeled]

    # 2. Baca raster stratifikasi dasar jika ada
    if strat_raster_path and Path(strat_raster_path).exists():
        with rasterio.open(strat_raster_path) as src:
            strat = src.read(1)
        decision_raster = np.full(strat.shape, 255, dtype=np.uint8)
        
        # Kelas non-vegetasi stratifikasi (0) -> 5
        decision_raster[strat == 0] = 5
        # Kelas non-HCS stratifikasi (1: Open Land, 2: Scrub) -> 4 (Developable)
        decision_raster[(strat == 1) | (strat == 2)] = 4

        # HCS forest pixels (3..6)
        hcs_forest = (strat >= 3) & (strat <= 6)
        valid_p = hcs_forest & (patch_dec > 0)
        decision_raster[valid_p] = patch_dec[valid_p]
        # Fragmen HCS sieved di luar patch -> 4 (Developable)
        sieved_hcs = hcs_forest & (patch_dec == 0)
        decision_raster[sieved_hcs] = 4
    else:
        # Jika raster stratifikasi tidak tersedia, gunakan patch_dec langsung
        decision_raster = np.full(labeled.shape, 255, dtype=np.uint8)
        decision_raster[labeled == 0] = 4
        decision_raster[labeled > 0] = patch_dec[labeled > 0]

    # 3. Overlay Kawasan Lindung Resmi (Protected Area)
    if conservation_layer and Path(conservation_layer).exists():
        cons_gdf = gpd.read_file(conservation_layer)
        if cons_gdf.crs != meta["crs"]:
            cons_gdf = cons_gdf.to_crs(meta["crs"])
        pa_mask = rio_rasterize(
            [(geom, 1) for geom in cons_gdf.geometry if geom is not None],
            out_shape=(meta["height"], meta["width"]),
            transform=meta["transform"],
            fill=0,
            dtype=np.uint8,
        )
        # Area formal lindung tidak boleh dikembangkan -> Kelas 1 (Conserve)
        decision_raster[(pa_mask == 1) & (decision_raster != 255)] = 1

    # 3b. Pembersihan derau spasial zonasi lanskap (Sieve filtering piksel terisolasi < MMU)
    if clean_mmu_pixels > 1:
        decision_raster = clean_landscape_zonation(decision_raster, mmu_pixels=clean_mmu_pixels)

    # 4. Tulis GeoTIFF dengan ColorMap resmi
    out_meta = meta.copy()
    out_meta.update(dtype="uint8", count=1, nodata=255, compress="lzw", driver="GTiff")
    with rasterio.open(p_tif, "w", **out_meta) as dst:
        dst.write(decision_raster, 1)
        colormap = {code: info["rgba"] for code, info in HCSA_DECISION_CLASSES.items()}
        dst.write_colormap(1, colormap)

    # 4b. Tulis file style QGIS (.qml) dan ArcGIS (.clr) agar otomatis terwarnai saat dibuka
    clr_lines = [f"{code} {info['rgba'][0]} {info['rgba'][1]} {info['rgba'][2]} 255 {info['name']}"
                 for code, info in HCSA_DECISION_CLASSES.items()]
    p_tif.with_suffix(".clr").write_text("\n".join(clr_lines) + "\n", encoding="utf-8")

    qml_entries = "\n".join([
        f'        <paletteEntry value="{code}" color="{info["color"]}" alpha="255" label="{code}: {info["name"]}"/>'
        for code, info in HCSA_DECISION_CLASSES.items()
    ])
    qml_text = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28.0" styleCategories="AllStyleCategories">
  <pipe>
    <rasterrenderer type="paletted" band="1" opacity="1">
      <rasterproperties>
        <nodata>
          <values>
            <value>255</value>
          </values>
        </nodata>
      </rasterproperties>
      <colorPalette>
{qml_entries}
      </colorPalette>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
"""
    p_tif.with_suffix(".qml").write_text(qml_text, encoding="utf-8")

    # 5. Hitung statistik zonasi
    valid_pixels = decision_raster[decision_raster != 255]
    total_area_ha = len(valid_pixels) * ha_px

    stats = []
    for code, info in HCSA_DECISION_CLASSES.items():
        n_px = int(np.count_nonzero(decision_raster == code))
        ha_val = n_px * ha_px
        pct = (ha_val / total_area_ha * 100.0) if total_area_ha > 0 else 0.0
        stats.append({
            "kode": code,
            "zona_hcsa": info["name"],
            "deskripsi": info["desc"],
            "piksel": n_px,
            "luas_ha": round(ha_val, 1),
            "persentase_pct": round(pct, 2),
        })

    summary_df = pd.DataFrame(stats)
    return decision_raster, summary_df


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


# ------------------------------------------------------------------------------
# Visualisasi Tematik Kartografis & Dashboard
# ------------------------------------------------------------------------------

def plot_hcsa_land_suitability_map(
    decision_raster: np.ndarray,
    summary_df: pd.DataFrame,
    output_png: str | Path,
    year_tag: str = "",
    meta: dict | None = None,
    admin_boundary: str | Path | None = None,
) -> None:
    """
    Peta Tematik Kartografis Standar Resmi: Zonasi Keputusan HCSA & Kelayakan Pembangunan.
    - Judul di fig.suptitle (tidak overlay ke peta)
    - Area di luar batas administrasi = putih (masking raster)
    - Bar chart vertikal
    - Sidebar (legenda + chart) tinggi setara dengan peta
    - Tanpa panel rekomendasi
    """
    import warnings
    warnings.filterwarnings("ignore")

    p_out = Path(output_png)
    p_out.parent.mkdir(parents=True, exist_ok=True)

    # 1. Load & reproyeksi batas administrasi
    admin_gdf = None
    if admin_boundary and Path(admin_boundary).exists():
        admin_gdf = gpd.read_file(admin_boundary)
        if meta is not None and admin_gdf.crs != meta.get("crs"):
            admin_gdf = admin_gdf.to_crs(meta["crs"])

    # 2. Masking: piksel di luar batas admin → NaN (putih)
    display_raster = decision_raster.astype(float)
    if admin_gdf is not None and meta is not None and "transform" in meta:
        from rasterio.features import geometry_mask
        from shapely.geometry import mapping
        geoms = [mapping(geom) for geom in admin_gdf.geometry]
        outside_mask = geometry_mask(
            geoms,
            transform=meta["transform"],
            invert=False,                # True = di dalam, False = di luar
            out_shape=(meta["height"], meta["width"])
        )
        display_raster = display_raster.astype(float)
        display_raster[outside_mask] = np.nan   # di luar → NaN → putih

    masked_data = np.ma.masked_where(
        (display_raster == 255) | np.isnan(display_raster), display_raster
    )

    # 3. Colormap
    cmap_colors = ["#ffffff"] * 256
    for code, info in HCSA_DECISION_CLASSES.items():
        cmap_colors[code] = info["color"]
    custom_cmap = mcolors.ListedColormap(cmap_colors)
    custom_cmap.set_bad(color="#ffffff")   # masked / di luar admin = putih

    # 4. Setup Figure
    # Layout: peta kiri (lebar ~58%), sidebar kanan (lebar ~34%)
    fig_w, fig_h = 22.0, 8.8
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=300, facecolor="#ffffff")
    ax_map = fig.add_axes([0.045, 0.06, 0.58, 0.86])

    # 5. Peta Spasial Utama
    if meta is not None and "transform" in meta:
        bounds = rasterio.transform.array_bounds(meta["height"], meta["width"], meta["transform"])
        x_min_r, y_min_r, x_max_r, y_max_r = bounds
        extent = [x_min_r, x_max_r, y_min_r, y_max_r]

        ax_map.imshow(
            masked_data, cmap=custom_cmap, vmin=0, vmax=255,
            interpolation="nearest", extent=extent, origin="upper"
        )
        if admin_gdf is not None:
            admin_gdf.boundary.plot(
                ax=ax_map, color="#1a1a1a", linewidth=1.8, linestyle="-", zorder=5
            )
            adm_b = admin_gdf.total_bounds
            pad_x = (adm_b[2] - adm_b[0]) * 0.012
            pad_y = (adm_b[3] - adm_b[1]) * 0.012
            ax_map.set_xlim(adm_b[0] - pad_x, adm_b[2] + pad_x)
            ax_map.set_ylim(adm_b[1] - pad_y, adm_b[3] + pad_y)
        else:
            ax_map.set_xlim(extent[0], extent[1])
            ax_map.set_ylim(extent[2], extent[3])

        ax_map.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x/1000:.0f}"))
        ax_map.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y/1000:.1f}"))
        ax_map.set_xlabel("Easting (km, UTM Zone 48S)", fontsize=8, color="#546e7a", labelpad=3)
        ax_map.set_ylabel("Northing (km, UTM Zone 48S)", fontsize=8, color="#546e7a", labelpad=3)
        ax_map.tick_params(labelsize=7.5, colors="#455a64", direction="out", length=3, width=0.7)
        ax_map.grid(True, linestyle=":", alpha=0.25, color="#90a4ae", linewidth=0.6)
        ax_map.set_facecolor("#ffffff")
        for spine in ax_map.spines.values():
            spine.set_edgecolor("#37474f")
            spine.set_linewidth(1.2)
    else:
        ax_map.imshow(masked_data, cmap=custom_cmap, vmin=0, vmax=255, interpolation="nearest")
        ax_map.set_axis_off()

    fig.canvas.draw()
    map_pos = ax_map.get_position()
    map_y0 = map_pos.y0
    map_y1 = map_pos.y1
    map_h = map_y1 - map_y0

    # 6. Judul Utama Visualisasi
    fig.suptitle(
        f"PETA KEPUTUSAN ZONASI HCSA & KELAYAKAN PEMBANGUNAN LANSKAP {year_tag}\n"
        f"Kabupaten Bogor, Provinsi Jawa Barat  ·  Standar HCSA Toolkit Modul 5: Forest Patch Analysis",
        fontsize=12.0, fontweight="bold", color="#1a237e",
        x=0.5, y=map_y1 + 0.018, ha="center", va="bottom"
    )
    side_x0 = map_pos.x1 + 0.045
    side_w = 0.975 - side_x0
    leg_h = map_h * 0.27
    gap = map_h * 0.07
    stats_h = map_h - leg_h - gap
    leg_y0 = map_y1 - leg_h
    stats_y0 = map_y0
    ax_leg = fig.add_axes([side_x0, leg_y0, side_w, leg_h])
    ax_stats = fig.add_axes([side_x0, stats_y0, side_w, stats_h])

    # 7. Legenda Keputusan Zonasi
    ax_leg.set_axis_off()
    ax_leg.set_facecolor("#ffffff")

    ax_leg.text(0.5, 0.98, "LEGENDA KEPUTUSAN ZONASI", fontsize=8.0,
                fontweight="bold", color="#1b5e20", va="top", ha="center",
                transform=ax_leg.transAxes)
    ax_leg.axhline(0.88, color="#c8e6c9", linewidth=1.2, xmin=0.02, xmax=0.98)

    entries = list(HCSA_DECISION_CLASSES.items())
    n = len(entries)
    y_start = 0.78
    step = y_start / n

    for rank, (code, info) in enumerate(entries):
        y_top = y_start - rank * step
        ax_leg.add_patch(mpatches.Rectangle(
            (0.015, y_top - 0.11), 0.042, 0.11,
            facecolor=info["color"], edgecolor="#37474f", linewidth=0.7,
            transform=ax_leg.transAxes, clip_on=False
        ))
        ax_leg.text(0.075, y_top - 0.01, info["name"], fontsize=6.8,
                    fontweight="bold", color="#212121", va="top",
                    transform=ax_leg.transAxes)
        desc = info["desc"]
        if len(desc) > 60:
            mid = desc.rfind(" ", 0, 60)
            mid = mid if mid > 0 else 60
            desc = desc[:mid] + "\n" + desc[mid+1:]
        ax_leg.text(0.075, y_top - 0.058, desc, fontsize=5.5,
                    color="#546e7a", style="italic", va="top",
                    transform=ax_leg.transAxes, linespacing=1.12)

    ax_leg.set_xlim(0, 1)
    ax_leg.set_ylim(0, 1)

    # 8. Bar Chart Vertikal: Distribusi Alokasi Ruang
    ax_stats.set_facecolor("#ffffff")
    ax_stats.spines["top"].set_visible(False)
    ax_stats.spines["right"].set_visible(False)
    ax_stats.spines["left"].set_color("#cfd8dc")
    ax_stats.spines["bottom"].set_color("#cfd8dc")

    short_labels = ["Konservasi", "Koridor", "Pre-RBA", "Layak\nDikembangkan", "Non-\nVegetasi"]
    vals       = summary_df["luas_ha"].values
    pcts       = summary_df["persentase_pct"].values
    bar_colors = [HCSA_DECISION_CLASSES[row["kode"]]["color"] for _, row in summary_df.iterrows()]
    bar_edge   = ["#1b5e20", "#558b2f", "#e65100", "#f9a825", "#78909c"]

    x_ind = np.arange(len(short_labels))
    bars  = ax_stats.bar(
        x_ind, vals, color=bar_colors,
        edgecolor=bar_edge, linewidth=0.9,
        width=0.55, zorder=3
    )

    ax_stats.set_xticks(x_ind)
    ax_stats.set_xticklabels(short_labels, fontsize=7.2, fontweight="bold",
                              color="#263238", linespacing=1.15)
    ax_stats.set_ylim(0, max(vals) * 1.22)
    ax_stats.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda y, _: f"{y/1000:.0f}k")
    )
    ax_stats.tick_params(axis="y", labelsize=7.0, colors="#546e7a", length=3)
    ax_stats.tick_params(axis="x", length=0, pad=3)
    ax_stats.set_title("Distribusi Alokasi Ruang Lanskap (ha)",
                        fontsize=8.2, fontweight="bold", color="#263238",
                        pad=6, loc="center")
    ax_stats.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)

    # Label nilai di atas setiap bar (2 baris: nilai | persen)
    for bar, val, pct in zip(bars, vals, pcts):
        ax_stats.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(vals) * 0.012,
            f"{val/1000:.0f}k\n({pct:.1f}%)",
            ha="center", va="bottom", fontsize=6.8, fontweight="bold",
            color="#263238", linespacing=1.12
        )
    plt.savefig(p_out, dpi=300, bbox_inches="tight")
    plt.close("all")
    print(f"  [OK] Peta Tematik Kartografis: {p_out}")




_PRIO_COLORS = {
    3: "#1b5e20",  # HPP — hijau gelap
    2: "#4caf50",  # MPP — hijau sedang
    1: "#c8e6c9",  # LPP — hijau muda
    0: "#eceff1",  # NoData
}
_CONN_COLORS = {
    "protect (HPP)":          "#1b5e20",
    "protect (MPP adjacent)": "#388e3c",
    "corridor":               "#7cb342",
    "assess":                 "#fb8c00",
    "isolated":               "#b71c1c",
}


def plot_patch_analysis_dashboard(
    df: pd.DataFrame,
    output_path: str | Path,
    total_hcs_ha: float,
    cfg: dict = CONFIG,
) -> None:
    """Dashboard 5-panel metrik petak HCS Modul 5."""
    _style = {
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.linestyle": "--",
        "grid.alpha": 0.35,
        "axes.labelsize": 10,
        "axes.titlesize": 11,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
    }

    with plt.rc_context(_style):
        fig = plt.figure(figsize=(18, 12))
        fig.suptitle(
            "Dashboard Analisis Petak HCS  (HCSA Toolkit Modul 5)",
            fontsize=15, fontweight="bold", y=0.98,
        )
        gs = fig.add_gridspec(2, 3, hspace=0.44, wspace=0.35,
                              left=0.06, right=0.97, top=0.93, bottom=0.08)
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax3 = fig.add_subplot(gs[0, 2])
        ax4 = fig.add_subplot(gs[1, 0:2])
        ax5 = fig.add_subplot(gs[1, 2])

        prio_order = [3, 2, 1]
        prio_names = [PRIORITY_LABELS[p] for p in prio_order]
        prio_colors = [_PRIO_COLORS[p] for p in prio_order]

        # ── Panel 1: Grouped bar – jumlah patch & total luas per prioritas ────
        counts = [len(df[df["priority"] == p]) for p in prio_order]
        areas  = [df[df["priority"] == p]["area_ha"].sum() for p in prio_order]
        x = np.arange(len(prio_order))
        w = 0.38
        bars_n = ax1.bar(x - w/2, counts, w, color=prio_colors, alpha=0.88,
                         edgecolor="white", linewidth=0.8, label="Jumlah Patch")
        ax1b = ax1.twinx()
        bars_a = ax1b.bar(x + w/2, areas, w, color=prio_colors, alpha=0.45,
                          edgecolor="white", linewidth=0.8, hatch="//", label="Luas (ha)")
        for bar, v in zip(bars_n, counts):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(counts)*0.02,
                     f"{v:,}", ha="center", va="bottom", fontsize=8.5, fontweight="bold")
        for bar, v in zip(bars_a, areas):
            ax1b.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(areas)*0.02,
                      f"{v:,.0f}", ha="center", va="bottom", fontsize=7.5, color="dimgray")
        ax1.set_xticks(x)
        ax1.set_xticklabels(prio_names)
        ax1.set_ylabel("Jumlah Patch", fontsize=9)
        ax1b.set_ylabel("Total Luas (ha)", fontsize=9, color="dimgray")
        ax1b.tick_params(axis="y", labelcolor="dimgray")
        ax1b.spines["right"].set_visible(True)
        ax1b.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax1b.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper right", framealpha=0.85)
        ax1.set_title("① Jumlah Patch & Total Luas per Prioritas")

        # ── Panel 2: Donut – status konektivitas ──────────────────────────────
        conn_counts = df.groupby("connectivity_status")["area_ha"].sum().sort_values(ascending=False)
        conn_labels = conn_counts.index.tolist()
        conn_vals   = conn_counts.values
        conn_colors_list = [_CONN_COLORS.get(s, "#90a4ae") for s in conn_labels]
        wedges, texts, autotexts = ax2.pie(
            conn_vals,
            colors=conn_colors_list,
            autopct=lambda p: f"{p:.1f}%" if p > 3 else "",
            pctdistance=0.78,
            startangle=90,
            wedgeprops={"linewidth": 1.5, "edgecolor": "white"},
        )
        for at in autotexts:
            at.set_fontsize(8)
            at.set_fontweight("bold")
        centre_circle = plt.Circle((0, 0), 0.52, color="white")
        ax2.add_artist(centre_circle)
        ax2.text(0, 0, f"{total_hcs_ha:,.0f}\nha HCS",
                 ha="center", va="center", fontsize=9.5, fontweight="bold", color="#1b5e20")
        legend_patches = [
            mpatches.Patch(color=_CONN_COLORS.get(s, "#90a4ae"), label=f"{s} ({v:,.0f} ha)")
            for s, v in zip(conn_labels, conn_vals)
        ]
        ax2.legend(handles=legend_patches, fontsize=7.5, loc="lower center",
                   bbox_to_anchor=(0.5, -0.18), ncol=1, framealpha=0.85)
        ax2.set_title("② Status Konektivitas Patch (Luas Ha)")

        # ── Panel 3: Box plot distribusi luas per prioritas ───────────────────
        data_boxes = [df[df["priority"] == p]["area_ha"].values for p in prio_order]
        bp = ax3.boxplot(
            data_boxes,
            patch_artist=True,
            notch=False,
            medianprops={"color": "white", "linewidth": 2},
            whiskerprops={"linewidth": 1.2},
            capprops={"linewidth": 1.2},
            flierprops={"marker": "o", "markersize": 3, "alpha": 0.5},
        )
        for patch, color in zip(bp["boxes"], prio_colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.85)
        for i, (data, color) in enumerate(zip(data_boxes, prio_colors), 1):
            jitter = np.random.normal(i, 0.07, size=len(data))
            ax3.scatter(np.clip(jitter, i - 0.35, i + 0.35), data,
                        alpha=0.35, s=12, color=color, zorder=3)
        ax3.set_xticks([1, 2, 3])
        ax3.set_xticklabels(prio_names)
        ax3.set_ylabel("Luas Patch (ha)")
        ax3.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax3.set_title("③ Distribusi Luas Patch per Prioritas")

        # ── Panel 4: Scatter – total area vs core area ────────────────────────
        for p in prio_order:
            sub = df[df["priority"] == p]
            risk_mask = sub["is_high_risk"]
            ax4.scatter(
                sub["area_ha"], sub["core_area_ha"],
                c=_PRIO_COLORS[p], s=40, alpha=0.65, label=PRIORITY_LABELS[p],
                zorder=3, edgecolors="none",
            )
            if risk_mask.any():
                ax4.scatter(
                    sub.loc[risk_mask, "area_ha"], sub.loc[risk_mask, "core_area_ha"],
                    c="none", s=80, edgecolors="#e53935", linewidths=1.5,
                    zorder=4, label=None,
                )
        max_val = df["area_ha"].max() * 1.05
        ax4.plot([0, max_val], [0, max_val], linestyle="--", color="dimgray",
                 linewidth=1.0, alpha=0.5, label="Core = Total (ref)")
        ax4.axhline(cfg["hpp_core_ha"], color="#1b5e20", linestyle=":",
                    linewidth=1.2, alpha=0.7, label=f"HPP core >= {cfg['hpp_core_ha']:.0f} ha")
        ax4.axhline(cfg["mpp_core_ha"], color="#4caf50", linestyle=":",
                    linewidth=1.2, alpha=0.7, label=f"MPP core >= {cfg['mpp_core_ha']:.0f} ha")
        risk_df = df[df["is_high_risk"] & (df["connectivity_status"] == "isolated")]
        risk_patch = mpatches.Patch(edgecolor="#e53935", facecolor="none",
                                    linewidth=1.5, label=f"High Risk ({len(risk_df)} patch)")
        ax4.set_xlabel("Total Luas Patch (ha)")
        ax4.set_ylabel("Luas Kawasan Inti (ha)")
        ax4.set_title("④ Luas Total vs Luas Inti per Patch  (◯ = High Risk)")
        ax4.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax4.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        handles4, labels4 = ax4.get_legend_handles_labels()
        ax4.legend(handles4 + [risk_patch], labels4 + [risk_patch.get_label()],
                   fontsize=8, loc="upper left", framealpha=0.85)

        # ── Panel 5: Histogram Shape Index ────────────────────────────────────
        si_all  = df["shape_index"].clip(upper=df["shape_index"].quantile(0.98))
        si_risk = df.loc[df["is_high_risk"], "shape_index"].clip(
            upper=df["shape_index"].quantile(0.98))
        bins = np.linspace(0, si_all.max() + 0.1, 40)
        ax5.hist(si_all, bins=bins, color="#1b5e20", alpha=0.7, label="Semua Patch")
        ax5.hist(si_risk, bins=bins, color="#e53935", alpha=0.8, label="High Risk")
        ax5.axvline(cfg["si_risk_threshold"], color="#b71c1c", linewidth=1.8,
                    linestyle="--", label=f"Batas Risiko SI={cfg['si_risk_threshold']}")
        ax5.set_xlabel("Shape Index (SI)")
        ax5.set_ylabel("Jumlah Patch")
        ax5.set_title("⑤ Distribusi Shape Index Patch")
        ax5.legend(fontsize=8.5, framealpha=0.85)

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path, dpi=300, bbox_inches="tight")
        plt.close("all")
        print(f"  [OK] Dashboard Patch Analysis: {out_path}")


def plot_multiyear_decision_dashboard(
    multi_df: pd.DataFrame,
    output_png: str | Path,
) -> None:
    """Dashboard Eksekutif Komparasi Keputusan HCSA & Kelayakan Lahan Lintas Tahun (2021-2025)."""
    p_out = Path(output_png)
    p_out.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(20, 13), dpi=300, facecolor="#ffffff")
    fig.suptitle(
        "DASHBOARD EKSEKUTIF KEPUTUSAN ZONASI HCSA LINTAS TAHUN (2021–2025)\n"
        "Evaluasi Dinamika Alokasi Konservasi, Koridor Ekologis, dan Potensi Lahan Pembangunan Berkelanjutan Kabupaten Bogor",
        fontsize=13.5, fontweight="bold", color="#1a237e", y=0.97
    )

    gs = fig.add_gridspec(3, 1, height_ratios=[0.75, 2.7, 1.2], hspace=0.35,
                          left=0.05, right=0.95, top=0.91, bottom=0.04)

    # --- TIER 1: KPI CARDS ---
    gs_kpi = gs[0].subgridspec(1, 4, wspace=0.15)
    last_r = multi_df.iloc[-1]
    first_r = multi_df.iloc[0]
    total_2025 = (last_r["conserve_ha"] + last_r["corridor_ha"] + last_r["assess_ha"] +
                  last_r["developable_ha"] + last_r["non_veg_ha"])
    pct_conserve_2025 = (last_r["conserve_ha"] / total_2025 * 100) if total_2025 > 0 else 0
    corridor_delta = ((last_r["corridor_ha"] - first_r["corridor_ha"]) / first_r["corridor_ha"] * 100) if first_r["corridor_ha"] > 0 else 0

    kpi_data = [
        {
            "title": "HCS KONSERVASI (2025)",
            "val": f"{last_r['conserve_ha']:,.0f} ha",
            "sub": f"{pct_conserve_2025:.1f}% Total Lanskap (Terproteksi Mutlak)",
            "color": "#1b5e20",
            "bg": "#f1f8e9",
        },
        {
            "title": "KORIDOR EKOLOGIS (2025)",
            "val": f"{last_r['corridor_ha']:,.0f} ha",
            "sub": f"+{corridor_delta:.1f}% vs 2021 (Konektivitas Satwa)",
            "color": "#558b2f",
            "bg": "#f9fbe7",
        },
        {
            "title": "INDIKASI PEMBANGUNAN (2025)",
            "val": f"{last_r['developable_ha']:,.0f} ha",
            "sub": f"Termasuk {last_r['dropped_lpp_ha']:,.0f} ha LPP Terisolasi Di-drop",
            "color": "#f57f17",
            "bg": "#fffde7",
        },
        {
            "title": "KAJI PRE-RBA (2025)",
            "val": f"{last_r['assess_ha']:,.0f} ha",
            "sub": "Prioritas Survei Keanekaragaman Hayati",
            "color": "#e65100",
            "bg": "#fff3e0",
        },
    ]

    for idx, kpi in enumerate(kpi_data):
        ax_k = fig.add_subplot(gs_kpi[idx])
        ax_k.set_axis_off()
        box = mpatches.FancyBboxPatch(
            (0.0, 0.0), 1.0, 1.0, boxstyle="round,pad=0.04",
            facecolor=kpi["bg"], edgecolor=kpi["color"], linewidth=1.5
        )
        ax_k.add_patch(box)
        ax_k.text(0.5, 0.78, kpi["title"], ha="center", va="center", fontsize=9.0, fontweight="bold", color=kpi["color"])
        ax_k.text(0.5, 0.45, kpi["val"], ha="center", va="center", fontsize=16, fontweight="bold", color="#212121")
        ax_k.text(0.5, 0.18, kpi["sub"], ha="center", va="center", fontsize=7.5, color="#546e7a")

    # --- TIER 2: CHARTS ---
    gs_charts = gs[1].subgridspec(1, 2, width_ratios=[1.15, 1.0], wspace=0.22)
    ax1 = fig.add_subplot(gs_charts[0])
    ax2 = fig.add_subplot(gs_charts[1])

    years = multi_df["tahun"].tolist()
    x = np.arange(len(years))

    c_conserve = multi_df["conserve_ha"].values
    c_corridor = multi_df["corridor_ha"].values
    c_assess   = multi_df["assess_ha"].values
    c_develop  = multi_df["developable_ha"].values

    w = 0.55
    b1 = ax1.bar(x, c_conserve, w, label="1. HCS Konservasi (Conserve)", color="#1b5e20", edgecolor="#0d3b13", linewidth=0.8)
    b2 = ax1.bar(x, c_corridor, w, bottom=c_conserve, label="2. HCS Koridor (Corridor)", color="#7cb342", edgecolor="#4b6b23", linewidth=0.8)
    b3 = ax1.bar(x, c_assess, w, bottom=c_conserve + c_corridor, label="3. HCS Kaji RBA (Assess)", color="#fb8c00", edgecolor="#b26000", linewidth=0.8)
    b4 = ax1.bar(x, c_develop, w, bottom=c_conserve + c_corridor + c_assess, label="4. Layak Dikembangkan", color="#ffee58", edgecolor="#bfa629", linewidth=0.8)

    for i in range(len(years)):
        ax1.text(x[i], c_conserve[i] / 2, f"{c_conserve[i]:,.0f} ha", ha="center", va="center", fontsize=8.2, fontweight="bold", color="#ffffff")
        tot_veg = c_conserve[i] + c_corridor[i] + c_assess[i] + c_develop[i]
        ax1.text(x[i], tot_veg + 3000, f"Total:\n{tot_veg:,.0f} ha", ha="center", va="bottom", fontsize=8.0, fontweight="bold", color="#37474f")

    ax1.set_xticks(x)
    ax1.set_xticklabels(years, fontsize=10, fontweight="bold", color="#263238")
    ax1.set_ylabel("Luas Area Vegetasi & Pembangunan (Hektare)", fontsize=9.5, color="#263238")
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda val, _: f"{val:,.0f} ha"))
    ax1.set_ylim(0, max(c_conserve + c_corridor + c_assess + c_develop) * 1.15)
    ax1.set_title("Komposisi Alokasi Ruang HCSA per Tahun (2021–2025)", fontsize=11, fontweight="bold", color="#1b5e20", pad=12)
    ax1.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, fontsize=8.2, framealpha=0.92, edgecolor="#cfd8dc")
    ax1.grid(axis="y", linestyle="--", alpha=0.4)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    # Chart 2: Tren Dinamika Konservasi vs Pembangunan (FIXED X-AXIS SYNC)
    ax2.plot(years, c_conserve, marker="o", markersize=7, color="#1b5e20", linewidth=2.6, label="HCS Konservasi (ha)")
    ax2.plot(years, c_develop, marker="s", markersize=7, color="#e65100", linewidth=2.4, linestyle="--", label="Layak Dikembangkan (ha)")

    for y, c, d in zip(years, c_conserve, c_develop):
        ax2.text(y, c + 2500, f"{c:,.0f}", ha="center", va="bottom", fontsize=8.0, fontweight="bold", color="#1b5e20")
        ax2.text(y, d - 4000, f"{d:,.0f}", ha="center", va="top", fontsize=8.0, fontweight="bold", color="#e65100")

    ax2_twin = ax2.twinx()
    ax2_twin.bar(years, multi_df["dropped_lpp_ha"].values, width=0.28, color="#8d6e63", alpha=0.45, edgecolor="#5d4037", linewidth=0.8, label="LPP Dropped ke Pembangunan (ha)")
    for y, v in zip(years, multi_df["dropped_lpp_ha"].values):
        ax2_twin.text(y, v + 80, f"{v:,.0f} ha", ha="center", va="bottom", fontsize=7.5, color="#4e342e", fontweight="bold")

    ax2_twin.set_ylabel("Luas LPP Dropped (Hektare)", color="#4e342e", fontsize=9.2)
    ax2_twin.tick_params(axis="y", labelcolor="#4e342e")
    ax2_twin.set_ylim(0, max(multi_df["dropped_lpp_ha"].values) * 2.2)
    ax2_twin.yaxis.set_major_formatter(mticker.FuncFormatter(lambda val, _: f"{val:,.0f} ha"))

    ax2.set_xticks(years)
    ax2.set_xticklabels(years, fontsize=10, fontweight="bold", color="#263238")
    ax2.set_ylabel("Luas Area Utama (Hektare)", fontsize=9.5, color="#263238")
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda val, _: f"{val:,.0f} ha"))
    ax2.set_ylim(0, max(c_conserve) * 1.15)
    ax2.set_title("Tren Dinamika Konservasi vs Indikasi Pembangunan", fontsize=11, fontweight="bold", color="#1b5e20", pad=12)
    ax2.grid(True, linestyle="--", alpha=0.4)
    ax2.spines["top"].set_visible(False)

    h_a, l_a = ax2.get_legend_handles_labels()
    h_b, l_b = ax2_twin.get_legend_handles_labels()
    ax2.legend(h_a + h_b, l_a + l_b, loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, fontsize=8.2, framealpha=0.92, edgecolor="#cfd8dc")

    # --- TIER 3: EXECUTIVE SUMMARY TABLE ---
    ax_tbl = fig.add_subplot(gs[2])
    ax_tbl.set_axis_off()

    tbl_headers = ["Tahun", "1. Konservasi (ha)", "2. Koridor (ha)", "3. Kaji RBA (ha)", "4. Layak Bangun (ha)", "5. Non-Target (ha)", "LPP Dropped (ha)", "Proporsi Konservasi (%)"]
    cell_data = []
    for _, r in multi_df.iterrows():
        tot = r["conserve_ha"] + r["corridor_ha"] + r["assess_ha"] + r["developable_ha"] + r["non_veg_ha"]
        pct_c = (r["conserve_ha"] / tot * 100) if tot > 0 else 0
        cell_data.append([
            str(int(r["tahun"])),
            f"{r['conserve_ha']:,.1f}",
            f"{r['corridor_ha']:,.1f}",
            f"{r['assess_ha']:,.1f}",
            f"{r['developable_ha']:,.1f}",
            f"{r['non_veg_ha']:,.1f}",
            f"{r['dropped_lpp_ha']:,.1f} ({int(r['dropped_lpp_count'])} patch)",
            f"{pct_c:.2f} %",
        ])

    avg_c = multi_df["conserve_ha"].mean()
    avg_cor = multi_df["corridor_ha"].mean()
    avg_ass = multi_df["assess_ha"].mean()
    avg_dev = multi_df["developable_ha"].mean()
    avg_nv  = multi_df["non_veg_ha"].mean()
    avg_drp = multi_df["dropped_lpp_ha"].mean()
    tot_avg = avg_c + avg_cor + avg_ass + avg_dev + avg_nv
    cell_data.append([
        "Rata-rata 5 Thn",
        f"{avg_c:,.1f}",
        f"{avg_cor:,.1f}",
        f"{avg_ass:,.1f}",
        f"{avg_dev:,.1f}",
        f"{avg_nv:,.1f}",
        f"{avg_drp:,.1f}",
        f"{avg_c / tot_avg * 100:.2f} %",
    ])

    table = ax_tbl.table(
        cellText=cell_data,
        colLabels=tbl_headers,
        loc="center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1.0, 1.4)

    for col_idx in range(len(tbl_headers)):
        cell = table[(0, col_idx)]
        cell.set_facecolor("#1b5e20")
        cell.set_text_props(color="#ffffff", weight="bold")

    for row_idx in range(1, len(cell_data) + 1):
        bg_c = "#f1f8e9" if row_idx == len(cell_data) else ("#f8fafc" if row_idx % 2 == 0 else "#ffffff")
        is_bold = (row_idx == len(cell_data))
        for col_idx in range(len(tbl_headers)):
            c = table[(row_idx, col_idx)]
            c.set_facecolor(bg_c)
            if is_bold:
                c.set_text_props(weight="bold", color="#1b5e20")

    plt.savefig(p_out, dpi=300, bbox_inches="tight")
    plt.close("all")
    print(f"  [OK] Dashboard Multi-Tahun: {p_out}")


# ==============================================================================
# PIPELINE UTAMA
# ==============================================================================

def run_patch_analysis(
    strat_path: str | Path,
    output_dir: str | Path,
    strat_raster_path: str | Path | None = None,
    conservation_layer: str | Path | None = None,
    admin_boundary: str | Path | None = None,
    cfg: dict = CONFIG,
    year_tag: str = "",
) -> dict:
    """
    Jalankan pipeline analisis petak dan keputusan zonasi HCSA lengkap.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("=" * 64)
    print(f"  ANALISIS PETAK & KEPUTUSAN ZONASI HCSA  {year_tag}")
    print("=" * 64)

    strat_file = Path(strat_path)
    print(f"\n[1/8] Membaca data masukan: {strat_file}")
    strat_data, meta = read_raster(strat_file)
    ha = _pixel_area_ha(meta)

    # Ekstraksi masker biner HCS dari raster stratifikasi (kelas 3 s/d 6: YRF, LRF, MRF, HK)
    # Jika input sudah berupa masker biner (nilai maks 1), langsung gunakan
    if strat_data.max() > 1:
        mask = ((strat_data >= 3) & (strat_data <= 6)).astype(np.uint8)
        actual_strat_file = strat_file
    else:
        mask = (strat_data == 1).astype(np.uint8)
        actual_strat_file = Path(strat_raster_path) if strat_raster_path else None

    n_hcs = int(np.count_nonzero(mask))
    print(f"      Piksel HCS mentah : {n_hcs:,} ({n_hcs * ha:,.1f} ha)")

    # Saring MMU & Penutupan Celah Kanopi Internal (HCSA Modul 5)
    mmu_ha = cfg.get("mmu_min_patch_ha", 0.5)
    max_hole_ha = cfg.get("max_hole_fill_ha", 0.5)
    mask_sieved, n_sieved = sieve_patch_mask(mask, mmu_ha, meta)
    mask_clean, n_filled = fill_internal_canopy_gaps(mask_sieved, max_hole_ha, meta)
    if n_sieved > 0 or n_filled > 0:
        print(f"      • Filter MMU ({mmu_ha} ha) : {n_sieved:,} fragmen < MMU dieliminasi")
        print(f"      • Celah Kanopi Internal  : {n_filled:,} piksel (<={max_hole_ha} ha) ditutup")

    n_clean_hcs = int(np.count_nonzero(mask_clean))
    print(f"      Piksel HCS bersih : {n_clean_hcs:,} ({n_clean_hcs * ha:,.1f} ha)")

    print(f"\n[2/8] Labeling patch (konektivitas 8-arah)")
    labeled, n_patches = label_patches(mask_clean)
    print(f"      Patch teridentifikasi: {n_patches:,}")

    buf_px = _meters_to_pixels(cfg["buffer_inner_m"], meta)
    print(f"\n[3/8] Erosi penyangga {cfg['buffer_inner_m']:.0f} m ({buf_px} piksel) -> kawasan inti")
    core_mask = erode_core_areas(mask_clean, buf_px)
    n_core = int(np.count_nonzero(core_mask))
    print(f"      Luas kawasan inti : {n_core:,} piksel ({n_core * ha:,.1f} ha)")

    print(f"\n[4/8] Menghitung atribut geometri patch")
    df = compute_patch_attributes(labeled, core_mask, n_patches, meta)

    print(f"\n[5/8] Klasifikasi prioritas HPP/MPP/LPP")
    df = classify_priority(df, cfg)

    print(f"\n[6/8] Analisis konektivitas & risiko fragmentasi")
    df = analyze_connectivity(df, labeled, meta, conservation_layer, cfg)
    df = flag_high_risk(df)

    print(f"\n[7/8] Menerapkan Pohon Keputusan HCSA (Decision Tree Step 1-6)")
    df = apply_hcsa_decision_tree(df, drop_isolated_lpp=cfg.get("drop_isolated_lpp", True))

    n_conserve = len(df[df["final_decision"] == "CONSERVE"])
    n_corridor = len(df[df["final_decision"] == "CORRIDOR"])
    n_assess   = len(df[df["final_decision"] == "ASSESS"])
    n_develop  = len(df[df["final_decision"] == "DEVELOP"])

    ha_conserve = df.loc[df["final_decision"] == "CONSERVE", "area_ha"].sum()
    ha_corridor = df.loc[df["final_decision"] == "CORRIDOR", "area_ha"].sum()
    ha_assess   = df.loc[df["final_decision"] == "ASSESS", "area_ha"].sum()
    ha_develop  = df.loc[df["final_decision"] == "DEVELOP", "area_ha"].sum()

    print(f"      • HCS Konservasi (Conserve) : {n_conserve:>4} patch ({ha_conserve:>10,.1f} ha)")
    print(f"      • HCS Koridor (Corridor)    : {n_corridor:>4} patch ({ha_corridor:>10,.1f} ha)")
    print(f"      • HCS Kaji RBA (Assess)     : {n_assess:>4} patch ({ha_assess:>10,.1f} ha)")
    print(f"      • LPP Dropped ke Pembangunan: {n_develop:>4} patch ({ha_develop:>10,.1f} ha)")

    print(f"\n[8/8] Menghasilkan Peta Zonasi Akhir Lanskap & Menyimpan Output")
    # Peta Keputusan Akhir Lanskap (HCSA Land Suitability GeoTIFF & Summary CSV)
    final_tif_path = out / f"HCSA_Final_Decision_Map_{year_tag}.tif" if year_tag else out / "HCSA_Final_Decision_Map.tif"
    final_raster, summary_df = generate_hcsa_land_suitability_map(
        labeled=labeled,
        df=df,
        strat_raster_path=actual_strat_file,
        conservation_layer=conservation_layer,
        meta=meta,
        output_tif=final_tif_path,
        clean_mmu_pixels=cfg.get("clean_zonation_mmu", 6),
    )

    summary_csv_path = out / f"HCSA_Decision_Summary_{year_tag}.csv" if year_tag else out / "HCSA_Decision_Summary.csv"
    summary_df.to_csv(summary_csv_path, index=False, encoding="utf-8")

    # Peta Kartografis Tematik PNG
    final_map_png = out / f"HCSA_Land_Suitability_Map_{year_tag}.png" if year_tag else out / "HCSA_Land_Suitability_Map.png"
    plot_hcsa_land_suitability_map(
        decision_raster=final_raster,
        summary_df=summary_df,
        output_png=final_map_png,
        year_tag=year_tag,
        meta=meta,
        admin_boundary=admin_boundary,
    )

    print(f"\nRingkasan Zonasi Lahan {year_tag}:")
    print(summary_df[["kode", "zona_hcsa", "luas_ha", "persentase_pct"]].to_string(index=False))

    return {
        "final_decision_tif":   final_tif_path,
        "final_map_png":        final_map_png,
        "final_summary_csv":    summary_csv_path,
        "patch_df":             df,
        "summary_df":           summary_df,
    }


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    cfg = CONFIG.copy()

    if PROCESS_ALL_YEARS:
        strat_files = sorted(STRAT_DIR.glob("HCS_Stratification_*_Final.tif"))
        if not strat_files:
            print(f"[ERROR] Tidak ditemukan file 'HCS_Stratification_*_Final.tif' di '{STRAT_DIR}'")
            print("Tips: Jalankan 'python hcs_stratification.py' terlebih dahulu.")
        else:
            print(f"[INFO] Ditemukan {len(strat_files)} raster stratifikasi HCS ({', '.join(f.stem for f in strat_files)}).")
            print("[INFO] Memproses analisis petak & keputusan zonasi untuk setiap tahun...\n")

            multi_year_decision_rows: list[dict] = []

            for idx, strat_file in enumerate(strat_files, 1):
                yr_match = re.search(r"\d{4}", strat_file.stem)
                year_tag = yr_match.group(0) if yr_match else strat_file.stem
                sub_out = OUTPUT_DIR / year_tag

                print(f"\n>>> [{idx}/{len(strat_files)}] Tahun {year_tag}: {strat_file} -> {sub_out}")
                outputs = run_patch_analysis(
                    strat_path=strat_file,
                    output_dir=sub_out,
                    conservation_layer=CONSERVATION_LAYER,
                    admin_boundary=ADMIN_BOUNDARY,
                    cfg=cfg,
                    year_tag=year_tag,
                )

                report_df = outputs["patch_df"]
                sum_df = outputs["summary_df"]
                dropped_lpp = report_df[report_df["is_dropped_hcs"] == True]

                multi_year_decision_rows.append({
                    "tahun": int(year_tag) if year_tag.isdigit() else year_tag,
                    "conserve_ha": sum_df.loc[sum_df["kode"] == 1, "luas_ha"].values[0] if (sum_df["kode"] == 1).any() else 0.0,
                    "corridor_ha": sum_df.loc[sum_df["kode"] == 2, "luas_ha"].values[0] if (sum_df["kode"] == 2).any() else 0.0,
                    "assess_ha": sum_df.loc[sum_df["kode"] == 3, "luas_ha"].values[0] if (sum_df["kode"] == 3).any() else 0.0,
                    "developable_ha": sum_df.loc[sum_df["kode"] == 4, "luas_ha"].values[0] if (sum_df["kode"] == 4).any() else 0.0,
                    "non_veg_ha": sum_df.loc[sum_df["kode"] == 5, "luas_ha"].values[0] if (sum_df["kode"] == 5).any() else 0.0,
                    "dropped_lpp_count": len(dropped_lpp),
                    "dropped_lpp_ha": round(dropped_lpp["area_ha"].sum(), 1),
                })

            # Simpan summary zonasi multi-tahun
            if multi_year_decision_rows:
                multi_df = pd.DataFrame(multi_year_decision_rows).sort_values("tahun")
                multi_summary_path = OUTPUT_DIR / "HCSA_MultiYear_Decision_Summary.csv"
                multi_df.to_csv(multi_summary_path, index=False, encoding="utf-8")
                print(f"\n[OK] Ringkasan keputusan zonasi multi-tahun: {multi_summary_path}")

                # Visualisasi Dashboard Multi-Tahun
                multi_dashboard_png = OUTPUT_DIR / "HCSA_MultiYear_Decision_Dashboard.png"
                plot_multiyear_decision_dashboard(multi_df, multi_dashboard_png)

                print("\nRingkasan Zonasi Multi-Tahun (Hektare):")
                print(multi_df.to_string(index=False))

            print("\n[SELESAI] Seluruh analisis petak & keputusan zonasi HCSA berhasil dijalankan!")
    else:
        target_strat = Path(INPUT_STRAT_FILE)
        if not target_strat.exists():
            print(f"[ERROR] File stratifikasi input '{target_strat}' tidak ditemukan.")
        else:
            yr_match = re.search(r"\d{4}", target_strat.stem)
            year_tag = yr_match.group(0) if yr_match else target_strat.stem

            outputs = run_patch_analysis(
                strat_path=target_strat,
                output_dir=OUTPUT_DIR / year_tag if year_tag else OUTPUT_DIR,
                conservation_layer=CONSERVATION_LAYER,
                admin_boundary=ADMIN_BOUNDARY,
                cfg=cfg,
                year_tag=year_tag,
            )

            print("\nOutput files:")
            for k in ["final_decision_tif", "final_map_png", "final_summary_csv"]:
                print(f"  {k:<20}: {outputs[k]}")
