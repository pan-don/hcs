from __future__ import annotations

import matplotlib
import re
from pathlib import Path
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import ListedColormap
from rasterio.warp import Resampling, reproject
from scipy.ndimage import binary_closing, binary_opening, label
matplotlib.use('Agg')  


# 1. Konfigurasi Global
DATA_DIR = Path("data")
OUTPUT_DIR = Path("output/stratification")
MMU_PIXELS = 56
HCS_CLASS_MIN = 3
NODATA_IN = -9999.0
AGBD_THRESHOLDS = [60.0, 75.0, 90.0, 110.0, 130.0]

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

HCS_COLORMAP = {
    0: (176, 190, 197, 255),
    1: (255, 245, 157, 255),
    2: (251, 192, 45, 255),
    3: (165, 214, 167, 255),
    4: (76, 175, 80, 255),
    5: (46, 125, 50, 255),
    6: (27, 94, 32, 255),
}


# 2. Modul I/O dan Alignment Raster
def read_raster(path: str | Path) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float32)
        meta = src.meta.copy()
        nodata = src.nodata if src.nodata is not None else NODATA_IN
    data[data == nodata] = np.nan
    return data, meta


def align_raster(
    src_path: str | Path,
    target_meta: dict,
    resampling_method: Resampling = Resampling.nearest,
    is_mask: bool = False,
) -> np.ndarray:
    dtype = np.uint8 if is_mask else np.float32
    fill_val = 0 if is_mask else np.nan
    aligned = np.full((target_meta["height"], target_meta["width"]), fill_val, dtype=dtype)
    with rasterio.open(src_path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=aligned,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=target_meta["transform"],
            dst_crs=target_meta["crs"],
            resampling=resampling_method,
        )
    return aligned


def write_discrete_geotiff(
    path: str | Path,
    data: np.ndarray,
    meta: dict,
    nodata: int = 255,
) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_meta = meta.copy()
    out_meta.update(dtype="uint8", count=1, nodata=nodata, compress="lzw", driver="GTiff")
    clean_data = np.nan_to_num(data, nan=nodata).astype(np.uint8)

    with rasterio.open(out_path, "w", **out_meta) as dst:
        dst.write(clean_data, 1)
        dst.write_colormap(1, HCS_COLORMAP)


# 3. Modul Stratifikasi dan MMU Sieve
def classify_agbd_with_masking(
    agbd: np.ndarray,
    lc: np.ndarray | None,
    thresholds: list[float],
) -> tuple[np.ndarray, np.ndarray]:
    clean_agbd = np.nan_to_num(agbd, nan=0.0)
    if lc is not None:
        non_veg_mask = (lc == 0) | (lc == 6) | (lc == 7) | (lc == 8) | (clean_agbd <= 0)
    else:
        non_veg_mask = clean_agbd <= 0

    veg_mask = ~non_veg_mask
    hcs = np.zeros(agbd.shape, dtype=np.uint8)

    if np.any(veg_mask):
        veg_classes = np.digitize(clean_agbd[veg_mask], bins=thresholds, right=False) + 1
        hcs[veg_mask] = np.clip(veg_classes, 1, 6).astype(np.uint8)

    hcs[non_veg_mask] = 0
    return hcs, veg_mask


def filter_mmu_and_downgrade(hcs_class: np.ndarray, mmu_pixels: int, hcs_min: int) -> np.ndarray:
    raw_mask = (hcs_class >= hcs_min).astype(bool)
    struct = np.ones((3, 3), dtype=int)
    labeled, _ = label(raw_mask, structure=struct)
    sizes = np.bincount(labeled.ravel())
    keep_mask = sizes >= mmu_pixels
    keep_mask[0] = False

    sieved = keep_mask[labeled]
    sieved = binary_closing(sieved, structure=struct, iterations=1)
    sieved = binary_opening(sieved, structure=struct, iterations=1)

    final_hcs = hcs_class.copy()
    downgrade_idx = (hcs_class >= hcs_min) & (~sieved)
    final_hcs[downgrade_idx] = 2
    return final_hcs


# 4. Modul Pipeline Tunggal
def process_single_year(
    agbd_path: Path,
    lc_path: Path | None = None,
    output_dir: Path = OUTPUT_DIR,
) -> tuple[np.ndarray, dict, int]:
    year_match = re.search(r"\d{4}", agbd_path.stem)
    year = int(year_match.group(0)) if year_match else 0

    agbd, meta = read_raster(agbd_path)
    lc = align_raster(lc_path, meta, Resampling.nearest, is_mask=True) if lc_path and lc_path.exists() else None

    raw_hcs, _ = classify_agbd_with_masking(agbd, lc, AGBD_THRESHOLDS)
    final_hcs = filter_mmu_and_downgrade(raw_hcs, MMU_PIXELS, HCS_CLASS_MIN)

    out_file = output_dir / f"HCS_Stratification_{year}_Final.tif"
    write_discrete_geotiff(out_file, final_hcs, meta)

    return final_hcs, meta, year


# 5. Modul Visualisasi Time Series
_STYLE = {
    "font.family": "DejaVu Sans",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.linestyle": "--",
    "grid.alpha": 0.4,
    "axes.labelsize": 10,
    "axes.titlesize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
}


def _ha_fmt(x: float, _pos: int) -> str:
    """Format angka hektare: ribuan dengan titik."""
    return f"{x:,.0f}"


def plot_timeseries_hcs(df_summary: pd.DataFrame, output_path: Path) -> None:
    """
    Dashboard 4-panel time series stratifikasi HCS:
      Panel 1 (kiri atas)  : Stacked area – luas tiap kelas per tahun
      Panel 2 (kanan atas) : Tren HCS Potensial vs Non-HCS (dual Y-axis)
      Panel 3 (kiri bawah) : Komposisi kelas ternormalisasi (stacked bar 100%)
      Panel 4 (kanan bawah): Perubahan YoY luas total HCS Potensial (waterfall bar)
    """
    with plt.rc_context(_STYLE):
        df = df_summary.sort_values(["Tahun", "Kelas_ID"]).copy()
        years = sorted(df["Tahun"].unique())

        # Pivot: baris=tahun, kolom=Kelas_ID
        pivot = df.pivot(index="Tahun", columns="Kelas_ID", values="Luas_Ha").fillna(0)
        colors = [tuple(c / 255.0 for c in HCS_COLORMAP[i][:3]) for i in range(7)]
        labels = [CLASS_LABELS[i] for i in range(7)]

        # Kelompok HCS Potensial (kelas 3–6) dan Non-HCS (kelas 1–2)
        hcs_total = pivot[[3, 4, 5, 6]].sum(axis=1)
        non_hcs_total = pivot[[1, 2]].sum(axis=1)
        masked_total = pivot[[0]].sum(axis=1)

        fig = plt.figure(figsize=(16, 12))
        fig.suptitle(
            "Dashboard Dinamika Stratifikasi HCS – Time Series Analisis",
            fontsize=14, fontweight="bold", y=0.98,
        )
        gs = fig.add_gridspec(2, 2, hspace=0.42, wspace=0.32,
                              left=0.07, right=0.97, top=0.93, bottom=0.08)
        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[0, 1])
        ax3 = fig.add_subplot(gs[1, 0])
        ax4 = fig.add_subplot(gs[1, 1])

        # ── Panel 1: Stacked Area ──────────────────────────────────────────────
        stacks = [pivot[i].values for i in range(7)]
        ax1.stackplot(years, stacks, labels=labels, colors=colors, alpha=0.88)
        ax1.set_title("① Luas Tiap Kelas HCS per Tahun (Stacked Area)")
        ax1.set_xlabel("Tahun")
        ax1.set_ylabel("Luas (Ha)")
        ax1.set_xticks(years)
        ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_ha_fmt))
        # Legend di luar, urutan terbalik agar sesuai stack
        handles, lbl = ax1.get_legend_handles_labels()
        ax1.legend(
            handles[::-1], lbl[::-1],
            fontsize=7.5, loc="upper left",
            framealpha=0.8, ncol=1,
        )

        # ── Panel 2: HCS Potensial vs Non-HCS dual Y-axis ─────────────────────
        color_hcs = tuple(c / 255.0 for c in HCS_COLORMAP[5][:3])   # MDF green
        color_non = tuple(c / 255.0 for c in HCS_COLORMAP[1][:3])   # Open Land yellow
        color_mask = tuple(c / 255.0 for c in HCS_COLORMAP[0][:3])  # Masked grey

        ax2.plot(years, hcs_total.values, marker="o", linewidth=2.2,
                 color=color_hcs, label="HCS Potensial (kl. 3–6)")
        ax2.fill_between(years, hcs_total.values, alpha=0.18, color=color_hcs)
        ax2.set_ylabel("HCS Potensial (Ha)", color=color_hcs)
        ax2.tick_params(axis="y", labelcolor=color_hcs)
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_ha_fmt))

        ax2b = ax2.twinx()
        ax2b.plot(years, non_hcs_total.values, marker="s", linewidth=2.0,
                  linestyle="--", color=color_non, label="Non-HCS (kl. 1–2)")
        ax2b.plot(years, masked_total.values, marker="^", linewidth=1.6,
                  linestyle=":", color=color_mask, label="Masked/Non-Veg")
        ax2b.set_ylabel("Non-HCS / Masked (Ha)", color="dimgray")
        ax2b.tick_params(axis="y", labelcolor="dimgray")
        ax2b.yaxis.set_major_formatter(mticker.FuncFormatter(_ha_fmt))
        ax2b.spines["right"].set_visible(True)

        ax2.set_title("② Tren HCS Potensial vs Non-HCS (Dual Y-Axis)")
        ax2.set_xlabel("Tahun")
        ax2.set_xticks(years)
        # Gabungkan legend dari kedua axis
        lines1, lbl1 = ax2.get_legend_handles_labels()
        lines2, lbl2 = ax2b.get_legend_handles_labels()
        ax2.legend(lines1 + lines2, lbl1 + lbl2, fontsize=8, loc="upper right", framealpha=0.85)

        # ── Panel 3: Komposisi Ternormalisasi (100% Stacked Bar) ───────────────
        total_per_year = pivot.sum(axis=1)
        bar_width = 0.6
        bottoms = np.zeros(len(years))
        for cls_id in range(7):
            vals = (pivot[cls_id] / total_per_year * 100).values if cls_id in pivot.columns else np.zeros(len(years))
            ax3.bar(
                years, vals, bar_width,
                bottom=bottoms,
                color=colors[cls_id],
                label=labels[cls_id],
                alpha=0.9,
            )
            # Tempel label persen jika cukup besar
            for x, bot, val in zip(years, bottoms, vals):
                if val >= 4.0:
                    ax3.text(x, bot + val / 2, f"{val:.1f}%",
                             ha="center", va="center", fontsize=7, color="white",
                             fontweight="bold")
            bottoms += vals

        ax3.set_title("③ Komposisi Kelas (Normalized 100% Stacked Bar)")
        ax3.set_xlabel("Tahun")
        ax3.set_ylabel("Proporsi (%)")
        ax3.set_xticks(years)
        ax3.set_ylim(0, 100)
        ax3.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
        ax3.legend(fontsize=7.5, loc="lower left", ncol=2, framealpha=0.85)

        # ── Panel 4: Perubahan YoY HCS Potensial (Waterfall Bar) ──────────────
        yoy = hcs_total.diff().fillna(0).values
        bar_colors_yoy = ["#2e7d32" if v >= 0 else "#c62828" for v in yoy]
        ax4.bar(years, yoy, color=bar_colors_yoy, width=0.55, alpha=0.88,
                edgecolor="white", linewidth=0.6)
        ax4.axhline(0, color="dimgray", linewidth=1.0)

        for x, v in zip(years, yoy):
            offset = 80 if v >= 0 else -80
            va_val = "bottom" if v >= 0 else "top"
            ax4.text(x, v + offset, f"{v:+,.0f}", ha="center", va=va_val,
                     fontsize=8.5, fontweight="bold",
                     color="#2e7d32" if v >= 0 else "#c62828")

        ax4.set_title("④ Perubahan YoY Luas HCS Potensial (Ha)")
        ax4.set_xlabel("Tahun")
        ax4.set_ylabel("Delta Luas (Ha)")
        ax4.set_xticks(years)
        ax4.yaxis.set_major_formatter(mticker.FuncFormatter(_ha_fmt))

        # Patch legend sederhana untuk warna bar
        gain_patch = mpatches.Patch(color="#2e7d32", alpha=0.88, label="Pertambahan")
        loss_patch = mpatches.Patch(color="#c62828", alpha=0.88, label="Penyusutan")
        ax4.legend(handles=[gain_patch, loss_patch], fontsize=8.5,
                   loc="upper right", framealpha=0.85)

        plt.savefig(output_path, dpi=300, bbox_inches="tight")
        plt.close("all")
        print(f"  [OK] Visualisasi tersimpan: {output_path}")


# 6. Modul Orchestrator Time Series
def run_timeseries_pipeline(data_dir: Path = DATA_DIR, output_dir: Path = OUTPUT_DIR) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    agbd_files = sorted((data_dir / "agbd").glob("*.tif"))
    if not agbd_files:
        agbd_files = sorted(data_dir.glob("*.tif"))

    records = []
    for agbd_file in agbd_files:
        year_match = re.search(r"\d{4}", agbd_file.stem)
        year_tag = year_match.group(0) if year_match else None

        lc_candidate = None
        if year_tag:
            # Coba pola nama file dengan dan tanpa prefix tambahan
            for lc_pattern in (
                f"Landcover_{year_tag}.tif",
                f"Landcover_DW9_{year_tag}.tif",
            ):
                lc_path = data_dir / "landcover" / lc_pattern
                if lc_path.exists():
                    lc_candidate = lc_path
                    break

        hcs_grid, meta, year = process_single_year(agbd_file, lc_candidate, output_dir)
        t = meta.get("transform")
        px_ha = abs(t[0]) * abs(t[4]) / 10_000.0 if t is not None else 0.09

        for cls_id in range(7):
            count = int(np.count_nonzero(hcs_grid == cls_id))
            records.append({
                "Tahun": year,
                "Kelas_ID": cls_id,
                "Nama_Kelas": CLASS_LABELS[cls_id],
                "Status": HCS_STATUS[cls_id],
                "Piksel": count,
                "Luas_Ha": round(count * px_ha, 2),
            })

    df = pd.DataFrame(records)
    csv_path = output_dir / "HCS_TimeSeries_Statistics.csv"
    df.to_csv(csv_path, index=False)
    print(f"  [OK] Statistik CSV: {csv_path}")

    plot_timeseries_hcs(df, output_dir / "HCS_TimeSeries_Dashboard.png")
    return df


# 7. Eksekusi Utama
if __name__ == "__main__":
    df_result = run_timeseries_pipeline(DATA_DIR, OUTPUT_DIR)
    print("\nRingkasan Statistik Time Series:")
    print(df_result.pivot(index="Tahun", columns="Nama_Kelas", values="Luas_Ha"))