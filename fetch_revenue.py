"""Scrape MOPS monthly revenue summary pages (TWSE sii + TPEx otc).

Output: data/revenue.csv.gz  columns: ym, code, rev, yoy
- ym: revenue month (YYYY-MM)
- rev: single-month revenue (thousand TWD)
- yoy: YoY growth % of single-month revenue
"""
import gzip
import io
import subprocess
import sys
import time
import urllib.request

subprocess.call([sys.executable, '-m', 'pip', 'install', '-q', 'lxml', 'html5lib'])

import pandas as pd

BASE = 'https://mopsov.twse.com.tw/nas/t21/{mkt}/t21sc03_{y}_{m}_0.html'
BASE2 = 'https://mops.twse.com.tw/nas/t21/{mkt}/t21sc03_{y}_{m}_0.html'


def fetch_month(roc_y, m, mkt):
    for base in (BASE, BASE2):
        url = base.format(mkt=mkt, y=roc_y, m=m)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            raw = urllib.request.urlopen(req, timeout=60).read()
            html = raw.decode('big5', 'ignore')
            tables = pd.read_html(io.StringIO(html))
            rows = []
            for t in tables:
                cols = [str(c) for c in (t.columns.get_level_values(-1)
                        if isinstance(t.columns, pd.MultiIndex) else t.columns)]
                if not any('公司代號' in c for c in cols):
                    continue
                t.columns = cols
                code_c = [c for c in cols if '公司代號' in c][0]
                rev_c = [c for c in cols if c.strip() in ('當月營收',)]
                yoy_c = [c for c in cols if '去年同月增減' in c]
                if not rev_c or not yoy_c:
                    continue
                sub = t[[code_c, rev_c[0], yoy_c[0]]].copy()
                sub.columns = ['code', 'rev', 'yoy']
                sub = sub[sub['code'].astype(str).str.match(r'^\d{4}$')]
                rows.append(sub)
            if rows:
                return pd.concat(rows)
        except Exception as e:
            print('miss', url, e)
    return None


def main():
    out = []
    now = pd.Timestamp.now()
    months = pd.period_range('2012-01', now.to_period('M') - 1, freq='M')
    for p in months:
        roc_y = p.year - 1911
        for mkt in ('sii', 'otc'):
            df = fetch_month(roc_y, p.month, mkt)
            if df is not None:
                df['ym'] = str(p)
                out.append(df)
        time.sleep(0.6)
        if p.month == 12:
            print(p, 'rows so far:', sum(len(x) for x in out))
    res = pd.concat(out, ignore_index=True)
    res['rev'] = pd.to_numeric(res['rev'], errors='coerce')
    res['yoy'] = pd.to_numeric(res['yoy'], errors='coerce')
    res = res.dropna(subset=['rev'])[['ym', 'code', 'rev', 'yoy']]
    res.to_csv('data/revenue.csv.gz', index=False, compression='gzip')
    print('saved', len(res), 'rows,', res.ym.nunique(), 'months')


if __name__ == '__main__':
    main()
