
// =============================================================
// KONFIGURASI DAN PARAMETER MODEL
// =============================================================
var ASSET_ID = 'users/sananta/gedi_master_multimodal_dataset';
var TARGET = 'rh98';
var SPLIT_SEED = 42;
var TRAIN_FRAC = 0.80;
var SPLIT_METHOD = 'SPATIAL';
var MAX_SLOPE_DEG = 35;
var MAX_TARGET = 1000;

var RF_PARAMS = {
    numberOfTrees: 350,
    variablesPerSplit: null,
    minLeafPopulation: 5,
    bagFraction: 0.632,
    seed: SPLIT_SEED
};

var FEATURES = [
    's2_b2', 's2_b3', 's2_b4', 's2_b5', 's2_b6', 's2_b7', 's2_b8', 's2_b11', 's2_b12',
    'ndvi', 'evi', 'ndre', 'ireci', 'gao_ndwi',
    'ireci_contrast', 'ireci_ent', 'ireci_corr',
    'swir_contrast', 'swir_ent', 'swir_corr',
    's1_vv', 's1_vh',
    's1_vv_contrast', 's1_vv_ent', 's1_vv_corr',
    's1_vh_contrast', 's1_vh_ent', 's1_vh_corr',
    'dem', 'slope', 'aspect',
    'water', 'trees', 'grass', 'flooded_veg',
    'crops', 'shrub_scrub', 'built', 'bareland'
];

// =============================================================
// 1. LOAD DATASET & STANDARISASI NAMA PROPERTI
// =============================================================
var rawDataset = typeof table !== 'undefined' ? table : ee.FeatureCollection(ASSET_ID);

print('1. Diagnostik Dataset Awal:');
print('   - Total Sampel Mentah Awal:', rawDataset.size());
print('   - Contoh 1 Data Mentah    :', rawDataset.first());

// Standarisasi properti dataset agar sinkron dengan daftar FEATURES
// Menjembatani perbedaan nama band seperti s1_vv vs vv, RH98 vs rh98, dsb.
var standardizedDataset = rawDataset.map(function (f) {
    var d = f.toDictionary();

    // S1 SAR Bands: salin dari s1_vv jika vv tidak ada
    var vv = ee.Algorithms.If(d.contains('vv'), d.get('vv'), d.get('s1_vv'));
    var vh = ee.Algorithms.If(d.contains('vh'), d.get('vh'), d.get('s1_vh'));
    var vv_contrast = ee.Algorithms.If(d.contains('vv_contrast'), d.get('vv_contrast'), d.get('s1_vv_contrast'));
    var vv_ent = ee.Algorithms.If(d.contains('vv_ent'), d.get('vv_ent'), d.get('s1_vv_ent'));
    var vv_corr = ee.Algorithms.If(d.contains('vv_corr'), d.get('vv_corr'), d.get('s1_vv_corr'));
    var vh_contrast = ee.Algorithms.If(d.contains('vh_contrast'), d.get('vh_contrast'), d.get('s1_vh_contrast'));
    var vh_ent = ee.Algorithms.If(d.contains('vh_ent'), d.get('vh_ent'), d.get('s1_vh_ent'));
    var vh_corr = ee.Algorithms.If(d.contains('vh_corr'), d.get('vh_corr'), d.get('s1_vh_corr'));

    // Target RH98
    var rh98 = ee.Algorithms.If(d.contains('rh98'), d.get('rh98'),
        ee.Algorithms.If(d.contains('RH98'), d.get('RH98'), null));

    // Topografi Slope & DEM
    var slope = ee.Algorithms.If(d.contains('slope'), d.get('slope'),
        ee.Algorithms.If(d.contains('Slope'), d.get('Slope'), 0));
    var dem = ee.Algorithms.If(d.contains('dem'), d.get('dem'),
        ee.Algorithms.If(d.contains('DEM'), d.get('DEM'), 0));
    var aspect = ee.Algorithms.If(d.contains('aspect'), d.get('aspect'),
        ee.Algorithms.If(d.contains('Aspect'), d.get('Aspect'), 0));

    // Hexagonal Grid ID
    var hex_id = ee.Algorithms.If(d.contains('hex_id'), d.get('hex_id'),
        ee.Algorithms.If(d.contains('HEX_ID'), d.get('HEX_ID'), 'HEX_0'));

    // Dynamic World
    var flooded_veg = ee.Algorithms.If(d.contains('flooded_veg'), d.get('flooded_veg'), d.get('flooded_vegetation'));
    var shrub_scrub = ee.Algorithms.If(d.contains('shrub_scrub'), d.get('shrub_scrub'), d.get('shrub_and_scrub'));
    var bareland = ee.Algorithms.If(d.contains('bareland'), d.get('bareland'), d.get('bare'));

    return f.set({
        'vv': vv,
        'vh': vh,
        'vv_contrast': vv_contrast,
        'vv_ent': vv_ent,
        'vv_corr': vv_corr,
        'vh_contrast': vh_contrast,
        'vh_ent': vh_ent,
        'vh_corr': vh_corr,
        'rh98': rh98,
        'slope': slope,
        'dem': dem,
        'aspect': aspect,
        'hex_id': hex_id,
        'flooded_veg': flooded_veg,
        'shrub_scrub': shrub_scrub,
        'bareland': bareland
    });
});

// =============================================================
// 2. FILTER KUALITAS & PEMBERSIHAN DATASET
// =============================================================
// Filter target valid
var targetFiltered = standardizedDataset
    .filter(ee.Filter.notNull([TARGET]))
    .filter(ee.Filter.gte(TARGET, 0))
    .filter(ee.Filter.lte(TARGET, MAX_TARGET));

// Filter drop data lereng/sudut elevasi > 35 derajat
var slopeFiltered = targetFiltered.filter(ee.Filter.lte('slope', MAX_SLOPE_DEG));

// Filter data yang memiliki fitur lengkap
var cleanDatasetCandidate = slopeFiltered.filter(ee.Filter.notNull(FEATURES));

// Proteksi: Gunakan cleanDatasetCandidate jika valid (>0), jika kosong fallback ke slopeFiltered
var cleanDataset = ee.FeatureCollection(ee.Algorithms.If(
    cleanDatasetCandidate.size().gt(0),
    cleanDatasetCandidate,
    slopeFiltered
));

print('2. Statistik Pembersihan Dataset:');
print('   - Sampel Target Valid                 :', targetFiltered.size());
print('   - Sampel Lolos Filter Slope <= ' + MAX_SLOPE_DEG + '°    :', slopeFiltered.size());
print('   - Total Sampel Bersih Siap Training   :', cleanDataset.size());
print('   - Total Fitur Prediktor Digunakan     :', FEATURES.length);

// =============================================================
// 3. SPATIAL SPLIT (BEBAS DATA LEAKAGE) DENGAN FALLBACK AMAN
// =============================================================
var trainSet;
var testSet;

if (SPLIT_METHOD === 'SPATIAL') {
    var uniqueHex = cleanDataset.distinct(['hex_id']).randomColumn('hex_rand', SPLIT_SEED);
    var trainHexIds = uniqueHex.filter(ee.Filter.lt('hex_rand', TRAIN_FRAC)).aggregate_array('hex_id');
    var trCandidate = cleanDataset.filter(ee.Filter.inList('hex_id', trainHexIds));
    var teCandidate = cleanDataset.filter(ee.Filter.inList('hex_id', trainHexIds).not());

    // Validasi agar trainSet tidak kosong jika hex_id homogen
    var isSpatialValid = trCandidate.size().gt(0).and(teCandidate.size().gt(0));

    trainSet = ee.FeatureCollection(ee.Algorithms.If(
        isSpatialValid,
        trCandidate,
        cleanDataset.randomColumn('rand', SPLIT_SEED).filter(ee.Filter.lt('rand', TRAIN_FRAC))
    ));

    testSet = ee.FeatureCollection(ee.Algorithms.If(
        isSpatialValid,
        teCandidate,
        cleanDataset.randomColumn('rand', SPLIT_SEED).filter(ee.Filter.gte('rand', TRAIN_FRAC))
    ));

    print('3. Metode Split:', ee.Algorithms.If(isSpatialValid, 'SPATIAL BLOCK', 'RANDOM SAMPLING (Fallback)'));
} else {
    var withRand = cleanDataset.randomColumn('rand', SPLIT_SEED);
    trainSet = withRand.filter(ee.Filter.lt('rand', TRAIN_FRAC));
    testSet = withRand.filter(ee.Filter.gte('rand', TRAIN_FRAC));
    print('3. Metode Split: RANDOM SAMPLING');
}

print('   - Jumlah Sampel Training:', trainSet.size());
print('   - Jumlah Sampel Testing :', testSet.size());

// =============================================================
// 4. PELATIHAN MODEL RANDOM FOREST
// =============================================================
var rfModel = ee.Classifier.smileRandomForest({
    numberOfTrees: RF_PARAMS.numberOfTrees,
    variablesPerSplit: RF_PARAMS.variablesPerSplit,
    minLeafPopulation: RF_PARAMS.minLeafPopulation,
    bagFraction: RF_PARAMS.bagFraction,
    seed: RF_PARAMS.seed
})
    .setOutputMode('REGRESSION')
    .train({
        features: trainSet,
        classProperty: TARGET,
        inputProperties: FEATURES
    });

print('4. Model Berhasil Dilatih: Random Forest Regressor (Canopy Height RH98)');

// =============================================================
// 5. PREDIKSI TRAINING DAN TESTING
// =============================================================
var trainPred = trainSet.classify(rfModel, 'predicted');
var testPred = testSet.classify(rfModel, 'predicted');

// =============================================================
// 6. FUNGSI: PERHITUNGAN METRIK EVALUASI
// =============================================================
function computeMetrics(fc, actualCol, predCol) {
    var n = fc.size();
    var meanActual = fc.aggregate_mean(actualCol);

    var evaluated = fc.map(function (f) {
        var y = ee.Number(f.get(actualCol));
        var yHat = ee.Number(f.get(predCol));
        var diff = yHat.subtract(y);
        var sqErr = diff.pow(2);
        var absErr = diff.abs();
        var ssTot = y.subtract(meanActual).pow(2);
        return f.set({
            'diff': diff,
            'sq_err': sqErr,
            'abs_err': absErr,
            'ss_tot': ssTot
        });
    });

    var sumSqErr = evaluated.aggregate_sum('sq_err');
    var sumTot = evaluated.aggregate_sum('ss_tot');
    var sumDiff = evaluated.aggregate_sum('diff');
    var meanAbsErr = evaluated.aggregate_mean('abs_err');

    var mse = sumSqErr.divide(n);
    var rmse = mse.sqrt();
    var mae = meanAbsErr;
    var r2 = ee.Number(1).subtract(sumSqErr.divide(sumTot));
    var bias = sumDiff.divide(n);
    var rRMSE = rmse.divide(meanActual).multiply(100);
    var pBias = bias.divide(meanActual).multiply(100);

    return {
        r2: r2,
        rmse: rmse,
        mae: mae,
        bias: bias,
        pBias: pBias,
        rRMSE: rRMSE
    };
}

// =============================================================
// 7. EVALUASI DAN MONITORING HASIL
// =============================================================
var trainMetrics = computeMetrics(trainPred, TARGET, 'predicted');
var testMetrics = computeMetrics(testPred, TARGET, 'predicted');

print('5. EVALUASI HASIL PREDIKSI CANOPY HEIGHT (RH98):');
print('   -- DATA TRAINING --');
print('      R²   :', trainMetrics.r2);
print('      RMSE :', trainMetrics.rmse, 'm');
print('      MAE  :', trainMetrics.mae, 'm');
print('      Bias :', trainMetrics.bias, 'm');
print('      %Bias:', trainMetrics.pBias, '%');
print('      rRMSE:', trainMetrics.rRMSE, '%');

print('   -- DATA TESTING (VALIDASI INDEPENDEN) --');
print('      R²   :', testMetrics.r2);
print('      RMSE :', testMetrics.rmse, 'm');
print('      MAE  :', testMetrics.mae, 'm');
print('      Bias :', testMetrics.bias, 'm');
print('      %Bias:', testMetrics.pBias, '%');
print('      rRMSE:', testMetrics.rRMSE, '%');

// =============================================================
// 8. VISUALISASI GRAFIK SCATTER AKTUAL VS PREDIKSI
// =============================================================
// Ambil sampel representatif (maks 2500 titik) untuk rendering grafik di UI tanpa lag
var scatterSample = testPred.limit(2500);

var scatterChart = ui.Chart.feature.byFeature({
    features: scatterSample,
    xProperty: TARGET,
    yProperties: ['predicted']
})
    .setChartType('ScatterChart')
    .setOptions({
        title: 'Actual vs Predicted Canopy Height RH98 (Test Set Sample)',
        titleTextStyle: { fontSize: 14, bold: true },
        hAxis: { title: 'Actual RH98 GEDI (m)', titleTextStyle: { bold: true } },
        vAxis: { title: 'Predicted Canopy Height (m)', titleTextStyle: { bold: true } },
        pointSize: 3,
        colors: ['#1b5e20'],
        trendlines: {
            0: {
                type: 'linear',
                color: '#d32f2f',
                lineWidth: 2,
                showR2: true,
                visibleInLegend: true,
                labelInLegend: '1:1 Fit Trendline'
            }
        },
        legend: { position: 'bottom' }
    });

print(scatterChart);

// =============================================================
// 9. VISUALISASI GRAFIK FEATURE IMPORTANCE
// =============================================================
var importance = rfModel.explain();
var importanceValues = ee.Dictionary(ee.Dictionary(importance).get('importance'));

var importanceChart = ui.Chart.feature.byProperty({
    features: ee.Feature(null, importanceValues),
    xProperties: FEATURES
})
    .setChartType('ColumnChart')
    .setOptions({
        title: 'Feature Importance - Canopy Height Random Forest',
        titleTextStyle: { fontSize: 14, bold: true },
        hAxis: { title: 'Prediktor', slantedText: true, slantedTextAngle: 45 },
        vAxis: { title: 'Skor Importance' },
        colors: ['#2e7d32'],
        legend: { position: 'none' }
    });

print(importanceChart);

// =============================================================
// 10. EKSPOR MODEL RANDOM FOREST KE ASSET
// =============================================================
Export.classifier.toAsset({
    classifier: rfModel,
    description: 'Export_RF_Canopy_Height_Model',
    assetId: 'users/sananta/rf_canopy_height_model'
});
