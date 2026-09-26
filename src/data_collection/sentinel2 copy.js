// -------------------------------------------------------------
// KONFIGURASI
// -------------------------------------------------------------
var SCALE = 30;
var PROJECTION = 'EPSG:32648';
var CS_THRESHOLD = 0.60;
var GLCM_SIZE = 5;
var EXPORT_PATH = 'users/sananta/';

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

print('1. Jumlah Titik Input (agbdTable):', agbdTable.size());
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
// PERHITUNGAN INDEKS VEGETASI SENTINEL-2
// -------------------------------------------------------------
function calculateSpectralIndices(image) {
  var blue = image.select('B2');
  var red = image.select('B4');
  var re1 = image.select('B5');
  var re2 = image.select('B6');
  var re3 = image.select('B7');
  var nir = image.select('B8');
  var swir1 = image.select('B11');

  var ndvi = nir.subtract(red).divide(nir.add(red)).rename('ndvi');

  var evi = image.expression(
    '2.5 * ((NIR - RED) / (NIR + 6.0 * RED - 7.5 * BLUE + 1.0))',
    { NIR: nir, RED: red, BLUE: blue }
  ).rename('evi');

  var ndre = nir.subtract(re1).divide(nir.add(re1)).rename('ndre');

  var ireci = image.expression(
    '(RE3 - RED) / (RE1 / RE2)',
    { RE3: re3, RED: red, RE1: re1, RE2: re2 }
  ).rename('ireci');

  var gaoNdwi = nir.subtract(swir1).divide(nir.add(swir1)).rename('gao_ndwi');

  return image.addBands([ndvi, evi, ndre, ireci, gaoNdwi]);
}

// -------------------------------------------------------------
// MASKING AWAN DAN RESCALING REFLEKTANSI
// -------------------------------------------------------------
function prepareSentinel2(image) {
  var opticalBands = ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B11', 'B12'];
  var scaled = image.select(opticalBands).multiply(0.0001);
  var clearMask = image.select('cs').gte(CS_THRESHOLD);

  return image.addBands(scaled, null, true)
    .updateMask(clearMask)
    .select(opticalBands);
}

// -------------------------------------------------------------
// EKSTRAKSI TEKSTUR GLCM SENTINEL-2
// -------------------------------------------------------------
function extractS2GLCM(image) {
  var ireciBins = image.select('ireci')
    .unitScale(0.0, 1.2)
    .multiply(63)
    .toByte()
    .rename('ireci');

  var swirBins = image.select('B11')
    .unitScale(0.02, 0.35)
    .multiply(63)
    .toByte()
    .rename('swir');

  var ireciGLCM = ireciBins.glcmTexture({ size: GLCM_SIZE })
    .select(['ireci_contrast', 'ireci_ent', 'ireci_corr'], ['ireci_cont', 'ireci_ent', 'ireci_corr']);

  var swirGLCM = swirBins.glcmTexture({ size: GLCM_SIZE })
    .select(['swir_contrast', 'swir_ent', 'swir_corr'], ['swir_cont', 'swir_ent', 'swir_corr']);

  return image.addBands([ireciGLCM, swirGLCM]);
}

// -------------------------------------------------------------
// PREPROCESSING KOLEKSI SENTINEL-2
// -------------------------------------------------------------
var s2Collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(overallRegion)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 70))
  .linkCollection(
    ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'),
    ['cs']
  )
  .map(prepareSentinel2)
  .map(calculateSpectralIndices);

print('3. Total Citra Sentinel-2 Terfilter:', s2Collection.size());

var s2Overall = s2Collection.median();

// -------------------------------------------------------------
// EKSTRAKSI FITUR KUARTALAN SENTINEL-2
// -------------------------------------------------------------
var quarterlyCollections = uniqueQuarters.map(function (yqStr) {
  yqStr = ee.String(yqStr);

  var quarterPoints = agbdTable.filter(
    ee.Filter.eq('year_quarter', yqStr)
  );

  var interval = getQuarterInterval(yqStr);

  var s2Median = s2Collection
    .filterDate(interval.start, interval.end)
    .median()
    .unmask(s2Overall);

  var composite = extractS2GLCM(s2Median)
    .resample('bilinear')
    .select([
      'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B11', 'B12',
      'ndvi', 'evi', 'ndre', 'ireci', 'gao_ndwi',
      'ireci_cont', 'ireci_ent', 'ireci_corr',
      'swir_cont', 'swir_ent', 'swir_corr'
    ], [
      'b2', 'b3', 'b4', 'b5', 'b6', 'b7', 'b8', 'b11', 'b12',
      'ndvi', 'evi', 'ndre', 'ireci', 'gao_ndwi',
      'ireci_cont', 'ireci_ent', 'ireci_corr',
      'swir_cont', 'swir_ent', 'swir_corr'
    ]);

  return composite.sampleRegions({
    collection: quarterPoints,
    scale: SCALE,
    geometries: true,
    tileScale: 4
  }).filter(ee.Filter.notNull(['ndvi', 'ireci', 'ndre']));
});

var finalDataset = ee.FeatureCollection(quarterlyCollections).flatten();

print('4. Jumlah Titik Hasil Ekstraksi S2 (finalDataset):', finalDataset.size());
print('5. Contoh Data Pertama S2:', finalDataset.first());

// -------------------------------------------------------------
// EKSPOR DATASET GEDI + SENTINEL-2
// -------------------------------------------------------------
Export.table.toAsset({
  collection: finalDataset,
  description: 'GEDI_S2_Combined_Dataset',
  assetId: EXPORT_PATH + 'gedi_s2_combined'
});