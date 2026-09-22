# ==========================================================
# IMPORT LIBRARY
# ==========================================================
import os
import shutil
import time
import geopandas as gpd
import numpy as np
from shapely.geometry import Polygon
import matplotlib.pyplot as plt
import zipfile

# ==========================================================
# FUNGSI: BUAT SATU HEXAGON DARI TITIK PUSAT
# ==========================================================
def create_hexagon(center_x, center_y, radius):
    angles = np.deg2rad(np.arange(30, 390, 60))
    x = center_x + radius * np.cos(angles)
    y = center_y + radius * np.sin(angles)
    return Polygon(zip(x, y))


# ==========================================================
# FUNGSI: GENERATE HEXAGONAL GRID DALAM BOUNDING BOX
# ==========================================================
def generate_hex_grid(bounds, diameter):
    radius = diameter / 2
    width = radius * np.sqrt(3)
    height = radius * 1.5

    xmin, ymin, xmax, ymax = bounds

    cols = np.arange(xmin, xmax + width, width)
    rows = np.arange(ymin, ymax + height, height)

    hexagons = []
    hex_ids = []

    for row_idx, y in enumerate(rows):
        x_offset = width / 2 if row_idx % 2 else 0
        for x in cols:
            cx = x + x_offset
            hexagons.append(create_hexagon(cx, y, radius))
            hex_ids.append(f"HEX_{int(cx)}_{int(y)}")

    return gpd.GeoDataFrame(
        {"hex_id": hex_ids, "geometry": hexagons}
    )


# ==========================================================
# FUNGSI: CLIP GRID KE BATAS ADMINISTRASI (SPATIAL INDEX)
# ==========================================================
def clip_grid_to_boundary(hex_grid, boundary_gdf, crs):
    hex_grid = hex_grid.set_crs(crs)
    boundary_proj = boundary_gdf.to_crs(crs)
    boundary_union = boundary_proj.union_all()
    mask = hex_grid.intersects(boundary_union)
    clipped = hex_grid[mask].reset_index(drop=True)
    clipped = clipped.drop_duplicates(subset="hex_id").reset_index(drop=True)
    return clipped


# ==========================================================
# FUNGSI: SIMPAN SHAPEFILE + ZIP UNTUK UPLOAD GEE
# ==========================================================
def save_as_shapefile_for_gee(gdf, output_dir, layer_name):
    os.makedirs(output_dir, exist_ok=True)
    shp_path = os.path.join(output_dir, f"{layer_name}.shp")
    gdf.to_file(shp_path, driver="ESRI Shapefile", engine="pyogrio")
    zip_path = os.path.join(output_dir, f"{layer_name}.zip")
    exts = [".shp", ".shx", ".dbf", ".prj", ".cpg"]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for ext in exts:
            component = os.path.join(output_dir, f"{layer_name}{ext}")
            if os.path.exists(component):
                zf.write(component, arcname=f"{layer_name}{ext}")
    return shp_path, zip_path


# ==========================================================
# FUNGSI: PIPELINE UTAMA
# ==========================================================
def build_hex_grid_for_riau(shapefile_path, diameter, crs, output_dir, layer_name):
    boundary = gpd.read_file(shapefile_path, engine="pyogrio")
    boundary_proj = boundary.to_crs(crs)

    bounds = boundary_proj.total_bounds
    raw_grid = generate_hex_grid(bounds, diameter)

    clipped_grid = clip_grid_to_boundary(raw_grid, boundary, crs)
    clipped_grid = clipped_grid.to_crs(epsg=4326)

    shp_path, zip_path = save_as_shapefile_for_gee(clipped_grid, output_dir, layer_name)

    return clipped_grid, shp_path, zip_path


# ==========================================================
# FUNGSI: PLOT OVERLAY HEXAGONAL GRID DI ATAS BATAS RIAU
# ==========================================================
def plot_hex_grid_overlay(hex_grid, boundary_gdf, output_image=None):
    boundary_wgs = boundary_gdf.to_crs(epsg=4326)

    fig, ax = plt.subplots(figsize=(10, 6))
    boundary_wgs.plot(ax=ax, facecolor="none", edgecolor="black", linewidth=1.2, zorder=2)
    hex_grid.plot(ax=ax, facecolor="none", edgecolor="orangered", linewidth=0.5, zorder=1)
    ax.set_title("Hexagonal Grid Overlay", fontsize=13)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    plt.tight_layout()

    if output_image:
        plt.savefig(output_image, dpi=300)

    plt.show()


# ==========================================================
# EKSEKUSI
# ==========================================================
if __name__ == "__main__":
    SHAPEFILE_PATH = "data/shp/bogor_administrasi_kabkota.shp"
    HEX_DIAMETER = 1000
    CRS_PROJECTED = "EPSG:32648"
    OUTPUT_DIR = "data/grid"
    LAYER_NAME = "hexgrid_bogor"

    t0 = time.time()

    result_grid, shp_path, zip_path = build_hex_grid_for_riau(
        SHAPEFILE_PATH, HEX_DIAMETER, CRS_PROJECTED, OUTPUT_DIR, LAYER_NAME
    )

    print(f"Waktu proses: {time.time() - t0:.2f} detik")
    print(f"Jumlah hexagon dihasilkan: {len(result_grid)}")
    print(f"Shapefile disimpan di: {shp_path}")
    print(f"File ZIP untuk upload GEE: {zip_path}")

    boundary_gdf = gpd.read_file(SHAPEFILE_PATH, engine="pyogrio")
    plot_hex_grid_overlay(result_grid, boundary_gdf, output_image="assets/hexgrid_plot.png")