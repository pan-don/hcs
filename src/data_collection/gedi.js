// ------------------------------------------------------------------------------
// KONFIGURASI
// ------------------------------------------------------------------------------
var SCALE = 30;
var PROJECTION = 'EPSG:32648';
var START_DATE = ee.Date('2024-04-25');
var END_DATE = ee.Date('2025-07-01');
var EXPORT_PATH = 'users/sananta/';
var OUTPUT_PROPS = ['agbd', 'agbd_se', 'rh98', 'longitude', 'latitude', 'year_quarter', 'hex_id'];
var proj = ee.Projection(PROJECTION);

var MAX_SAMPLES_PER_HEX = 100;
var RANDOM_SEED = 42;
var MIN_SENSITIVITY = 0.90;
var MASK_NON_VEGETATION = false;
var INCLUDE_BARE_SAMPLES = false;
var MAX_BARE_POINTS_PER_HEX = 10;

// ------------------------------------------------------------------------------
// FUNGSI HELPER
// ------------------------------------------------------------------------------
function getQuarterInterval(yqStr) {
  var parts = ee.String(yqStr).split('_');
  var yearNum = ee.Number.parse(parts.get(0));
  var qStr = ee.String(parts.get(1));
  var startMonth = ee.Number(
    ee.Algorithms.If(qStr.equals('Q1'), 1,
      ee.Algorithms.If(qStr.equals('Q2'), 4,
        ee.Algorithms.If(qStr.equals('Q3'), 7, 10)))
  );
  var startDate = ee.Date.fromYMD(yearNum, startMonth, 1);
  return { start: startDate, end: startDate.advance(3, 'month') };
}

function limitSamplesPerGrid(collection, maxPerGrid, seed) {
  if (!maxPerGrid || maxPerGrid <= 0) {
    return collection;
  }

  var withRandom = collection.randomColumn('rand_sample', seed);
  var uniqueHex = withRandom.distinct(['hex_id']);

  var join = ee.Join.saveAll({
    matchesKey: 'samples',
    ordering: 'rand_sample',
    ascending: true
  });

  var filter = ee.Filter.equals({
    leftField: 'hex_id',
    rightField: 'hex_id'
  });

  var joined = join.apply({
    primary: uniqueHex,
    secondary: withRandom,
    condition: filter
  });

  var limited = joined.map(function (feat) {
    var samplesList = ee.List(feat.get('samples'));
    var sliced = samplesList.slice(0, maxPerGrid);
    return ee.FeatureCollection(sliced);
  }).flatten();

  return limited;
}

// ------------------------------------------------------------------------------
// INPUT AOI DAN STANDARISASI HEXAGON GRID
// ------------------------------------------------------------------------------
var aoiGeom;
if (typeof aoi !== 'undefined') {
  aoiGeom = aoi.geometry();
} else if (typeof geometry !== 'undefined') {
  aoiGeom = (typeof geometry.geometry === 'function') ? geometry.geometry() : geometry;
} else {
  aoiGeom = Map.getBounds(true);
}

var hexGridInput;
if (typeof hexgrid !== 'undefined') {
  hexGridInput = hexgrid;
} else if (typeof aoi !== 'undefined') {
  hexGridInput = aoi;
} else {
  hexGridInput = ee.FeatureCollection([ee.Feature(aoiGeom, { hex_id: 'HEX_0' })]);
}

var hexGridClean = hexGridInput.map(function (cell) {
  var hexKey = ee.Algorithms.If(
    cell.get('hex_id'), cell.get('hex_id'),
    ee.Algorithms.If(cell.get('HEX_ID'), cell.get('HEX_ID'),
      ee.String('HEX_').cat(cell.id()))
  );
  return ee.Feature(cell.geometry(), { hex_id: ee.String(hexKey) });
});

var lonLat = ee.Image.pixelLonLat();

// ------------------------------------------------------------------------------
// FILTER KUALITAS GEDI L4A (AGBD) & L2A (RH98)
// ------------------------------------------------------------------------------
// GEDI L4A: AGBD dan agbd_se
var gediL4aMasked = ee.ImageCollection('LARSE/GEDI/GEDI04_A_002_MONTHLY')
  .filterDate(START_DATE, END_DATE)
  .filterBounds(aoiGeom)
  .map(function (img) {
    var d = img.date();
    var qNum = d.get('month').subtract(1).divide(3).floor().add(1);
    var yqStr = ee.String(d.get('year').format('%d')).cat('_Q').cat(qNum.format('%d'));

    var agbd = img.select('agbd');
    // Filter kualitas standar rekomendasi NASA/GEDI L4A
    var qualityMask = img.select('l4_quality_flag').eq(1)
      .and(img.select('degrade_flag').eq(0))
      .and(img.select('l2_quality_flag').eq(1))
      .and(img.select('sensitivity').gte(MIN_SENSITIVITY))
      .and(agbd.gt(0));

    return img.updateMask(qualityMask)
      .select(['agbd', 'agbd_se'])
      .set('year_quarter', yqStr);
  });

// GEDI L2A: RH98 (Tinggi Kanopi)
var gediL2aMasked = ee.ImageCollection('LARSE/GEDI/GEDI02_A_002_MONTHLY')
  .filterDate(START_DATE, END_DATE)
  .filterBounds(aoiGeom)
  .map(function (img) {
    var d = img.date();
    var qNum = d.get('month').subtract(1).divide(3).floor().add(1);
    var yqStr = ee.String(d.get('year').format('%d')).cat('_Q').cat(qNum.format('%d'));

    var rh98 = img.select('rh98');
    var qualityMask = img.select('quality_flag').eq(1)
      .and(img.select('degrade_flag').eq(0))
      .and(img.select('sensitivity').gte(MIN_SENSITIVITY))
      .and(rh98.gt(0));

    return img.updateMask(qualityMask)
      .select(['rh98'])
      .set('year_quarter', yqStr);
  });

var overallL2a = gediL2aMasked.median().select('rh98');

// ------------------------------------------------------------------------------
// DATASET TUTUPAN LAHAN: DYNAMIC WORLD V1
// ------------------------------------------------------------------------------
var dwCollection = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
  .filterBounds(aoiGeom);

var overallDW = dwCollection
  .filterDate(START_DATE, END_DATE)
  .select('label')
  .mode();

var overallVegMask = overallDW.gte(1).and(overallDW.lte(5));
var overallBareMask = overallDW.eq(7);

// Daftar Kuartal Aktif GEDI
var uniqueQuarters = ee.List(
  gediL4aMasked.aggregate_array('year_quarter')
).distinct().sort();

print('Daftar Kuartal Aktif GEDI:', uniqueQuarters);

// ------------------------------------------------------------------------------
// EKSTRAKSI GEDI VALID PER HEXAGON DAN FILTER TUTUPAN LAHAN
// ------------------------------------------------------------------------------
var extractedQuarterlySamples = ee.FeatureCollection(uniqueQuarters.map(function (yq) {
  yq = ee.String(yq);
  var interval = getQuarterInterval(yq);

  // Mosaik kuartalan GEDI L4A dan L2A
  var l4aQ = gediL4aMasked.filter(ee.Filter.eq('year_quarter', yq)).mosaic();
  var l2aQ = gediL2aMasked.filter(ee.Filter.eq('year_quarter', yq)).mosaic()
    .select('rh98')
    .unmask(overallL2a);

  var dwQ = dwCollection
    .filterDate(interval.start, interval.end)
    .select('label')
    .mode()
    .unmask(overallDW)
    .rename('dw_label');

  var quarterImg = l4aQ.select(['agbd', 'agbd_se'])
    .addBands(l2aQ.select('rh98'))
    .addBands(dwQ.select('dw_label'))
    .addBands(lonLat.select(['longitude', 'latitude']));

  var validGediMask = l4aQ.select('agbd').mask().and(l2aQ.select('rh98').mask());

  var samplingMask = validGediMask;
  if (MASK_NON_VEGETATION) {
    var vegMask = dwQ.gte(1).and(dwQ.lte(5));
    samplingMask = samplingMask.and(vegMask);
  }

  var maskedQuarterImg = quarterImg.updateMask(samplingMask);

  var hexQuarterSamples = maskedQuarterImg.sampleRegions({
    collection: hexGridClean,
    properties: ['hex_id'],
    scale: SCALE,
    projection: proj,
    geometries: true,
    tileScale: 4
  });

  var baseQualityFilter = ee.Filter.and(
    ee.Filter.gt('agbd', 0),
    ee.Filter.notNull(['rh98'])
  );

  var targetFilter = MASK_NON_VEGETATION
    ? ee.Filter.and(
      baseQualityFilter,
      ee.Filter.gte('dw_label', 1),
      ee.Filter.lte('dw_label', 5)
    )
    : baseQualityFilter;

  var quarterSamplesFiltered = hexQuarterSamples.filter(targetFilter)
    .map(function (f) {
      return f.set('year_quarter', yq).select(OUTPUT_PROPS);
    });

  var quarterSamples = (MAX_SAMPLES_PER_HEX && MAX_SAMPLES_PER_HEX > 0)
    ? limitSamplesPerGrid(quarterSamplesFiltered, MAX_SAMPLES_PER_HEX, RANDOM_SEED)
      .select(OUTPUT_PROPS)
    : quarterSamplesFiltered;

  return quarterSamples;
})).flatten();

var gediProcessedSamples = extractedQuarterlySamples;

// ------------------------------------------------------------------------------
// SAMPEL PSEUDO-ABSENCE BARELAND DENGAN KONTROL PROPORSI
// ------------------------------------------------------------------------------
var gediSamples;

if (INCLUDE_BARE_SAMPLES) {
  var bareBase = hexGridClean.map(function (hex) {
    var hexId = hex.get('hex_id');
    var barePoints = lonLat.select(['longitude', 'latitude'])
      .updateMask(overallBareMask)
      .sample({
        region: hex.geometry(),
        scale: SCALE,
        projection: proj,
        numPixels: MAX_BARE_POINTS_PER_HEX,
        seed: RANDOM_SEED,
        geometries: true
      }).map(function (pt) {
        return pt.set({
          agbd: 0,
          agbd_se: 0,
          rh98: 0,
          hex_id: hexId
        });
      });
    return barePoints;
  }).flatten();

  var bareSamples = ee.FeatureCollection(uniqueQuarters.map(function (yq) {
    return bareBase.map(function (f) {
      return f.set('year_quarter', yq).select(OUTPUT_PROPS);
    });
  })).flatten();

  gediSamples = gediProcessedSamples.merge(bareSamples);
  print('Status Bareland Pseudo-Absence: Diaktifkan');
} else {
  gediSamples = gediProcessedSamples;
  print('Status Bareland Pseudo-Absence: Dinonaktifkan (Hanya Sampel GEDI Asli)');
}

// ------------------------------------------------------------------------------
// LOGGING & MONITORING HASIL DI CONSOLE
// ------------------------------------------------------------------------------
print('================== KONFIGURASI DATA COLLECTION GEDI ==================');
print('1. Opsi Masking Non-Vegetasi (MASK_NON_VEGETATION):', MASK_NON_VEGETATION ? 'AKTIF (Hanya Tutupan Vegetasi DW 1-5)' : 'NONAKTIF (Semua Tutupan Lahan)');
print('2. Ambang Batas Sensitivitas GEDI (MIN_SENSITIVITY):', MIN_SENSITIVITY);
print('3. Unit Pembatasan Sampel: (year_quarter, hex_id) — maks', MAX_SAMPLES_PER_HEX ? MAX_SAMPLES_PER_HEX : 'Tanpa Batas', 'per kombinasi');
print('4. Jumlah Total Sampel GEDI (Setelah Pembatasan per Kuartal per Hexagon):', gediProcessedSamples.size());
print('5. Jumlah Total Dataset Final (Termasuk Bareland jika aktif):', gediSamples.size());
print('6. Contoh 5 Titik Sampel Pertama:', gediSamples.limit(5));
print('======================================================================');

// ------------------------------------------------------------------------------
// VALIDASI: Verifikasi batas sampel per kombinasi (year_quarter, hex_id)
// Hasil validasi hanya untuk print(), tidak dimasukkan ke dataset final.
// ------------------------------------------------------------------------------
var validationSamples = gediProcessedSamples.map(function (f) {
  return ee.Feature(null, {
    year_quarter: f.get('year_quarter'),
    hex_id: f.get('hex_id'),
    yq_hex_key: ee.String(f.get('year_quarter')).cat('|').cat(ee.String(f.get('hex_id')))
  });
});

var uniqueYqHex = validationSamples.distinct(['yq_hex_key']);

var joinValidation = ee.Join.saveAll({
  matchesKey: 'matched_samples',
  ordering: 'yq_hex_key',
  ascending: true
});

var filterValidation = ee.Filter.equals({
  leftField: 'yq_hex_key',
  rightField: 'yq_hex_key'
});

var joinedValidation = joinValidation.apply({
  primary: uniqueYqHex,
  secondary: validationSamples,
  condition: filterValidation
});

var validationResult = joinedValidation.map(function (feat) {
  var count = ee.List(feat.get('matched_samples')).size();
  return ee.Feature(null, {
    year_quarter: feat.get('year_quarter'),
    hex_id: feat.get('hex_id'),
    sample_count: count
  });
});

print('VALIDASI: Jumlah sampel per (year_quarter, hex_id) [harus <= ' + MAX_SAMPLES_PER_HEX + ']:', validationResult.limit(20));
print('VALIDASI: Total kombinasi (year_quarter, hex_id) unik:', uniqueYqHex.size());

// ------------------------------------------------------------------------------
// VISUALISASI PETA
// ------------------------------------------------------------------------------
Map.centerObject(aoiGeom, 8);
Map.addLayer(aoiGeom, { color: 'black' }, 'Batas AOI', false);
Map.addLayer(
  hexGridClean.style({ color: 'orangered', fillColor: '00000000', width: 1 }),
  {}, 'Hexagonal Grid'
);
Map.addLayer(overallVegMask.selfMask(), { palette: ['#2ca25f'] }, 'DW Masker Vegetasi', false);
Map.addLayer(overallBareMask.selfMask(), { palette: ['#e6550d'] }, 'DW Masker Bare Land', false);

var gediAgbdVis = gediL4aMasked.mosaic().select('agbd');
var gediRh98Vis = overallL2a;

if (MASK_NON_VEGETATION) {
  gediAgbdVis = gediAgbdVis.updateMask(overallVegMask);
  gediRh98Vis = gediRh98Vis.updateMask(overallVegMask);
}

Map.addLayer(
  gediAgbdVis,
  { min: 0, max: 300, palette: ['#f7fcb9', '#addd8e', '#31a354', '#006837'] },
  'GEDI AGBD Mosaik ' + (MASK_NON_VEGETATION ? '(Hanya Vegetasi)' : '(Semua Tutupan)')
);
Map.addLayer(
  gediRh98Vis,
  { min: 0, max: 40, palette: ['#edf8b1', '#7fcdbb', '#2c7fb8'] },
  'GEDI RH98 Kanopi ' + (MASK_NON_VEGETATION ? '(Hanya Vegetasi)' : '(Semua Tutupan)'),
  false
);
Map.addLayer(gediSamples.limit(1000), { color: 'blue' }, 'Titik Sampel GEDI Final', true);

// ------------------------------------------------------------------------------
// EKSPOR DATASET KE ASSET & GOOGLE DRIVE
// ------------------------------------------------------------------------------
// Ekspor ke Earth Engine Asset
Export.table.toAsset({
  collection: gediSamples,
  description: 'GEDI_Hexagonal_Target_Dataset',
  assetId: EXPORT_PATH + 'gedi_target_dataset'
});

// Ekspor ke CSV di Google Drive
Export.table.toDrive({
  collection: gediSamples,
  description: 'GEDI_Hexagonal_Target_CSV',
  folder: 'Tugas Akhir',
  fileNamePrefix: 'gedi_target_dataset',
  fileFormat: 'CSV',
  selectors: OUTPUT_PROPS
});