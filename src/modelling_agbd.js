// =============================================================
// KONFIGURASI DAN PARAMETER MODEL
// =============================================================
var ASSET_ID = 'users/sananta/gedi_master_multimodal_dataset';
var TARGET = 'agbd';
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
// LOAD DAN VALIDASI DATASET
// =============================================================
var rawDataset = typeof table !== 'undefined' ? table : ee.FeatureCollection(ASSET_ID);

var totalRaw = rawDataset.size();

var slopeFiltered = rawDataset.filter(ee.Filter.lte('slope', MAX_SLOPE_DEG));

var cleanDataset = slopeFiltered
    .filter(ee.Filter.notNull([TARGET]))
    .filter(ee.Filter.gte(TARGET, 0))
    .filter(ee.Filter.lte(TARGET, MAX_TARGET))
    .filter(ee.Filter.notNull(FEATURES));

print('1. Statistik Pembersihan Dataset:');
print('   - Total Sampel Mentah Awal       :', totalRaw);
print('   - Sampel Lolos Filter Slope <= ' + MAX_SLOPE_DEG + '°:', slopeFiltered.size());
print('   - Total Sampel Bersih & Valid    :', cleanDataset.size());
print('2. Total Fitur Prediktor            :', FEATURES.length);
print('3. Variabel Target                  :', TARGET, '(Aboveground Biomass Density, Mg/ha)');

// =============================================================
// SPATIAL SPLIT (BEBAS DATA LEAKAGE)
// =============================================================
var trainSet;
var testSet;

if (SPLIT_METHOD === 'SPATIAL') {
    var uniqueHex = cleanDataset.distinct(['hex_id']).randomColumn('hex_rand', SPLIT_SEED);
    var trainHexIds = uniqueHex.filter(ee.Filter.lt('hex_rand', TRAIN_FRAC)).aggregate_array('hex_id');
    trainSet = cleanDataset.filter(ee.Filter.inList('hex_id', trainHexIds));
    testSet = cleanDataset.filter(ee.Filter.inList('hex_id', trainHexIds).not());
    print('4. Metode Split: SPATIAL BLOCK (Bebas Spatial Autocorrelation Leakage)');
} else {
    var withRand = cleanDataset.randomColumn('rand', SPLIT_SEED);
    trainSet = withRand.filter(ee.Filter.lt('rand', TRAIN_FRAC));
    testSet = withRand.filter(ee.Filter.gte('rand', TRAIN_FRAC));
    print('4. Metode Split: RANDOM SAMPLING');
}

print('   - Jumlah Sampel Training:', trainSet.size());
print('   - Jumlah Sampel Testing :', testSet.size());

// =============================================================
// PELATIHAN MODEL RANDOM FOREST
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

print('5. Model Berhasil Dilatih: Random Forest Regressor (AGBD)');

// =============================================================
// PREDIKSI TRAINING DAN TESTING
// =============================================================
var trainPred = trainSet.classify(rfModel, 'predicted');
var testPred = testSet.classify(rfModel, 'predicted');

// =============================================================
// FUNGSI: PERHITUNGAN METRIK EVALUASI
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
// EVALUASI DAN MONITORING HASIL
// =============================================================
var trainMetrics = computeMetrics(trainPred, TARGET, 'predicted');
var testMetrics = computeMetrics(testPred, TARGET, 'predicted');

print('6. EVALUASI HASIL PREDIKSI AGBD:');
print('   -- DATA TRAINING --');
print('      R²   :', trainMetrics.r2);
print('      RMSE :', trainMetrics.rmse, 'Mg/ha');
print('      MAE  :', trainMetrics.mae, 'Mg/ha');
print('      Bias :', trainMetrics.bias, 'Mg/ha');
print('      %Bias:', trainMetrics.pBias, '%');
print('      rRMSE:', trainMetrics.rRMSE, '%');

print('   -- DATA TESTING (VALIDASI INDEPENDEN) --');
print('      R²   :', testMetrics.r2);
print('      RMSE :', testMetrics.rmse, 'Mg/ha');
print('      MAE  :', testMetrics.mae, 'Mg/ha');
print('      Bias :', testMetrics.bias, 'Mg/ha');
print('      %Bias:', testMetrics.pBias, '%');
print('      rRMSE:', testMetrics.rRMSE, '%');

// =============================================================
// VISUALISASI GRAFIK SCATTER AKTUAL VS PREDIKSI
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
        title: 'Actual vs Predicted AGBD (Test Set Sample)',
        titleTextStyle: { fontSize: 14, bold: true },
        hAxis: { title: 'Actual AGBD GEDI (Mg/ha)', titleTextStyle: { bold: true } },
        vAxis: { title: 'Predicted AGBD (Mg/ha)', titleTextStyle: { bold: true } },
        pointSize: 3,
        colors: ['#2e7d32'],
        trendlines: {
            0: {
                type: 'linear',
                color: '#c62828',
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
// VISUALISASI GRAFIK FEATURE IMPORTANCE
// =============================================================
var importance = rfModel.explain();
var importanceValues = ee.Dictionary(ee.Dictionary(importance).get('importance'));

var importanceChart = ui.Chart.feature.byProperty({
    features: ee.Feature(null, importanceValues),
    xProperties: FEATURES
})
    .setChartType('ColumnChart')
    .setOptions({
        title: 'Feature Importance - Random Forest AGBD',
        titleTextStyle: { fontSize: 14, bold: true },
        hAxis: { title: 'Prediktor', slantedText: true, slantedTextAngle: 45 },
        vAxis: { title: 'Skor Importance' },
        colors: ['#1565c0'],
        legend: { position: 'none' }
    });

print(importanceChart);

// =============================================================
// EKSPOR MODEL RANDOM FOREST KE ASSET
// =============================================================
Export.classifier.toAsset({
    classifier: rfModel,
    description: 'Export_RF_AGBD_Model',
    assetId: 'users/sananta/rf_agbd_model'
});