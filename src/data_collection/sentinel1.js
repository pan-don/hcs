// =============================================================
// KONFIGURASI DAN KONSTANTA
// =============================================================
var SCALE = 30;
var GLCM_SIZE = 5;
var S1_ORBIT = 'DESCENDING';
var EXPORT_PATH = 'users/sananta/';

// =============================================================
// PEMULIHAN GEOMETRI SPASIAL & BOUNDING BOX
// =============================================================
var rawTable = typeof table !== 'undefined' ? table : ee.FeatureCollection([]);

var agbdTable = rawTable.map(function (f) {
  var lon = ee.Number(ee.Algorithms.If(f.get('longitude'), f.get('longitude'), f.get('Longitude')));
  var lat = ee.Number(ee.Algorithms.If(f.get('latitude'), f.get('latitude'), f.get('Latitude')));
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

// =============================================================
// FUNGSI: PERHITUNGAN RENTANG WAKTU KUARTAL
// =============================================================
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

// =============================================================
// FUNGSI: RADIOMETRIC TERRAIN FLATTENING (MULLISSA ET AL., 2021)
// =============================================================
var dem = ee.Image('USGS/SRTMGL1_003');
var terrain = ee.Terrain.products(dem);
var slope = terrain.select('slope').multiply(Math.PI / 180);
var aspect = terrain.select('aspect').multiply(Math.PI / 180);

function applyTerrainFlattening(image) {
  var isAscending = ee.String(image.get('orbitProperties_pass')).equals('ASCENDING');
  var heading = ee.Number(
    ee.Algorithms.If(isAscending, -106.0, -74.0)
  ).multiply(Math.PI / 180);

  var thetaInc = image.select('angle').multiply(Math.PI / 180);

  var cosLIA = thetaInc.cos().multiply(slope.cos())
    .add(thetaInc.sin().multiply(slope.sin()).multiply(aspect.subtract(heading).cos()));

  var ratio = cosLIA.divide(thetaInc.cos()).max(0.0001);

  var gamma0_VV = image.select('VV').subtract(
    ratio.log10().multiply(10)
  ).rename('VV');

  var gamma0_VH = image.select('VH').subtract(
    ratio.log10().multiply(10)
  ).rename('VH');

  return image.addBands([gamma0_VV, gamma0_VH], null, true);
}

// =============================================================
// FUNGSI: PREPARASI SENTINEL-1 KE SKALA LINIER
// =============================================================
function prepareSentinel1(image) {
  var flattened = applyTerrainFlattening(image);
  var linVV = ee.Image(10).pow(flattened.select('VV').divide(10)).rename('VV_lin');
  var linVH = ee.Image(10).pow(flattened.select('VH').divide(10)).rename('VH_lin');
  return linVV.addBands(linVH);
}

// =============================================================
// FUNGSI: SPECKLE FILTERING PADA HASIL KOMPOSIT (1 KALI SAJA)
// =============================================================
function applySpeckleFilterLinear(imageLin) {
  var vvFiltered = imageLin.select('VV_lin').reduceNeighborhood({
    reducer: ee.Reducer.mean(),
    kernel: ee.Kernel.square(1, 'pixels')
  });

  var vhFiltered = imageLin.select('VH_lin').reduceNeighborhood({
    reducer: ee.Reducer.mean(),
    kernel: ee.Kernel.square(1, 'pixels')
  });

  var vvDB = vvFiltered.log10().multiply(10).rename('VV');
  var vhDB = vhFiltered.log10().multiply(10).rename('VH');

  return ee.Image.cat([vvDB, vhDB]);
}

// =============================================================
// FUNGSI: EKSTRAKSI FITUR TEKSTUR GLCM
// =============================================================
function extractGLCM(image) {
  var vvByte = image.select('VV')
    .unitScale(-25.0, 0.0)
    .multiply(63)
    .toByte()
    .rename('VV');

  var vhByte = image.select('VH')
    .unitScale(-30.0, -5.0)
    .multiply(63)
    .toByte()
    .rename('VH');

  var vvGLCM = vvByte.glcmTexture({ size: GLCM_SIZE })
    .select(['VV_contrast', 'VV_ent', 'VV_corr']);

  var vhGLCM = vhByte.glcmTexture({ size: GLCM_SIZE })
    .select(['VH_contrast', 'VH_ent', 'VH_corr']);

  return image.addBands([vvGLCM, vhGLCM]);
}

// =============================================================
// TAHAP 1: PREPROCESSING KOLEKSI SENTINEL-1
// =============================================================
var s1Base = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filterBounds(overallRegion) // Optimasi: Bounding box tunggal
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
  .filter(ee.Filter.eq('instrumentMode', 'IW'));

var s1Collection = (S1_ORBIT === 'ALL')
  ? s1Base
  : s1Base.filter(ee.Filter.eq('orbitProperties_pass', S1_ORBIT));

var s1Preprocessed = s1Collection
  .select(['VV', 'VH', 'angle'])
  .map(prepareSentinel1);

print('3. Total Citra Sentinel-1 Terfilter:', s1Preprocessed.size());
var s1OverallLin = s1Preprocessed.median();

// =============================================================
// TAHAP 2: EKSTRAKSI FITUR KUARTALAN SENTINEL-1
// =============================================================
var quarterlyCollections = uniqueQuarters.map(function (yqStr) {
  yqStr = ee.String(yqStr);

  var quarterPoints = agbdTable.filter(
    ee.Filter.eq('year_quarter', yqStr)
  );

  var interval = getQuarterInterval(yqStr);
  var s1QuarterMedianLin = s1Preprocessed
    .filterDate(interval.start, interval.end)
    .median()
    .unmask(s1OverallLin);

  var s1FilteredDB = applySpeckleFilterLinear(s1QuarterMedianLin);
  var s1Composite = extractGLCM(s1FilteredDB)
    .resample('bilinear')
    .select([
      'VV', 'VH',
      'VV_contrast', 'VV_ent', 'VV_corr',
      'VH_contrast', 'VH_ent', 'VH_corr'
    ], [
      's1_vv', 's1_vh',
      's1_vv_contrast', 's1_vv_ent', 's1_vv_corr',
      's1_vh_contrast', 's1_vh_ent', 's1_vh_corr'
    ]);

  return s1Composite.sampleRegions({
    collection: quarterPoints,
    scale: SCALE,
    geometries: true,
    tileScale: 4
  }).filter(ee.Filter.notNull(['s1_vv', 's1_vh']));
});

var finalDataset = ee.FeatureCollection(quarterlyCollections).flatten();
print('4. Contoh Data Pertama:', finalDataset.first());

// =============================================================
// TAHAP 3: EKSPOR DATASET GEDI + SENTINEL-2 + SENTINEL-1
// =============================================================
Export.table.toAsset({
  collection: finalDataset,
  description: 'GEDI_S2_S1_Combined_Dataset',
  assetId: EXPORT_PATH + 'gedi_s2_s1_combined'
});