# V1 Stage 1 — Raw Data Validation Report

## 1. Purpose

This report documents the validation of the historical 1-minute cryptocurrency market data used for V1 Stage 1 research.

The purpose of validation is to ensure that the raw dataset is reliable before calculating averages, detecting price touches, or performing any further research.

---

## 2. Dataset

| Item                    | Value                        |
| ----------------------- | ---------------------------- |
| Assets                  | BTCUSDT, ETHUSDT, SOLUSDT    |
| Timeframe               | 1-minute                     |
| Data Source             | Binance Historical Spot Data |
| Requested Period        | 2024-09-01 → 2026-08-31      |
| Actual Available Period | 2024-09-01 → 2026-07-31      |
| Timestamp Standard      | UTC                          |
| Storage Format          | Parquet                      |
| Research Type           | Historical only              |

### August 2026 Data

The monthly Binance archive for August 2026 was not available during data collection.

Therefore, the actual dataset ends at:

**2026-07-31 23:59:00 UTC**

The missing August 2026 archive is not considered a data-quality failure.

---

## 3. Dataset Summary

| Symbol  |      Rows | First Candle         | Last Candle          |
| ------- | --------: | -------------------- | -------------------- |
| BTCUSDT | 1,006,560 | 2024-09-01 00:00 UTC | 2026-07-31 23:59 UTC |
| ETHUSDT | 1,006,560 | 2024-09-01 00:00 UTC | 2026-07-31 23:59 UTC |
| SOLUSDT | 1,006,560 | 2024-09-01 00:00 UTC | 2026-07-31 23:59 UTC |

Total candles across all assets:

**3,019,680**

---

## 4. Validation Checks

### 4.1 Required Columns

Required columns:

* `open_time`
* `open`
* `high`
* `low`
* `close`
* `volume`
* `close_time`

| Symbol  | Result |
| ------- | ------ |
| BTCUSDT | PASS   |
| ETHUSDT | PASS   |
| SOLUSDT | PASS   |

All required columns are present.

---

### 4.2 Timestamp Validation

Checks performed:

* Timestamp datatype
* Timezone information
* Chronological ordering

All three datasets contain UTC timestamps and are sorted chronologically.

| Symbol  | Timezone | Sorted |
| ------- | -------- | ------ |
| BTCUSDT | UTC      | Yes    |
| ETHUSDT | UTC      | Yes    |
| SOLUSDT | UTC      | Yes    |

Result: **PASS**

---

### 4.3 Duplicate Validation

Both complete duplicate rows and duplicate timestamps were checked.

| Symbol  | Duplicate Rows | Duplicate Timestamps |
| ------- | -------------: | -------------------: |
| BTCUSDT |              0 |                    0 |
| ETHUSDT |              0 |                    0 |
| SOLUSDT |              0 |                    0 |

Result: **PASS**

---

### 4.4 Missing Candle / Gap Validation

The timestamp difference between consecutive candles was checked against the expected 1-minute interval.

| Symbol  | Gaps |
| ------- | ---: |
| BTCUSDT |    0 |
| ETHUSDT |    0 |
| SOLUSDT |    0 |

No missing 1-minute candles were detected within the available dataset period.

Result: **PASS**

---

### 4.5 OHLC Validation

The following conditions were checked:

* `high >= low`
* `low <= open <= high`
* `low <= close <= high`
* All OHLC prices greater than zero

| Check                  | BTCUSDT | ETHUSDT | SOLUSDT |
| ---------------------- | ------: | ------: | ------: |
| High < Low             |       0 |       0 |       0 |
| Open outside High/Low  |       0 |       0 |       0 |
| Close outside High/Low |       0 |       0 |       0 |
| Non-positive prices    |       0 |       0 |       0 |

Result: **PASS**

---

### 4.6 Volume Validation

Negative volume values were checked.

| Symbol  | Negative Volume |
| ------- | --------------: |
| BTCUSDT |               0 |
| ETHUSDT |               0 |
| SOLUSDT |               0 |

Result: **PASS**

---

## 5. Overall Validation Result

| Symbol  | Overall Status |
| ------- | -------------- |
| BTCUSDT | PASS           |
| ETHUSDT | PASS           |
| SOLUSDT | PASS           |

All defined validation checks passed successfully.

No cleaning or modification of the raw Parquet datasets is required.

---

## 6. Data Handling Decision

The validated Parquet files in:

```text
data/raw/
```

will remain unchanged.

The raw data is considered the original historical dataset for V1 Stage 1.

Any future transformations, such as:

* Resampling 1-minute candles to 3-minute candles
* Resampling 1-minute candles to 5-minute candles
* Calculating daily closes
* Calculating 7D / 15D / 30D averages
* Creating research datasets

should be performed on derived data rather than modifying the raw files.

---

## 7. Validation Conclusion

**V1 Stage 1 — Part 4: Validate Raw Data**

**STATUS: COMPLETE ✅**

The historical 1-minute datasets for BTCUSDT, ETHUSDT, and SOLUSDT have passed all defined data-quality checks.

The dataset is ready for the next stage of V1 Stage 1 research.

### Next Part

**Part 5 — Process and Prepare the Historical Data**

The next step will prepare the validated 1-minute data for research while keeping the original raw data unchanged.
