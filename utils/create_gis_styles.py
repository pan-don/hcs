"""
create_gis_styles.py
====================
Utility mandiri untuk menghasilkan file styling QGIS (.qml) dan ArcGIS (.clr)
untuk peta keputusan zonasi HCSA (HCSA_Final_Decision_Map_*.tif).
"""

from pathlib import Path

QML_TEMPLATE = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
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
        <paletteEntry value="1" color="#1b5e20" alpha="255" label="1: HCS Konservasi (Conserve)"/>
        <paletteEntry value="2" color="#7cb342" alpha="255" label="2: HCS Koridor (Corridor)"/>
        <paletteEntry value="3" color="#fb8c00" alpha="255" label="3: HCS Kaji Lapangan / Pre-RBA (Assess)"/>
        <paletteEntry value="4" color="#ffee58" alpha="255" label="4: Indikasi Layak Dikembangkan (Developable)"/>
        <paletteEntry value="5" color="#b0bec5" alpha="255" label="5: Non-Vegetasi / Non-Target"/>
      </colorPalette>
    </rasterrenderer>
    <brightnesscontrast brightness="0" contrast="0"/>
    <huesaturation colorizeGreen="128" colorizeOn="0" colorizeRed="255" colorizeBlue="128" grayscaleMode="0" saturation="0" colorizeStrength="100"/>
    <rasterresampler maxOversampling="2"/>
  </pipe>
  <blendMode>0</blendMode>
</qgis>
"""

CLR_CONTENT = """1 27 94 32 255 HCS Konservasi (Conserve)
2 124 179 66 255 HCS Koridor (Corridor)
3 251 140 0 255 HCS Kaji Lapangan / Pre-RBA (Assess)
4 255 238 88 255 Indikasi Layak Dikembangkan (Developable)
5 176 190 197 255 Non-Vegetasi / Non-Target
"""


def generate_styles(base_dir: Path = Path("output/patch_analysis"), start_year: int = 2021, end_year: int = 2025) -> None:
    for yr in range(start_year, end_year + 1):
        dir_yr = base_dir / str(yr)
        if dir_yr.exists():
            tif_name = f"HCSA_Final_Decision_Map_{yr}"
            (dir_yr / f"{tif_name}.qml").write_text(QML_TEMPLATE, encoding="utf-8")
            (dir_yr / f"{tif_name}.clr").write_text(CLR_CONTENT, encoding="utf-8")
            print(f"[OK] Berhasil membuat style GIS untuk tahun {yr} di {dir_yr}")


if __name__ == "__main__":
    generate_styles()
