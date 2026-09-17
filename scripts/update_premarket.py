#!/usr/bin/env python3
import json
import math
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

DATA = Path("data.json")
NY = ZoneInfo("America/New_York")
TAIPEI = ZoneInfo("Asia/Taipei")
PRE_OPEN = dtime(4, 0)
REGULAR_OPEN = dtime(9, 30)


def finite(x):
    try:
        x = float(x)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def clear_premarket(stock):
    changed = False
    for key in ("preMarketPrice", "preMarketPct", "preMarketAsOf"):
        if stock.get(key) is not None:
            stock[key] = None
            changed = True
    if stock.get("preMarketState") != "CLOSED":
        stock["preMarketState"] = "CLOSED"
        changed = True
    return changed


def latest_premarket_price(symbol, session_date):
    hist = yf.Ticker(symbol).history(
        period="2d",
        interval="5m",
        prepost=True,
        auto_adjust=False,
        actions=False,
    )
    if hist is None or hist.empty or "Close" not in hist:
        raise RuntimeError("no intraday data")

    idx = pd.DatetimeIndex(hist.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    idx = idx.tz_convert(NY)
    hist = hist.copy()
    hist.index = idx

    mask = [
        ts.date() == session_date and PRE_OPEN <= ts.time().replace(tzinfo=None) < REGULAR_OPEN
        for ts in hist.index
    ]
    pre = hist.loc[mask]
    pre = pre.dropna(subset=["Close"])
    if pre.empty:
        raise RuntimeError("no premarket bars yet")

    price = finite(pre["Close"].iloc[-1])
    if price is None:
        raise RuntimeError("invalid premarket price")
    stamp = pre.index[-1].strftime("%Y-%m-%d %H:%M ET")
    return round(price, 2), stamp


def main():
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    now_ny = datetime.now(NY)
    session_date = now_ny.date()
    in_premarket = PRE_OPEN <= now_ny.time().replace(tzinfo=None) < REGULAR_OPEN and now_ny.weekday() < 5

    changed = False
    warnings = {}

    if not in_premarket:
        for stock in payload.get("watchlist", []):
            changed = clear_premarket(stock) or changed
        payload["preMarketStatus"] = "CLOSED"
        payload["preMarketUpdatedAt"] = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M Asia/Taipei")
    else:
        for stock in payload.get("watchlist", []):
            symbol = stock["ticker"]
            try:
                price, stamp = latest_premarket_price(symbol, session_date)
                regular_close = finite(stock.get("price"))
                pct = None if regular_close in (None, 0) else round((price / regular_close - 1) * 100, 2)
                updates = {
                    "preMarketPrice": price,
                    "preMarketPct": pct,
                    "preMarketAsOf": stamp,
                    "preMarketState": "PRE",
                }
                for key, value in updates.items():
                    if stock.get(key) != value:
                        stock[key] = value
                        changed = True
            except Exception as exc:
                warnings[symbol] = str(exc)

        payload["preMarketStatus"] = "PRE"
        payload["preMarketUpdatedAt"] = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M Asia/Taipei")

    if warnings:
        payload["preMarketWarnings"] = warnings
    else:
        payload.pop("preMarketWarnings", None)

    # Always write during scheduled premarket checks so the timestamp/status stays truthful.
    # Outside premarket, only write if stale PRE fields need clearing.
    if in_premarket or changed:
        DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Premarket snapshot updated. status={payload.get('preMarketStatus')} warnings={len(warnings)}")
    else:
        print("Premarket closed and no stale fields to clear; no data.json change.")


if __name__ == "__main__":
    main()
