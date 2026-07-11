"""Full-market Taiwan stock data fetcher.

- Scrapes all common-stock codes from TWSE ISIN pages (TWSE + TPEx)
- Batch-downloads dividend/split-adjusted daily data from Yahoo Finance (2010+)
- Keeps stocks with enough history and liquidity, writes gzipped CSVs
- Falls back to the original TW50 superset if the ISIN scrape fails
"""
import gzip
import json
import os
import re
import time
import urllib.request

import pandas as pd
import yfinance as yf

FALLBACK = [
    '2330','2317','2454','2308','2382','2412','2881','2882','2891','2886',
    '2884','2885','2892','2880','2883','2887','5880','2890','2303','3711',
    '2379','3034','2345','3231','6669','2376','2357','4938','2327','2360',
    '3017','3661','3443','3008','2395','1216','1101','1301','1303','2002',
    '2207','2603','2912','5871','6446','3037','2383','3045','4904','2301',
    '2408','1590','2059','1519','6505','1326','2615','2609','3653','3529',
]
EXTRA = ['0050.TW', '006208.TW', '00631L.TW', '^TWII']
MIN_DOLLAR_VOL = 20e6   # median daily dollar volume over trailing 2y
MAX_STOCKS = 1200


def get_codes(mode, suffix):
    """Parse TWSE ISIN page; return [(code, suffix)] for common stocks (CFI ES*)."""
    url = f'https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}'
    html = urllib.request.urlopen(url, timeout=120).read().decode('big5', 'ignore')
    out = []
    for tr in html.split('<tr>')[1:]:
        tds = re.findall(r'<td[^>]*>([^<]*)</td>', tr)
        if len(tds) < 6:
            continue
        head, cfi = tds[0].strip(), tds[5].strip()
        m = re.match(r'^(\d{4})　', head)
        if m and cfi.startswith('ES'):
            out.append((m.group(1), suffix))
    return out


def main():
    os.makedirs('data', exist_ok=True)
    try:
        codes = get_codes(2, '.TW') + get_codes(4, '.TWO')
        assert len(codes) > 500
        print('ISIN codes:', len(codes))
    except Exception as e:
        print('ISIN scrape failed, fallback:', e)
        codes = [(c, '.TW') for c in FALLBACK]

    ok, skipped, fail = [], [], []
    chunk = 40
    for i in range(0, len(codes), chunk):
        batch = codes[i:i + chunk]
        syms = [c + s for c, s in batch]
        try:
            df = yf.download(' '.join(syms), start='2010-01-01', auto_adjust=True,
                             group_by='ticker', threads=True, progress=False)
        except Exception as e:
            print('batch err', i, e)
            fail += [c for c, _ in batch]
            time.sleep(10)
            continue
        for c, s in batch:
            sym = c + s
            try:
                sub = df[sym][['Open', 'Close', 'Volume']].dropna(how='all')
            except Exception:
                fail.append(c)
                continue
            sub = sub.dropna()
            if len(sub) < 250:
                skipped.append(c)
                continue
            dv = (sub['Close'] * sub['Volume']).tail(500).median()
            if pd.isna(dv) or dv < MIN_DOLLAR_VOL:
                skipped.append(c)
                continue
            sub.round(4).to_csv(f'data/{c}.csv.gz', compression='gzip')
            old = f'data/{c}.csv'
            if os.path.exists(old):
                os.remove(old)
            ok.append(c)
        print(f'{i + chunk}/{len(codes)} ok={len(ok)}')
        time.sleep(1)
        if len(ok) >= MAX_STOCKS:
            break

    for sym in EXTRA:
        name = sym.replace('^', 'IDX_').replace('.TW', '')
        try:
            df = yf.download(sym, start='2010-01-01', auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df[['Open', 'High', 'Low', 'Close', 'Volume']].round(4).to_csv(f'data/{name}.csv')
            ok.append(sym)
        except Exception as e:
            fail.append(sym)
        time.sleep(1)

    json.dump({'ok_count': len(ok), 'skipped_lowliq': len(skipped), 'fail': fail[:50],
               'updated': pd.Timestamp.now().isoformat()},
              open('manifest.json', 'w'), indent=1)
    print('done ok:', len(ok), 'skipped:', len(skipped), 'fail:', len(fail))


if __name__ == '__main__':
    main()
