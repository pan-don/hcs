// ------------------------------------------------------------------------------
// 1. KONFIGURASI DAN PARAMETER
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
var INCLUDE_BARE_SAMPLES = false;
var MAX_BARE_POINTS_PER_HEX = 10;

// ------------------------------------------------------------------------------
// 2. FUNGSI HELPER
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

  // Tambahkan kolom acak untuk pengacakan sampling
  var withRandom = collection.randomColumn('rand_sample', seed);
  var uniqueHex = withRandom.distinct(['hex_id']);

  // Kelompokkan sampel per hex_id dan urutkan berdasarkan nilai acak
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

  // Potong list sampel maksimal sebanyak maxPerGrid per hex_id
  var limited = joined.map(function (feat) {
    var samplesList = ee.List(feat.get('samples'));
    var sliced = samplesList.slice(0, maxPerGrid);
    return ee.FeatureCollection(sliced);
  }).flatten();

  return limited;
}

// ------------------------------------------------------------------------------
// 3. INPUT AOI DAN STANDARISASI HEXAGON GRID
// ------------------------------------------------------------------------------
var aoiGeom = typeof aoi !== 'undefined' ? aoi.geometry() : geometry.geometry();
var hexGridInput = typeof hexgrid !== 'undefined' ? hexgrid : aoi;

// Bersihkan dan standarisasi properti hex_id pada setiap hexagon
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
// 4. FILTER KUALITAS GEDI L4A (AGBD) & L2A (RH98)
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
      .and(img.select('sensitivity').gte(0.90))
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
      .and(img.select('sensitivity').gte(0.90))
      .and(rh98.gt(0));

    return img.updateMask(qualityMask)
      .select(['rh98'])
      .set('year_quarter', yqStr);
  });

var overallL2a = gediL2aMasked.median().select('rh98');

// ------------------------------------------------------------------------------
// 5. DATASET TUTUPAN LAHAN: DYNAMIC WORLD V1
// ------------------------------------------------------------------------------
// Dynamic World Label:
// 0: water, 1: trees, 2: grass, 3: flooded_veg, 4: crops, 5: shrub_and_scrub,
// 6: built, 7: bare, 8: snow_and_ice
var dwCollection = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
  .filterBounds(aoiGeom);

var overallDW = dwCollection
  .filterDate(START_DATE, END_DATE)
  .select('label')
  .mode()
  .reproject({ crs: proj, scale: SCALE });

var overallVegMask = overallDW.gte(1).and(overallDW.lte(5));
var overallBareMask = overallDW.eq(7);

// Daftar Kuartal Aktif GEDI
var uniqueQuarters = ee.List(
  gediL4aMasked.aggregate_array('year_quarter')
).distinct().sort();

print('Daftar Kuartal Aktif GEDI:', uniqueQuarters);

// ------------------------------------------------------------------------------
// 6. EKSTRAKSI GEDI VALID PER HEXAGON DAN FILTER TUTUPAN VEGETASI
// ------------------------------------------------------------------------------
var vegSamples = ee.FeatureCollection(uniqueQuarters.map(function (yq) {
  yq = ee.String(yq);
  var interval = getQuarterInterval(yq);

  // Mosaik kuartalan GEDI L4A dan L2A
  var l4aQ = gediL4aMasked.filter(ee.Filter.eq('year_quarter', yq)).mosaic();
  var l2aQ = gediL2aMasked.filter(ee.Filter.eq('year_quarter', yq)).mosaic()
    .select('rh98')
    .unmask(overallL2a);

  // Mosaik Dynamic World kuartalan (fallback ke overallDW jika kuartal berawan/kosong)
  var dwQ = dwCollection
    .filterDate(interval.start, interval.end)
    .select('label')
    .mode()
    .unmask(overallDW)
    .rename('dw_label');

  // Gabungkan seluruh band ke dalam 1 citra
  var quarterImg = l4aQ.select(['agbd', 'agbd_se'])
    .addBands(l2aQ.select('rh98'))
    .addBands(dwQ.select('dw_label'))
    .addBands(lonLat.select(['longitude', 'latitude']));

  // Pastikan citra hanya memiliki nilai pada piksel GEDI yang valid
  var validGediMask = l4aQ.select('agbd').mask().and(l2aQ.select('rh98').mask());
  var maskedQuarterImg = quarterImg.updateMask(validGediMask);

  // LANGKAH 1: Ekstraksi seluruh piksel GEDI valid yang berada di dalam setiap hexagon
  // sampleRegions pada polygon hanya mengambil piksel unmasked (shot GEDI nyata)
  // dan secara otomatis mewarisi properti 'hex_id' dari hexagon terkait.
  var hexQuarterSamples = maskedQuarterImg.sampleRegions({
    collection: hexGridClean,
    properties: ['hex_id'],
    scale: SCALE,
    projection: proj,
    geometries: true,
    tileScale: 4
  });

  // LANGKAH 2: Filter titik-titik valid GEDI tersebut untuk tutupan vegetasi
  // (Dynamic World classes 1..5: trees, grass, flooded_vegetation, crops, shrub_and_scrub)
  var vegQuarterSamples = hexQuarterSamples.filter(
    ee.Filter.and(
      ee.Filter.gte('dw_label', 1),
      ee.Filter.lte('dw_label', 5),
      ee.Filter.gt('agbd', 0),
      ee.Filter.notNull(['rh98'])
    )
  ).map(function (f) {
    return f.set('year_quarter', yq).select(OUTPUT_PROPS);
  });

  return vegQuarterSamples;
})).flatten();

// LANGKAH 3: Batasi jumlah sampel maksimum per hexagon untuk mencegah spatial bias
var rawVegSamples = vegSamples;
if (MAX_SAMPLES_PER_HEX && MAX_SAMPLES_PER_HEX > 0) {
  vegSamples = limitSamplesPerGrid(vegSamples, MAX_SAMPLES_PER_HEX, RANDOM_SEED)
    .select(OUTPUT_PROPS);
}

// ------------------------------------------------------------------------------
// 7. (OPSIONAL) SAMPEL PSEUDO-ABSENCE BARELAND DENGAN KONTROL PROPORSI
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

  gediSamples = vegSamples.merge(bareSamples);
  print('Status Bareland Pseudo-Absence: Diaktifkan');
} else {
  gediSamples = vegSamples;
  print('Status Bareland Pseudo-Absence: Dinonaktifkan (Hanya Sampel Vegetasi Asli GEDI)');
}

// ------------------------------------------------------------------------------
// 8. LOGGING & MONITORING HASIL DI CONSOLE
// ------------------------------------------------------------------------------
print('Batas Maksimal Sampel per Hexagon (MAX_SAMPLES_PER_HEX):', MAX_SAMPLES_PER_HEX ? MAX_SAMPLES_PER_HEX : 'Tanpa Batas');
print('Jumlah Total Sampel GEDI Vegetasi (Sebelum Pembatasan):', rawVegSamples.size());
print('Jumlah Total Sampel GEDI Vegetasi (Setelah Pembatasan):', vegSamples.size());
print('Contoh 5 Titik Sampel Pertama:', gediSamples.limit(5));

// ------------------------------------------------------------------------------
// 9. VISUALISASI PETA
// ------------------------------------------------------------------------------
Map.centerObject(aoiGeom, 8);
Map.addLayer(aoiGeom, { color: 'black' }, 'Batas AOI', false);
Map.addLayer(
  hexGridClean.style({ color: 'orangered', fillColor: '00000000', width: 1 }),
  {}, 'Hexagonal Grid'
);
Map.addLayer(overallVegMask.selfMask(), { palette: ['#2ca25f'] }, 'DW Masker Vegetasi', false);
Map.addLayer(overallBareMask.selfMask(), { palette: ['#e6550d'] }, 'DW Masker Bare Land', false);
Map.addLayer(
  gediL4aMasked.mosaic().select('agbd').updateMask(overallVegMask),
  { min: 0, max: 300, palette: ['#f7fcb9', '#addd8e', '#31a354', '#006837'] },
  'GEDI AGBD Mosaik (Vegetasi)'
);
Map.addLayer(
  overallL2a.updateMask(overallVegMask),
  { min: 0, max: 40, palette: ['#edf8b1', '#7fcdbb', '#2c7fb8'] },
  'GEDI RH98 Kanopi', false
);
Map.addLayer(gediSamples.limit(1000), { color: 'blue' }, 'Titik Sampel GEDI Final', true);

// ------------------------------------------------------------------------------
// 10. EKSPOR DATASET KE ASSET & GOOGLE DRIVE
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