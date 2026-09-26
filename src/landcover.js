// =============================================================
// KONFIGURASI DAN PARAMETER GLOBAL
// =============================================================
var PARAMS = {
  years: [2021, 2022, 2023, 2024, 2025],
  scale: 30,
  crs: 'EPSG:32648',
  exportFolder: 'GEE_Exports',
  exportFileName: 'Landcover_DW9',
  exportMaxPixels: 1e13
};

var aoi = typeof geometry !== 'undefined' ? geometry : Map.getBounds(true);

var DW_CLASSES = [
  { value: 0, name: 'Water', color: '#419BDF' },
  { value: 1, name: 'Trees', color: '#397D49' },
  { value: 2, name: 'Grass', color: '#88B053' },
  { value: 3, name: 'Flooded Vegetation', color: '#7A87C6' },
  { value: 4, name: 'Crops', color: '#E49635' },
  { value: 5, name: 'Shrub & Scrub', color: '#DFC35A' },
  { value: 6, name: 'Built Area', color: '#C4281B' },
  { value: 7, name: 'Bare Ground', color: '#A59B8F' },
  { value: 8, name: 'Snow & Ice', color: '#B39FE1' }
];

var DW_PALETTE = DW_CLASSES.map(function (c) { return c.color; });

// =============================================================
// FUNGSI: MEMBANGUN KOMPOSIT TAHUNAN DYNAMIC WORLD (9 KELAS)
// =============================================================
function buildAnnualLandcover(year, region) {
  var start = year + '-01-01';
  var end = year + '-12-31';

  var dwCol = ee.ImageCollection('GOOGLE/DYNAMICWORLD/V1')
    .filterBounds(region);

  var dwYearMode = dwCol.filterDate(start, end).select('label').mode();
  var dwOverallMode = dwCol.select('label').mode();

  var composite = dwYearMode.unmask(dwOverallMode)
    .unmask(255)
    .clip(region)
    .rename('landcover')
    .reproject({ crs: PARAMS.crs, scale: PARAMS.scale });

  return composite.toByte().set({
    'landcover_class_values': DW_CLASSES.map(function (c) { return c.value; }).concat([255]),
    'landcover_class_names': DW_CLASSES.map(function (c) { return c.name; }).concat(['No Data'])
  });
}

// =============================================================
// FUNGSI: VISUALISASI PETA TUTUPAN LAHAN DENGAN LEGENDA RESMI
// =============================================================
function visualizeLandcover(image, region, year) {
  Map.centerObject(region, 10);

  Map.addLayer(
    ee.Image().paint(region, 0, 2),
    { palette: ['#ff0000'] },
    'AOI Boundary'
  );

  Map.addLayer(
    image,
    { min: 0, max: 8, palette: DW_PALETTE },
    'Dynamic World Landcover ' + year
  );

  var legend = ui.Panel({
    style: {
      position: 'bottom-left',
      padding: '8px 12px',
      backgroundColor: 'rgba(255, 255, 255, 0.9)'
    }
  });

  legend.add(ui.Label({
    value: 'Dynamic World (9 Classes)',
    style: { fontWeight: 'bold', fontSize: '13px', margin: '0 0 6px 0' }
  }));

  DW_CLASSES.forEach(function (c) {
    legend.add(ui.Panel([
      ui.Label('', { backgroundColor: c.color, padding: '8px', margin: '2px 6px 2px 0' }),
      ui.Label(c.value + ': ' + c.name, { fontSize: '11px', margin: '2px 0' })
    ], ui.Panel.Layout.flow('horizontal')));
  });

  Map.add(legend);
}

// =============================================================
// FUNGSI: MONITORING DAN PERHITUNGAN LUAS PER KELAS (HEKTAR)
// =============================================================
function printClassAreas(image, region, year) {
  var areaImage = ee.Image.pixelArea().divide(10000).addBands(image);

  var areaStats = areaImage.reduceRegion({
    reducer: ee.Reducer.sum().group({
      groupField: 1,
      groupName: 'class_value'
    }),
    geometry: region,
    scale: PARAMS.scale,
    crs: PARAMS.crs,
    maxPixels: PARAMS.exportMaxPixels,
    bestEffort: true
  });

  var labelDict = { '255': 'No Data' };
  DW_CLASSES.forEach(function (c) {
    labelDict[c.value.toString()] = c.name;
  });
  var classLabels = ee.Dictionary(labelDict);

  var groups = ee.List(areaStats.get('groups'));
  var attributeTable = ee.FeatureCollection(groups.map(function (item) {
    var dict = ee.Dictionary(item);
    var val = ee.Number(dict.get('class_value'));
    var label = classLabels.get(val.format('%.0f'), 'Unknown');
    return ee.Feature(null, {
      'class_value': val,
      'label': label,
      'area_ha': dict.get('sum')
    });
  }));

  print('Ringkasan Luas Tutupan Lahan Tahun ' + year + ' (Hektar):', attributeTable);
}

// =============================================================
// FUNGSI: EKSPOR RASTER TUTUPAN LAHAN KE GOOGLE DRIVE
// =============================================================
function exportLandcoverToDrive(image, region, year) {
  var fileName = PARAMS.exportFileName + '_' + year;

  var meta = image.unmask(255).set({
    'dataset': 'GOOGLE/DYNAMICWORLD/V1',
    'year': year,
    'scale_m': PARAMS.scale,
    'crs': PARAMS.crs,
    'purpose': 'HCS Stratification Analysis',
    'landcover_class_values': DW_CLASSES.map(function (c) { return c.value; }).concat([255]),
    'landcover_class_names': DW_CLASSES.map(function (c) { return c.name; }).concat(['No Data'])
  });

  Export.image.toDrive({
    image: meta,
    description: fileName,
    folder: PARAMS.exportFolder,
    fileNamePrefix: fileName,
    region: region,
    scale: PARAMS.scale,
    crs: PARAMS.crs,
    maxPixels: PARAMS.exportMaxPixels
  });

  print('Task Ekspor Drive Terdaftar: ' + fileName);
}

// =============================================================
// PIPELINE UTAMA
// =============================================================
(function main() {
  print('Inisialisasi Ekstraksi Tutupan Lahan Dynamic World 9 Kelas...');
  print('Skala:', PARAMS.scale + ' m | CRS:', PARAMS.crs);
  print('Daftar Tahun:', PARAMS.years);

  var aoiGeom = typeof geometry !== 'undefined' ? geometry : Map.getBounds(true);

  PARAMS.years.forEach(function (year) {
    print('Memproses Tutupan Lahan Tahun:', year);

    var lcImg = buildAnnualLandcover(year, aoiGeom);

    printClassAreas(lcImg, aoiGeom, year);
    exportLandcoverToDrive(lcImg, aoiGeom, year);

    if (year === PARAMS.years[PARAMS.years.length - 1]) {
      visualizeLandcover(lcImg, aoiGeom, year);
    }
  });
})();