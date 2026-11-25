# tw50-quant-data

Daily price data for Taiwan-listed stocks, plus monthly revenue, kept as a ready-to-use dataset for quant backtesting. A GitHub Actions workflow refreshes it every weekday.

The project started with the Taiwan 50 constituents and now covers the whole TWSE and TPEx common-stock market, filtered for liquidity. The TW50 code list is kept as a fallback.

## What's in `data/`

| File | Content | Columns |
|---|---|---|
| `<code>.csv.gz` (about 750 stocks) | Daily prices since 2010, dividend- and split-adjusted | `Date, Open, Close, Volume` |
| `0050.csv`, `006208.csv`, `00631L.csv` | ETFs, adjusted | `Date, Open, High, Low, Close, Volume` |
| `IDX_TWII.csv` | TAIEX index | `Date, Open, High, Low, Close, Volume` |
| `revenue.csv.gz` | Monthly revenue since 2011-12, all listed companies | `ym, code, rev, yoy` |
| `fetch_rev_log.txt` | Log of the last revenue fetch | |

- Prices come from Yahoo Finance with `auto_adjust=True`, rounded to 4 decimals. Volume is in shares.
- `rev` is in thousands of NTD; `yoy` is the year-over-year change in percent.
- `manifest.json` records the last run: stocks kept, stocks skipped for low liquidity, failures and a timestamp.

### Stock universe

1. All common stocks (CFI code `ES*`) are read from the TWSE ISIN pages for TWSE (`.TW`) and TPEx (`.TWO`).
2. A stock is kept if it has at least 250 trading days and a median daily traded value (`Close × Volume`) of at least NT$20 million over the last 500 days.

A stock that stops passing the filter, or stops trading, keeps its last file but no longer gets updated, so check the last `Date` before using a file.

### Things to know when backtesting

- Adjusted prices are recalculated on every run, so past values change after each dividend or split. Pin a commit if you need a fixed snapshot.
- Stock files have no High or Low; the ETF and index files do.

## Usage

```python
import pandas as pd

base = "https://raw.githubusercontent.com/Jaycome/tw50-quant-data/main/data"
tsmc = pd.read_csv(f"{base}/2330.csv.gz", parse_dates=["Date"], index_col="Date")
revenue = pd.read_csv(f"{base}/revenue.csv.gz", dtype={"code": str})
```

## How it updates

`.github/workflows/fetch.yml` runs `fetch_data.py` at 06:30 UTC (14:30 Taiwan time) on weekdays, on manual dispatch, and when the scripts change. The bot commits the refreshed `data/` and `manifest.json`.

- `fetch_data.py` downloads prices in batches of 40 tickers, applies the liquidity filter and writes the files above. If the ISIN pages can't be read it falls back to the TW50 list.
- `fetch_revenue.py` runs from `fetch_data.py` when the newest month in `revenue.csv.gz` is more than one month old. It tries the MOPS monthly summary pages first and falls back to the FinMind API.

Run it locally:

```bash
pip install -r requirements.txt
python fetch_data.py
```
