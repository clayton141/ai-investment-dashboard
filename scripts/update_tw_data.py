#!/usr/bin/env python3
import json, math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import requests

DATA=Path("tw-data.json")
TPE=ZoneInfo("Asia/Taipei")

def num(x):
    try:
        x=float(x)
        return x if math.isfinite(x) else None
    except Exception:
        return None

def fetch_daily(symbol):
    params={"range":"3y","interval":"1d","includePrePost":"false","events":"div,splits"}
    last=None
    for host in ("https://query1.finance.yahoo.com","https://query2.finance.yahoo.com"):
        try:
            r=requests.get(f"{host}/v8/finance/chart/{symbol}",params=params,timeout=20,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"})
            r.raise_for_status()
            j=r.json()
            result=(j.get("chart",{}).get("result") or [None])[0]
            if result: break
            last=j.get("chart",{}).get("error")
        except Exception as e:
            result=None; last=str(e)
    if not result: raise RuntimeError(f"{symbol}: {last}")
    ts=result.get("timestamp") or []
    quote=((result.get("indicators") or {}).get("quote") or [{}])[0]
    adj=((result.get("indicators") or {}).get("adjclose") or [{}])[0]
    closes=quote.get("close") or []
    adjcloses=adj.get("adjclose") or []
    rows=[]
    for i,t in enumerate(ts):
        if i>=len(closes): continue
        raw=num(closes[i])
        if raw is None: continue
        day=datetime.fromtimestamp(int(t),tz=ZoneInfo("UTC")).astimezone(TPE).date().isoformat()
        ind=raw
        if i<len(adjcloses):
            av=num(adjcloses[i])
            if av is not None: ind=av
        rows.append((day,raw,ind))
    df=pd.DataFrame(rows,columns=["Session","RawClose","IndicatorClose"]).drop_duplicates("Session",keep="last").sort_values("Session")
    if len(df)<210: raise RuntimeError(f"{symbol}: only {len(df)} rows")
    return df

def tech(df):
    raw=pd.to_numeric(df["RawClose"],errors="coerce").dropna()
    c=pd.to_numeric(df["IndicatorClose"],errors="coerce").dropna()
    d=c.diff()
    gain=d.clip(lower=0); loss=-d.clip(upper=0)
    ag=gain.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    al=loss.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rs=ag/al.replace(0,float("nan"))
    rsi=100-100/(1+rs)
    rv=100.0 if pd.isna(rsi.iloc[-1]) and al.iloc[-1]==0 else float(rsi.iloc[-1])
    return {
      "price":round(float(raw.iloc[-1]),2),
      "dayPct":round((float(raw.iloc[-1])/float(raw.iloc[-2])-1)*100,2),
      "rsi14":round(rv,3),
      "ma20":round(float(c.rolling(20).mean().iloc[-1]),2),
      "ma50":round(float(c.rolling(50).mean().iloc[-1]),2),
      "ma200":round(float(c.rolling(200).mean().iloc[-1]),2),
      "asOf":str(df["Session"].iloc[-1])
    }

def main():
    payload=json.loads(DATA.read_text(encoding="utf-8"))
    dates=[]
    for s in payload["watchlist"]:
        t=tech(fetch_daily(s["ticker"]))
        s.update({k:v for k,v in t.items() if k!="asOf"})
        dates.append(t["asOf"])
    payload["asOf"]=min(dates) if dates else None
    payload["updatedAt"]=datetime.now(TPE).strftime("%Y-%m-%d %H:%M Asia/Taipei")
    DATA.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(payload,ensure_ascii=False))

if __name__=="__main__":
    main()
