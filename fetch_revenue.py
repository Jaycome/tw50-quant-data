"""Monthly revenue fetcher with two sources and a committed debug log.

1) MOPS summary pages (fast, all companies per page) — often blocks cloud IPs
2) FinMind TaiwanStockMonthRevenue per stock (slow, rate-limited) as fallback

Output: data/revenue.csv.gz  columns: ym, code, rev, yoy
Debug:  data/fetch_rev_log.txt
"""
import glob
import io
import json
import os
import subprocess
import sys
import time
import urllib.request

subprocess.call([sys.executable, '-m', 'pip', 'install', '-q', 'lxml', 'html5lib'])

import pandas as pd

LOG = []


def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s)
    LOG.append(s)


def http_get(url, timeout=45):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=timeout).read()


# ---------- source 1: MOPS ----------
def mops_month(roc_y, m, mkt):
    for dom in ('mopsov.twse.com.tw', 'mops.twse.com.tw'):
        url = f'https://{dom}/nas/t21/{mkt}/t21sc03_{roc_y}_{m}_0.html'
        try:
            html = http_get(url).decode('big5', 'ignore')
        except Exception as e:
            log('MISS', url, repr(e)[:120])
            continue
        try:
            tables = pd.read_html(io.StringIO(html))
        except Exception as e:
            log('PARSE-ERR', url, repr(e)[:120], 'len=', len(html), 'head=', html[:120].replace('\n', ' '))
            continue
        rows = []
        for t in tables:
            cols = [str(c) for c in (t.columns.get_level_values(-1)
                    if isinstance(t.columns, pd.MultiIndex) else t.columns)]
            if not any('公司代號' in c for c in cols):
                continue
            t.columns = cols
            code_c = [c for c in cols if '公司代號' in c][0]
            rev_c = [c for c in cols if c.strip() == '當月營收']
            yoy_c = [c for c in cols if '去年同月增減' in c]
            if not rev_c or not yoy_c:
                continue
            sub = t[[code_c, rev_c[0], yoy_c[0]]].copy()
            sub.columns = ['code', 'rev', 'yoy']
            sub = sub[sub['code'].astype(str).str.match(r'^\d{4}$')]
            rows.append(sub)
        if rows:
            return pd.concat(rows)
        log('EMPTY', url, 'tables=', len(tables))
    return None


def try_mops(months):
    # probe one known-good month first
    probe = mops_month(113, 1, 'sii')
    if probe is None or len(probe) < 100:
        log('MOPS probe failed -> fallback to FinMind')
        return None
    log('MOPS probe ok, rows:', len(probe))
    out = []
    for p in months:
        for mkt in ('sii', 'otc'):
            df = mops_month(p.year - 1911, p.month, mkt)
            if df is not None:
                df['ym'] = str(p)
                out.append(df)
        time.sleep(0.5)
    return pd.concat(out, ignore_index=True) if out else None


# ---------- source 2: FinMind ----------
def try_finmind():
    codes = sorted(os.path.basename(f).split('.')[0]
                   for f in glob.glob('data/[1-9]*.csv.gz'))
    log('FinMind fallback for', len(codes), 'stocks')
    out = []
    fails = 0
    for i, c in enumerate(codes):
        url = ('https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue'
               f'&data_id={c}&start_date=2012-01-01')
        got = False
        for attempt in range(4):
            try:
                j = json.loads(http_get(url, timeout=60))
                if j.get('status') == 200:
                    for r in j.get('data', []):
                        out.append({'ym': f"{r['revenue_year']}-{r['revenue_month']:02d}",
                                    'code': c, 'rev': r['revenue'] / 1000.0, 'yoy': None})
                    got = True
                    break
                # rate limited or error
                log('FM', c, 'status', j.get('status'), str(j.get('msg'))[:80])
                time.sleep(90 if '402' in str(j.get('status')) or 'limit' in str(j.get('msg', '')).lower() else 10)
            except Exception as e:
                log('FM-ERR', c, repr(e)[:100])
                time.sleep(15)
        if not got:
            fails += 1
        if i % 50 == 0:
            log('FM progress', i, '/', len(codes), 'rows', len(out), 'fails', fails)
        time.sleep(2.5)
    if not out:
        return None
    df = pd.DataFrame(out)
    # compute yoy from revenue itself
    piv = df.pivot_table(index='ym', columns='code', values='rev', aggfunc='last').sort_index()
    yoy = (piv / piv.shift(12) - 1) * 100
    long_rev = piv.stack().rename('rev')
    long_yoy = yoy.stack().rename('yoy')
    res = pd.concat([long_rev, long_yoy], axis=1).reset_index()
    res.columns = ['ym', 'code', 'rev', 'yoy']
    return res


def main():
    os.makedirs('data', exist_ok=True)
    now = pd.Timestamp.now()
    months = pd.period_range('2012-01', now.to_period('M') - 1, freq='M')
    res = None
    try:
        res = try_mops(months)
    except Exception as e:
        log('MOPS fatal', repr(e)[:200])
    if res is None or len(res) < 10000:
        try:
            res = try_finmind()
        except Exception as e:
            log('FinMind fatal', repr(e)[:200])
    if res is not None:
        res['rev'] = pd.to_numeric(res['rev'], errors='coerce')
        res['yoy'] = pd.to_numeric(res['yoy'], errors='coerce')
        res = res.dropna(subset=['rev'])[['ym', 'code', 'rev', 'yoy']]
        res.to_csv('data/revenue.csv.gz', index=False, compression='gzip')
        log('saved', len(res), 'rows,', res['ym'].nunique(), 'months')
    else:
        log('NO REVENUE DATA OBTAINED')
    with open('data/fetch_rev_log.txt', 'w') as f:
        f.write('\n'.join(LOG[-400:]))


if __name__ == '__main__':
    main()
