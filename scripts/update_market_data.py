#!/usr/bin/env python3
# Refresh trigger: 2026-09-18
import copy, json, math
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal
import requests
import yfinance as yf

DATA = Path("data.json")
MARKET_JS = Path("market-data.js")
TAIPEI = ZoneInfo("Asia/Taipei")
NEW_YORK = ZoneInfo("America/New_York")
TECH = ("price","dayPct","rsi14","ma20","ma50","ma200")
FUND = ("revenueGrowth","fcfMargin","sbcRevenue","forwardPE","evSales","pFcf")

def sync_market_js(payload):
    MARKET_JS.write_text(
        "window.MARKET_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )


def num(x):
    try:
        x = float(x)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def row(df, names):
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            s = pd.to_numeric(df.loc[n], errors="coerce").dropna()
            if not s.empty:
                return s
    return None


def ttm(s):
    if s is None:
        return None
    v = [num(x) for x in s.iloc[:4]]
    return sum(v) if len(v) == 4 and all(x is not None for x in v) else None


def yoy(s):
    if s is None or len(s) < 5:
        return None
    a, b = num(s.iloc[0]), num(s.iloc[4])
    return None if a is None or b in (None, 0) else (a / b - 1) * 100


def expected_session():
    now = pd.Timestamp.now(tz="UTC")
    cal = mcal.get_calendar("NYSE")
    sched = cal.schedule(start_date=(now - pd.Timedelta(days=14)).date(), end_date=(now + pd.Timedelta(days=1)).date())
    done = sched[sched["market_close"] <= now]
    if done.empty: raise RuntimeError("No completed NYSE session found")
    return done.index[-1].date().isoformat()


def history(symbol, expected):
    params = {
        "range": "3y",
        "interval": "1d",
        "includePrePost": "false",
        "events": "div,splits",
    }
    result = None
    last_error = None
    for host in ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"):
        try:
            r = requests.get(
                f"{host}/v8/finance/chart/{symbol}",
                params=params,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            )
            r.raise_for_status()
            payload = r.json()
            result = (payload.get("chart", {}).get("result") or [None])[0]
            if result:
                break
            last_error = payload.get("chart", {}).get("error")
        except Exception as e:
            last_error = str(e)
    if not result:
        raise RuntimeError(f"chart api failed: {last_error}")

    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((result.get("indicators") or {}).get("adjclose") or [{}])[0]
    closes = quote.get("close") or []
    adjcloses = adj.get("adjclose") or []

    rows = []
    for i, ts in enumerate(timestamps):
        if i >= len(closes):
            continue
        raw = num(closes[i])
        if raw is None:
            continue
        day = datetime.fromtimestamp(int(ts), tz=ZoneInfo("UTC")).astimezone(NEW_YORK).date().isoformat()
        indicator = raw
        if i < len(adjcloses):
            av = num(adjcloses[i])
            if av is not None:
                indicator = av
        rows.append((day, raw, indicator))

    if not rows:
        raise RuntimeError("no daily chart rows")

    df = pd.DataFrame(rows, columns=["Session", "RawClose", "IndicatorClose"])
    df = df.drop_duplicates(subset=["Session"], keep="last").sort_values("Session")
    if expected not in set(df["Session"]):
        raise RuntimeError(f"latest_session={df['Session'].iloc[-1]}, expected={expected}")
    df = df.loc[df["Session"] <= expected].copy()
    if len(df) < 210:
        raise RuntimeError(f"only {len(df)} rows")
    df.index = pd.RangeIndex(len(df))
    return df


def technicals(df):
    raw = pd.to_numeric(df["RawClose"], errors="coerce").dropna(); c = pd.to_numeric(df["IndicatorClose"], errors="coerce").dropna(); d = c.diff()
    gain, loss = d.clip(lower=0), -d.clip(upper=0); ag = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean(); al = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean(); rs = ag/al.replace(0,float("nan")); rsi=100-100/(1+rs)
    rv = 100.0 if pd.isna(rsi.iloc[-1]) and al.iloc[-1] == 0 else float(rsi.iloc[-1])
    return {"price":round(float(raw.iloc[-1]),2),"dayPct":round((float(raw.iloc[-1])/float(raw.iloc[-2])-1)*100,2),"rsi14":round(rv,3),"ma20":round(float(c.rolling(20).mean().iloc[-1]),2),"ma50":round(float(c.rolling(50).mean().iloc[-1]),2),"ma200":round(float(c.rolling(200).mean().iloc[-1]),2)}


def fundamentals(symbol):
    t=yf.Ticker(symbol); inc,cf=t.quarterly_financials,t.quarterly_cashflow; rev=row(inc,("Total Revenue","Operating Revenue")); rev_ttm=ttm(rev); growth=yoy(rev); fcf=ttm(row(cf,("Free Cash Flow",)))
    if fcf is None:
        ocf=ttm(row(cf,("Operating Cash Flow","Total Cash From Operating Activities"))); capex=ttm(row(cf,("Capital Expenditure","Capital Expenditures")))
        if ocf is not None and capex is not None: fcf=ocf+capex if capex<=0 else ocf-capex
    sbc=ttm(row(cf,("Stock Based Compensation","Stock Based Compensation Expense")))
    try: info=t.get_info() or {}
    except Exception: info={}
    try: mcap=num(t.fast_info.get("market_cap"))
    except Exception: mcap=None
    mcap=mcap or num(info.get("marketCap")); ev,fpe=num(info.get("enterpriseValue")),num(info.get("forwardPE")); out={}
    if growth is not None: out["revenueGrowth"]=round(growth,1)
    if rev_ttm not in (None,0) and fcf is not None: out["fcfMargin"]=round(fcf/rev_ttm*100,1)
    if rev_ttm not in (None,0) and sbc is not None: out["sbcRevenue"]=round(sbc/rev_ttm*100,1)
    if fpe is not None and fpe>0: out["forwardPE"]=round(fpe,1)
    if rev_ttm not in (None,0) and ev is not None and ev>0: out["evSales"]=round(ev/rev_ttm,1)
    if mcap is not None and mcap>0 and fcf is not None and fcf>0: out["pFcf"]=round(mcap/fcf,1)
    return out


def main():
    old=json.loads(DATA.read_text(encoding="utf-8")); new=copy.deepcopy(old); expected=expected_session(); histories,failures={},{}
    for s in new.get("watchlist",[]):
        try: histories[s["ticker"]]=history(s["ticker"],expected)
        except Exception as e: failures[s["ticker"]]=str(e)
    if failures:
        print("Provider lag; data.json left untouched: "+json.dumps(failures)); return
    warnings={}
    for s in new.get("watchlist",[]):
        symbol=s["ticker"]; s.update(technicals(histories[symbol]))
        try: s.update(fundamentals(symbol))
        except Exception as e: warnings[symbol]=str(e)
    new["asOf"]=expected
    new["automation"]={"marketData":"Yahoo Finance Chart API daily bars","schedule":"07:17, 08:17, 09:17 and 11:17 Asia/Taipei with holiday-safe no-op","autoFields":list(TECH+FUND),"preservedFields":["aiOpportunity","companyQuality","valuation","riskReward","thesis","risk","bearPct","basePct","bullPct","ARR/cRPO/billings"]}
    if warnings: new["automation"]["warnings"]=warnings
    a,b=copy.deepcopy(old),copy.deepcopy(new); a.pop("updatedAt",None); b.pop("updatedAt",None)
    if a==b:
        sync_market_js(old)
        print(f"No changes; already current through {expected}.")
        return
    new["updatedAt"]=datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M Asia/Taipei"); DATA.write_text(json.dumps(new,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); sync_market_js(new); print(f"Updated data.json through {expected}.")

if __name__=="__main__": main()
