# Trading Bot

Quantitative research and trading bot framework.

## Project Structure

```text
trading-bot/
│
├── README.md
├── requirements.txt
├── .gitignore
│
├── config/
│   ├── settings.py
│   └── symbols.py
│
├── data/
│   ├── raw/
│   │   ├── BTCUSDT/
│   │   ├── ETHUSDT/
│   │   └── SOLUSDT/
│   │
│   ├── processed/
│   │   ├── BTCUSDT/
│   │   ├── ETHUSDT/
│   │   └── SOLUSDT/
│   │
│   └── research/
│       ├── BTCUSDT/
│       ├── ETHUSDT/
│       └── SOLUSDT/
│
├── src/
│   ├── __init__.py
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   ├── downloader.py
│   │   └── loader.py
│   │
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── resampling.py
│   │   └── cleaning.py
│   │
│   ├── indicators/
│   │   ├── __init__.py
│   │   └── averages.py
│   │
│   ├── research/
│   │   ├── __init__.py
│   │   ├── touch_detection.py
│   │   ├── outcome_analysis.py
│   │   └── statistics.py
│   │
│   └── utils/
│       ├── __init__.py
│       └── logger.py
│
├── experiments/
│   ├── experiment_001/
│   │   ├── config.yaml
│   │   └── notes.md
│   │
│   └── experiment_002/
│       ├── config.yaml
│       └── notes.md
│
├── notebooks/
│   ├── 01_data_check.ipynb
│   ├── 02_average_analysis.ipynb
│   ├── 03_touch_analysis.ipynb
│   └── 04_results_analysis.ipynb
│
├── tests/
│   ├── __init__.py
│   ├── test_data.py
│   ├── test_averages.py
│   └── test_touch_detection.py
│
└── results/
    ├── tables/
    ├── charts/
    └── reports/
```
