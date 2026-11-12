# V1 Stage 1 — Resampled Data Validation Report

## 1. Purpose

This report documents the creation and validation of 3-minute and 5-minute cryptocurrency candles derived from the validated 1-minute historical datasets.

The 1-minute datasets were used as the single source of truth. No separate 3-minute or 5-minute market data was downloaded.

---

## 2. Source Data

| Item                 | Value                                  |
| -------------------- | -------------------------------------- |
| Source timeframe     | 1-minute                               |
| Source data          | Validated Binance historical spot data |
| Assets               | BTCUSDT, ETHUSDT, SOLUSDT              |
| Timezone             | UTC                                    |
| Source format        | Parquet                                |
| Resampled timeframes | 3-minute, 5-minute                     |

The original 1-minute datasets in `data/raw/` were not modified.

---

## 3. Resampling Method

The 3-minute and 5-minute candles were created by aggregating the existing 1-minute candles.

### Open

The first 1-minute candle's open price is used.

### High

The highest high among the component 1-minute candles is used.

### Low

The lowest low among the component 1-minute candles is used.

### Close

The last 1-minute candle's close price is used.

### Volume

Volume is summed across the component 1-minute candles.

### Number of Trades

The number of trades is summed across the component 1-minute candles.

The same aggregation method is applied to quote volume and taker-buy volume fields.

---

## 4. Generated Datasets

### BTCUSDT

```text
data/processed/BTCUSDT/BTCUSDT_3m.parquet
data/processed/BTCUSDT/BTCUSDT_5m.parquet
```

### ETHUSDT

```text
data/processed/ETHUSDT/ETHUSDT_3m.parquet
data/processed/ETHUSDT/ETHUSDT_5m.parquet
```

### SOLUSDT

```text
data/processed/SOLUSDT/SOLUSDT_3m.parquet
data/processed/SOLUSDT/SOLUSDT_5m.parquet
```

---

## 5. Dataset Summary

| Symbol  | Timeframe | Candles | First Candle         | Last Candle          |
| ------- | --------- | ------: | -------------------- | -------------------- |
| BTCUSDT | 3m        | 335,520 | 2024-09-01 00:00 UTC | 2026-07-31 23:57 UTC |
| BTCUSDT | 5m        | 201,312 | 2024-09-01 00:00 UTC | 2026-07-31 23:55 UTC |
| ETHUSDT | 3m        | 335,520 | 2024-09-01 00:00 UTC | 2026-07-31 23:57 UTC |
| ETHUSDT | 5m        | 201,312 | 2024-09-01 00:00 UTC | 2026-07-31 23:55 UTC |
| SOLUSDT | 3m        | 335,520 | 2024-09-01 00:00 UTC | 2026-07-31 23:57 UTC |
| SOLUSDT | 5m        | 201,312 | 2024-09-01 00:00 UTC | 2026-07-31 23:55 UTC |

---

## 6. Validation Results

### 6.1 Required Columns

All required OHLCV and trade-related columns are present.

**Result: PASS**

---

### 6.2 Timestamp Validation

All datasets:

* Use UTC timestamps
* Are sorted chronologically
* Have the expected candle opening timestamps

**Result: PASS**

---

### 6.3 Duplicate Validation

| Timeframe  | Duplicate Rows | Duplicate Timestamps |
| ---------- | -------------: | -------------------: |
| BTCUSDT 3m |              0 |                    0 |
| BTCUSDT 5m |              0 |                    0 |
| ETHUSDT 3m |              0 |                    0 |
| ETHUSDT 5m |              0 |                    0 |
| SOLUSDT 3m |              0 |                    0 |
| SOLUSDT 5m |              0 |                    0 |

**Result: PASS**

---

### 6.4 Candle Interval Validation

Expected intervals:

* 3-minute dataset → exactly 3 minutes between candle timestamps
* 5-minute dataset → exactly 5 minutes between candle timestamps

| Dataset    | Expected Interval | Incorrect Intervals |
| ---------- | ----------------- | ------------------: |
| BTCUSDT 3m | 3 minutes         |                   0 |
| BTCUSDT 5m | 5 minutes         |                   0 |
| ETHUSDT 3m | 3 minutes         |                   0 |
| ETHUSDT 5m | 5 minutes         |                   0 |
| SOLUSDT 3m | 3 minutes         |                   0 |
| SOLUSDT 5m | 5 minutes         |                   0 |

**Result: PASS**

---

### 6.5 OHLC Validation

The following conditions were checked:

* High >= Low
* Open is between High and Low
* Close is between High and Low
* Prices are positive

All six datasets returned zero violations.

**Result: PASS**

---

### 6.6 Volume Validation

Negative volume values were checked.

All six datasets returned:

```text
Negative volume: 0
```

**Result: PASS**

---

### 6.7 Missing Value Validation

All required fields were checked for missing values.

All six datasets returned:

```text
Total missing values: 0
```

**Result: PASS**

---

## 7. Final Validation Summary

| Dataset    | Status |
| ---------- | ------ |
| BTCUSDT 3m | PASS   |
| BTCUSDT 5m | PASS   |
| ETHUSDT 3m | PASS   |
| ETHUSDT 5m | PASS   |
| SOLUSDT 3m | PASS   |
| SOLUSDT 5m | PASS   |

---

## 8. Data Integrity Decision

The generated 3-minute and 5-minute datasets passed all validation checks.

No cleaning or modification is required.

The original 1-minute data remains unchanged in:

```text
data/raw/
```

The derived 3-minute and 5-minute datasets are stored in:

```text
data/processed/
```

---

## 9. Conclusion

**V1 Stage 1 — Part 5: Create 3-Minute & 5-Minute Candles**

**STATUS: COMPLETE ✅**

The project now has validated:

* 1-minute raw data
* 3-minute processed data
* 5-minute processed data

for BTCUSDT, ETHUSDT, and SOLUSDT.

These datasets are ready for the next research step.