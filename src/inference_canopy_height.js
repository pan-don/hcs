// -------------------------------------------------------------
// 1. KONFIGURASI GLOBAL
// -------------------------------------------------------------
var CFG = {
  MODEL_ASSET: 'users/sananta/rf_canopy_height_model',
  maskNonVegetation: false,
  years: [2021, 2022, 2023, 2024, 2025],
  scale: 30,
  crs: 'EPSG:32648',
  s1Orbit: 'DESCENDING',
  csThreshold: 0.60,
  maxCloudPct: 70,
  glcmSize: 5,
  exportPath: 'users/sananta/',
  exportFileName: 'Canopy_Height_RH98_Prediction',
  exportDriveFolder: 'GEE_Exports',
  exportMaxPixels: 1e13,
  features: [
    'b2', 'b3', 'b4', 'b5', 'b6', 'b7', 'b8', 'b11', 'b12',
    'ndvi', 'gndvi', 'evi', 'ireci', 'rvi', 'gao_ndwi',
    'vv', 'vh',
    'vv_cont', 'vv_ent', 'vv_corr',
    'vh_cont', 'vh_ent', 'vh_corr',
    'dem', 'slope', 'aspect',
    'water', 'trees', 'grass', 'flooded_veg',
    'crops', 'shrub_scrub', 'built', 'bareland'
  ]
};

var aoi = typeof geometry !== 'undefined' ? geometry : Map.getBounds(true);
// -------------------------------------------------------------
// 2. LOAD MODEL RANDOM FOREST DARI ASSET
// -------------------------------------------------------------
var rfModel = ee.Classifier.load(CFG.MODEL_ASSET);
print('1. Status Model: Berhasil dimuat dari Asset (' + CFG.MODEL_ASSET + ')');

// -------------------------------------------------------------
// 3. PRA-PEMROSESAN SENTINEL-2 MULTISPEKTRAL
// -------------------------------------------------------------
function calculateSpectralIndices(image) {
  var blue = image.select('B2');
  var green = image.select('B3');
  var red = image.select('B4');
  var re1 = image.select('B5');
  var re2 = image.select('B6');
  var re3 = image.select('B7');
  var nir = image.select('B8');
  var swir1 = image.select('B11');

  var ndvi = nir.subtract(red).divide(nir.add(red)).rename('ndvi');
  var gndvi = nir.subtract(green).divide(nir.add(green)).rename('gndvi');
  var evi = image.expression(
    '2.5 * ((NIR - RED) / (NIR + 6.0 * RED - 7.5 * BLUE + 1.0))',
    { NIR: nir, RED: red, BLUE: blue }
  ).rename('evi');
  var ireci = image.expression(
    '(RE3 - RED) / (RE1 / RE2)',
    { RE3: re3, RED: red, RE1: re1, RE2: re2 }
  ).rename('ireci');
  var rvi = nir.divide(red).rename('rvi');
  var gaoNdwi = nir.subtract(swir1).divide(nir.add(swir1)).rename('gao_ndwi');

  return image.addBands([ndvi, gndvi, evi, ireci, rvi, gaoNdwi]);
}

function prepareSentinel2(image) {
  var opticalBands = ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B11', 'B12'];
  var scaled = image.select(opticalBands).multiply(0.0001);
  var clearMask = image.select('cs').gte(CFG.csThreshold);
  return image.addBands(scaled, null, true).updateMask(clearMask).select(opticalBands);
}

var s2Baseline = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(aoi)
  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', CFG.maxCloudPct))
  .linkCollection(ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'), ['cs'])
  .map(prepareSentinel2)
  .map(calculateSpectralIndices)
  .median();

function buildS2Composite(year, region) {
  var start = year + '-01-01';
  var end = year + '-12-31';

  var s2Col = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(region)
    .filterDate(start, end)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', CFG.maxCloudPct))
    .linkCollection(ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED'), ['cs'])
    .map(prepareSentinel2)
    .map(calculateSpectralIndices);

  var s2Median = s2Col.median().unmask(s2Baseline);

  return s2Median
    .resample('bilinear')
    .select(
      ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B11', 'B12',
        'ndvi', 'gndvi', 'evi', 'ireci', 'rvi', 'gao_ndwi'],
      ['b2', 'b3', 'b4', 'b5', 'b6', 'b7', 'b8', 'b11', 'b12',
        'ndvi', 'gndvi', 'evi', 'ireci', 'rvi', 'gao_ndwi']
    );
}

// -------------------------------------------------------------
// 4. PRA-PEMROSESAN SENTINEL-1 SAR
// -------------------------------------------------------------
var s1Dem = ee.Image('USGS/SRTMGL1_003');
var s1Terrain = ee.Terrain.products(s1Dem);
var s1Slope = s1Terrain.select('slope').multiply(Math.PI / 180);
var s1Aspect = s1Terrain.select('aspect').multiply(Math.PI / 180);

function applyTerrainFlattening(image) {
  var isAscending = ee.String(image.get('orbitProperties_pass')).equals('ASCENDING');
  var heading = ee.Number(ee.Algorithms.If(isAscending, -106.0, -74.0)).multiply(Math.PI / 180);
  var thetaInc = image.select('angle').multiply(Math.PI / 180);
  var cosLIA = thetaInc.cos().multiply(s1Slope.cos())
    .add(thetaInc.sin().multiply(s1Slope.sin()).multiply(s1Aspect.subtract(heading).cos()));
  var ratio = cosLIA.divide(thetaInc.cos()).max(0.0001);
  var gamma0_VV = image.select('VV').subtract(ratio.log10().multiply(10)).rename('VV');
  var gamma0_VH = image.select('VH').subtract(ratio.log10().multiply(10)).rename('VH');
  return image.addBands([gamma0_VV, gamma0_VH], null, true);
}

function prepareS1Linear(image) {
  var flattened = applyTerrainFlattening(image);
  var linVV = ee.Image(10).pow(flattened.select('VV').divide(10)).rename('VV_lin');
  var linVH = ee.Image(10).pow(flattened.select('VH').divide(10)).rename('VH_lin');
  return linVV.addBands(linVH);
}

function applySpeckleFilterLinear(imageLin) {
  var vvFiltered = imageLin.select('VV_lin').reduceNeighborhood({
    reducer: ee.Reducer.mean(),
    kernel: ee.Kernel.square(1, 'pixels')
  });
  var vhFiltered = imageLin.select('VH_lin').reduceNeighborhood({
    reducer: ee.Reducer.mean(),
    kernel: ee.Kernel.square(1, 'pixels')
  });
  return ee.Image.cat([
    vvFiltered.log10().multiply(10).rename('VV'),
    vhFiltered.log10().multiply(10).rename('VH')
  ]);
}

function extractS1GLCM(image) {
  var vvByte = image.select('VV').unitScale(-25.0, 0.0).multiply(63).toByte().rename('VV');
  var vhByte = image.select('VH').unitScale(-30.0, -5.0).multiply(63).toByte().rename('VH');

  var vvGLCM = vvByte.glcmTexture({ size: CFG.glcmSize })
    .select(['VV_contrast', 'VV_ent', 'VV_corr']);
  var vhGLCM = vhByte.glcmTexture({ size: CFG.glcmSize })
    .select(['VH_contrast', 'VH_ent', 'VH_corr']);

  return image.addBands([vvGLCM, vhGLCM]);
}

var s1Baseline = ee.ImageCollection('COPERNICUS/S1_GRD')
  .filterBounds(aoi)
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
  .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
  .filter(ee.Filter.eq('instrumentMode', 'IW'))
  .filter(ee.Filter.eq('orbitProperties_pass', CFG.s1Orbit))
  .select(['VV', 'VH', 'angle'])
  .map(prepareS1Linear)
  .median();

function buildS1Composite(year, region) {
  var start = year + '-01-01';
  var end = year + '-12-31';

  var s1Col = ee.ImageCollection('COPERNICUS/S1_GRD')
    .filterBounds(region)
    .filterDate(start, end)
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    .filter(ee.Filter.eq('orbitProperties_pass', CFG.s1Orbit))
    .select(['VV', 'VH', 'angle'])
    .map(prepareS1Linear);

  var s1LinMedian = s1Col.median().unmask(s1Baseline);
  var s1FilteredDB = applySpeckleFilterLinear(s1LinMedian);

  return extractS1GLCM(s1FilteredDB)
    .resample('bilinear')
    .select(
      ['VV', 'VH', 'VV_contrast', 'VV_ent', 'VV_corr', 'VH_contrast', 'VH_ent', 'VH_corr'],
      ['vv', 'vh', 'vv_cont', 'vv_ent', 'vv_corr', 'vh_cont', 'vh_ent', 'vh_corr']
    );
}

// -------------------------------------------------------------
// 5. PRA-PEMROSESAN COPERNICUS GLO-30 DEM
// -------------------------------------------------------------
function buildDEMBands(region) {
  var collection = ee.ImageCollection('COPERNICUS/DEM/GLO30').filterBounds(region);
  var nativeProj = collection.first().projection();
  var dem = collection.select('DEM').mosaic().setDefaultProjection(nativeProj).rename('dem');
  var terrain = ee.Terrain.products(dem.reproject({ crs: CFG.crs, scale: CFG.scale }));
  return dem
    .addBands(terrain.select('slope').rename('slope'))
    .addBands(terrain.select('aspect').rename('aspect'))
    .resample('bilinear');
}

// -------------------------------------------------------------
// 6. PRA-PEMROSESAN DYNAMIC WORLD
// -------------------------------------------------------------
var DW_INPUT_BANDS = ['water', 'trees', 'grass', 'flooded_vegetation', 'crops', 'shrub_and_scrub', 'built', 'bare'];
var DW_OUTPUT_BANDS = ['water', 'trees', 'grass', 'flooded_veg', 'crops', 'shrub_scrub', 'built', 'bareland'];

var dwBaseline = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
  .filterBounds(aoi)
  .select(DW_INPUT_BANDS)
  .mean()
  .resample('bilinear')
  .select(DW_INPUT_BANDS, DW_OUTPUT_BANDS);

function buildDWComposite(year, region) {
  var start = year + '-01-01';
  var end = year + '-12-31';
  var dwCol = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
    .filterBounds(region).filterDate(start, end).select(DW_INPUT_BANDS);
  return dwCol.mean().resample('bilinear')
    .select(DW_INPUT_BANDS, DW_OUTPUT_BANDS)
    .unmask(dwBaseline);
}

function buildVegetationMask(year, region) {
  var start = year + '-01-01';
  var end = year + '-12-31';
  var dwCol = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1').filterBounds(region);
  var dwYear = dwCol.filterDate(start, end).select('label').mode();
  var dwOverall = dwCol.select('label').mode();
  var label = dwYear.unmask(dwOverall);
  return label.gte(1).and(label.lte(5));
}

// -------------------------------------------------------------
// 7. STACK FITUR DAN INFERENSI MODEL
// -------------------------------------------------------------
function buildFeatureStack(s2, s1, dem, dw, region) {
  return s2.addBands(s1).addBands(dem).addBands(dw).clip(region).select(CFG.features);
}

function runInference(featureStack, vegMask, region) {
  var stack = (CFG.maskNonVegetation && vegMask) ? featureStack.updateMask(vegMask) : featureStack;
  var prediction = stack.classify(rfModel).max(0);
  var finalPrediction = (CFG.maskNonVegetation && vegMask) ? prediction.unmask(0) : prediction;
  return finalPrediction.clip(region).rename('canopy_height_predicted');
}

// -------------------------------------------------------------
// 8. VISUALISASI DAN EKSPOR
// -------------------------------------------------------------
function visualizeResults(prediction, region, year) {
  var chViz = {
    min: 0,
    max: 40,
    palette: ['#ffffcc', '#c7e9b4', '#7fcdbb', '#41b6c4', '#2c7fb8', '#253494']
  };

  Map.centerObject(region, 10);
  Map.addLayer(ee.Image().paint(region, 0, 2), { palette: ['#ff0000'] }, 'Batas AOI');
  Map.addLayer(prediction, chViz, 'Canopy Height RH98 ' + year + ' (m)');

  var legend = ui.Panel({
    style: { position: 'bottom-left', padding: '8px 12px', backgroundColor: 'rgba(255,255,255,0.9)' }
  });
  legend.add(ui.Label({
    value: 'Canopy Height RH98 (m)',
    style: { fontWeight: 'bold', fontSize: '13px', margin: '0 0 6px 0' }
  }));
  ['#ffffcc', '#c7e9b4', '#7fcdbb', '#41b6c4', '#2c7fb8', '#253494'].forEach(function (col, i) {
    legend.add(ui.Panel([
      ui.Label('', { backgroundColor: col, padding: '8px', margin: '2px 6px 2px 0' }),
      ui.Label(['0', '8', '16', '24', '32', '40'][i] + ' m', { fontSize: '11px', margin: '2px 0' })
    ], ui.Panel.Layout.flow('horizontal')));
  });
  Map.add(legend);
}

function exportPrediction(prediction, region, year) {
  var fileName = CFG.exportFileName + '_' + year;
  var meta = prediction.set({
    'model': CFG.MODEL_ASSET,
    'year': year,
    'scale_m': CFG.scale,
    'unit': 'meter'
  });

  Export.image.toAsset({
    image: meta,
    description: fileName,
    assetId: CFG.exportPath + fileName,
    region: region,
    scale: CFG.scale,
    crs: CFG.crs,
    maxPixels: CFG.exportMaxPixels
  });

  Export.image.toDrive({
    image: meta,
    description: fileName + '_Drive',
    folder: CFG.exportDriveFolder,
    fileNamePrefix: fileName,
    region: region,
    scale: CFG.scale,
    crs: CFG.crs,
    maxPixels: CFG.exportMaxPixels
  });

  print('   -> Task Ekspor Terdaftar: ' + fileName);
}

// -------------------------------------------------------------
// 9. PIPELINE UTAMA (MULTI-YEAR INFERENCE)
// -------------------------------------------------------------
(function main() {
  print('2. Inisialisasi Inferensi Canopy Height Multi-Tahun (2021-2025)...');
  print('   - Total Fitur Input:', CFG.features.length);
  print('   - Orbit Sentinel-1 :', CFG.s1Orbit);
  print('   - CRS / Skala      :', CFG.crs, '/', CFG.scale, 'm');
  print('   - Tahun Pemrosesan :', CFG.years);
  print('   - Mask Non-Vegetasi:', CFG.maskNonVegetation ? 'Aktif' : 'Nonaktif');

  var dem = buildDEMBands(aoi);

  CFG.years.forEach(function (year) {
    print('Memproses Tahun: ' + year + '...');

    var s2 = buildS2Composite(year, aoi);
    var s1 = buildS1Composite(year, aoi);
    var dw = buildDWComposite(year, aoi);
    var vegMask = CFG.maskNonVegetation ? buildVegetationMask(year, aoi) : null;

    var stack = buildFeatureStack(s2, s1, dem, dw, aoi);
    var prediction = runInference(stack, vegMask, aoi);

    exportPrediction(prediction, aoi, year);

    if (year === CFG.years[CFG.years.length - 1]) {
      visualizeResults(prediction, aoi, year);
    }
  });

  print('3. Seluruh Task Inferensi Terdaftar. Buka tab "Tasks" untuk menjalankan Run.');
})();
