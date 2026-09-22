// =============================================================
// KONFIGURASI DAN KONSTANTA
// =============================================================
var SCALE = 30;
var PROJECTION = 'EPSG:32648';
var EXPORT_PATH = 'users/sananta/';

// =============================================================
// PEMULIHAN GEOMETRI SPASIAL (JIKA INPUT DARI CSV / ASSET)
// =============================================================
var rawTable = typeof table !== 'undefined' ? table : ee.FeatureCollection([]);

var agbdTable = rawTable.map(function (f) {
  var lon = ee.Number(f.get('longitude'));
  var lat = ee.Number(f.get('latitude'));
  var reconstructedGeom = ee.Geometry.Point([lon, lat]);
  var geom = ee.Algorithms.If(
    f.geometry(),
    f.geometry(),
    reconstructedGeom
  );
  return ee.Feature(ee.Geometry(geom), f.toDictionary());
});

var overallRegion = agbdTable.geometry().bounds();

print('1. Jumlah Titik Input (agbdTable):', agbdTable.size());

// =============================================================
// TAHAP 1: PREPROCESSING COPERNICUS GLO-30 DEM
// =============================================================
var collection = ee.ImageCollection('COPERNICUS/DEM/GLO30')
  .filterBounds(overallRegion);

var nativeProj = collection.first().projection();

var dem = collection
  .select('DEM')
  .mosaic()
  .setDefaultProjection(nativeProj)
  .rename('dem');

var terrain = ee.Terrain.products(
  dem.reproject({ crs: PROJECTION, scale: SCALE })
);

var demBands = dem
  .addBands(terrain.select('slope').rename('slope'))
  .addBands(terrain.select('aspect').rename('aspect'))
  .resample('bilinear');

// =============================================================
// TAHAP 2: EKSTRAKSI FITUR TOPOGRAFI
// =============================================================
var finalDataset = demBands.sampleRegions({
  collection: agbdTable,
  scale: SCALE,
  geometries: true,
  tileScale: 4
}).filter(ee.Filter.notNull(['dem', 'slope', 'aspect']));

print('2. Jumlah Titik Output DEM (finalDataset):', finalDataset.size());
print('3. Contoh Data Pertama DEM:', finalDataset.first());

// =============================================================
// TAHAP 3: EKSPOR DATASET GEDI + S2 + S1 + DEM
// =============================================================
Export.table.toAsset({
  collection: finalDataset,
  description: 'GEDI_S2_S1_DEM_Combined_Dataset',
  assetId: EXPORT_PATH + 'gedi_s2_s1_dem_combined'
});