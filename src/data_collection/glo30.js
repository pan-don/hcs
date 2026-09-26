// -------------------------------------------------------------
// KONFIGURASI
// -------------------------------------------------------------
var SCALE = 30;
var EXPORT_PATH = 'users/sananta/';

var DW_INPUT_BANDS = [
  'water', 'trees', 'grass', 'flooded_vegetation',
  'crops', 'shrub_and_scrub', 'built', 'bare'
];

var DW_OUTPUT_BANDS = [
  'water', 'trees', 'grass', 'flooded_veg',
  'crops', 'shrub_scrub', 'built', 'bareland'
];

// -------------------------------------------------------------
// GEOMETRI SPASIAL
// -------------------------------------------------------------
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

var uniqueQuarters = ee.List(
  agbdTable.aggregate_array('year_quarter')
).distinct().sort();

// Diagnostik Awal
print('1. Jumlah Titik Input DW (agbdTable):', agbdTable.size());
print('2. Daftar Kuartal pada Titik Target:', uniqueQuarters);

// -------------------------------------------------------------
// PERHITUNGAN RENTANG WAKTU KUARTAL
// -------------------------------------------------------------
function getQuarterInterval(yqStr) {
  var str = ee.String(yqStr);
  var parts = str.split('_');
  var yearNum = ee.Number.parse(parts.get(0));
  var qStr = ee.String(parts.get(1));

  var startMonth = ee.Number(
    ee.Algorithms.If(
      qStr.equals('Q1'), 1,
      ee.Algorithms.If(
        qStr.equals('Q2'), 4,
        ee.Algorithms.If(
          qStr.equals('Q3'), 7, 10
        )
      )
    )
  );

  var startDate = ee.Date.fromYMD(yearNum, startMonth, 1);
  var endDate = startDate.advance(3, 'month');

  return { start: startDate, end: endDate };
}

// -------------------------------------------------------------
// PREPROCESSING KOLEKSI DYNAMIC WORLD V1
// -------------------------------------------------------------
var dwCollection = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
  .filterBounds(overallRegion)
  .select(DW_INPUT_BANDS);

print('3. Total Citra Dynamic World Terfilter:', dwCollection.size());

// Fallback overall jika ada kuartal yang kosong
var dwOverall = dwCollection.mean().resample('bilinear')
  .select(DW_INPUT_BANDS, DW_OUTPUT_BANDS);

// -------------------------------------------------------------
// EKSTRAKSI FITUR KUARTALAN DYNAMIC WORLD
// -------------------------------------------------------------
var quarterlyCollections = uniqueQuarters.map(function (yqStr) {
  yqStr = ee.String(yqStr);

  var quarterPoints = agbdTable.filter(
    ee.Filter.eq('year_quarter', yqStr)
  );

  var interval = getQuarterInterval(yqStr);

  var compositeQuarter = dwCollection
    .filterDate(interval.start, interval.end)
    .mean()
    .resample('bilinear')
    .select(DW_INPUT_BANDS, DW_OUTPUT_BANDS);

  // Fallback ke dwOverall jika kuartal kosong
  var composite = compositeQuarter.unmask(dwOverall);

  return composite.sampleRegions({
    collection: quarterPoints,
    scale: SCALE,
    geometries: true,
    tileScale: 4
  }).filter(ee.Filter.notNull(['trees']));
});

var finalDataset = ee.FeatureCollection(quarterlyCollections).flatten();

// Diagnostik Akhir
print('4. Jumlah Titik Final Master Dataset:', finalDataset.size());
print('5. Contoh Data Pertama Master Dataset:', finalDataset.first());

// -------------------------------------------------------------
// EKSPOR DATASET FINAL MULTIMODAL LENGKAP
// -------------------------------------------------------------
Export.table.toAsset({
  collection: finalDataset,
  description: 'GEDI_S2_S1_DEM_DW_Master_Dataset',
  assetId: EXPORT_PATH + 'gedi_master_multimodal_dataset'
});

Export.table.toDrive({
  collection: finalDataset,
  description: 'GEDI_S2_S1_DEM_DW_Master_Dataset',
  folder: 'Tugas Akhir',
  fileNamePrefix: 'gedi_master_multimodal_dataset',
  fileFormat: 'CSV'
});