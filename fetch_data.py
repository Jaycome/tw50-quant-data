import json, os, time
import yfinance as yf
import pandas as pd

# Superset of Taiwan 50 constituents (2026-07) + ETFs + index.
# Failures are skipped and recorded in manifest.json.
STOCKS = [
    '2330','2317','2454','2308','2382','2412','2881','2882','2891','2886',
    '2884','2885','2892','2880','2883','2887','5880','2890','2303','3711',
    '2379','3034','2345','3231','6669','2376','2357','4938','2327','2360',
    '3017','3661','3443','3008','2395','1216','1101','1301','1303','2002',
    '2207','2603','2912','5871','6446','3037','2383','3045','4904','2301',
    '2408','1590','2059','1519','6505','1326','2615','2609','3653','3529',
]
EXTRA = ['0050.TW','006208.TW','00631L.TW','^TWII']

os.makedirs('data', exist_ok=True)
ok, fail = [], []

def fetch(sym, name):
    for attempt in range(3):
        try:
            df = yf.download(sym, start='2010-01-01', auto_adjust=True, progress=False)
            if df is not None and len(df) > 100:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df[['Open','High','Low','Close','Volume']].round(4)
                df.to_csv(f'data/{name}.csv')
                return True
        except Exception as e:
            print(sym, 'err', e)
        time.sleep(2 + attempt * 3)
    return False

for code in STOCKS:
    sym = code + '.TW'
    if fetch(sym, code):
        ok.append(code)
    elif fetch(code + '.TWO', code):
        ok.append(code)
    else:
        fail.append(code)
    time.sleep(0.5)

for sym in EXTRA:
    name = sym.replace('^','IDX_').replace('.TW','')
    (ok if fetch(sym, name) else fail).append(sym)
    time.sleep(0.5)

json.dump({'ok': ok, 'fail': fail, 'updated': pd.Timestamp.now().isoformat()},
          open('manifest.json','w'), indent=1)
print('ok:', len(ok), 'fail:', fail)
