#!/usr/bin/env python3
import copy
import json
import math
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

DATA_PATH = Path("data.json")
TAIPEI = ZoneInfo("Asia/Taipei")
NEW_YORK = ZoneInfo("America/New_York")

TECH_FIELDS = ("price", "dayPct", "rsi14", "ma20", "ma50", "ma200")
FUND_FIELDS = ("revenueGrowth", "fcfMargin", "sbcRevenue", "forwardPE", "evSales", "pFcf")


def finite_number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def pick_row(frame, names):
    if frame is None or frame.empty:
        return None
    for name in names:
        if name in frame.index:
            row = pd.to_numeric(frame.loc[name], errors="coerce").dropna()
            return row if not row.empty else None
    return None


def ttm(row):
    if row is None:
        return None
    values = [finite_number(v) for v in row.iloc[:4].tolist()]
    values = [v for v in values if v is not None]
    return sum(values) if len(values) == 4 else None


def latest_quarter_yoy(row):
    if row is None or len(row) < 5:
        return None
    latest = finite_number(row.iloc[0])
    prior = finite_number(row.iloc[4])
    if latest is None or prior in (None, 0):
        return None
    return (latest / prior - 1) * 100


def market_history(ticker):
    hist = yf.Ticker(ticker).history(period="2y", interval="1d", auto_adjust=True)
    if hist is None or hist.empty:
        raise RuntimeError("no price history returned")
    hist = hist.dropna(subset=["Close"]).copy()

    # Never use an in-progress US trading day.
    now_ny = datetime.now(NEW_YORK)
    last_date = pd.Timestamp(hist.index[-1]).date()
    if last_date == now_ny.date() and now_ny.time() < dtime(16, 15):
        hist = hist.iloc[:-1]
    if len(hist) < 210:
        raise RuntimeError(f"insufficient history ({len(hist)} rows)")
    return hist


def technicals(hist):
    close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
    latest = float(close.iloc[-1])
    prev = float(close.iloc[-2])

    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + rs))
    if pd.isna(rsi.iloc[-1]) and avg_loss.iloc[-1] == 0:
        rsi_value = 100.0
    else:
        rsi_value = float(rsi.iloc[-1])

    return {
        "asOf": pd.Timestamp(hist.index[-1]).date().isoformat(),
        "price": round(latest, 2),
        "dayPct": round((latest / prev - 1) * 100, 2),
        "rsi14": round(rsi_value, 3),
        "ma20": round(float(close.rolling(20).mean().iloc[-1]), 2),
        "ma50": round(float(close.rolling(50).mean().iloc[-1]), 2),
        "ma200": round(float(close.rolling(200).mean().iloc[-1]), 2),
    }


def fundamentals(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    income = ticker.quarterly_financials
    cashflow = ticker.quarterly_cashflow

    revenue_row = pick_row(income, ("Total Revenue", "Operating Revenue"))
    revenue_ttm = ttm(revenue_row)
    revenue_growth = latest_quarter_yoy(revenue_row)

    fcf_row = pick_row(cashflow, ("Free Cash Flow",))
    fcf_ttm = ttm(fcf_row)
    if fcf_ttm is None:
        ocf = ttm(pick_row(cashflow, ("Operating Cash Flow", "Total Cash From Operating Activities")))
        capex = ttm(pick_row(cashflow, ("Capital Expenditure", "Capital Expenditures")))
        if ocf is not None and capex is not None:
            fcf_ttm = ocf + capex if capex <= 0 else ocf - capex

    sbc_ttm = ttm(pick_row(cashflow, ("Stock Based Compensation", "Stock Based Compensation Expense")))

    try:
        info = ticker.get_info() or {}
    except Exception:
        info = {}

    try:
        market_cap = finite_number(ticker.fast_info.get("market_cap"))
    except Exception:
        market_cap = None
    if market_cap is None:
        market_cap = finite_number(info.get("marketCap"))

    enterprise_value = finite_number(info.get("enterpriseValue"))
    forward_pe = finite_number(info.get("forwardPE"))

    out = {}
    if revenue_growth is not None:
        out["revenueGrowth"] = round(revenue_growth, 1)
    if revenue_ttm not in (None, 0) and fcf_ttm is not None:
        out["fcfMargin"] = round(fcf_ttm / revenue_ttm * 100, 1)
    if revenue_ttm not in (None, 0) and sbc_ttm is not None:
        out["sbcRevenue"] = round(sbc_ttm / revenue_ttm * 100, 1)
    if forward_pe is not None and forward_pe > 0:
        out["forwardPE"] = round(forward_pe, 1)
    if revenue_ttm not in (None, 0) and enterprise_value is not None and enterprise_value > 0:
        out["evSales"] = round(enterprise_value / revenue_ttm, 1)
    if market_cap is not None and market_cap > 0 and fcf_ttm is not None and fcf_ttm > 0:
        out["pFcf"] = round(market_cap / fcf_ttm, 1)
    return out


def main():
    original = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    candidate = copy.deepcopy(original)
    errors = {}
    as_of_dates = []

    for stock in candidate.get("watchlist", []):
        symbol = stock["ticker"]
        try:
            tech = technicals(market_history(symbol))
            as_of_dates.append(tech.pop("asOf"))
            stock.update(tech)
        except Exception as exc:
            errors.setdefault(symbol, []).append(f"technicals: {exc}")

        try:
            fresh_fundamentals = fundamentals(symbol)
            for key, value in fresh_fundamentals.items():
                if value is not None:
                    stock[key] = value
        except Exception as exc:
            errors.setdefault(symbol, []).append(f"fundamentals: {exc}")

        time.sleep(0.4)

    if as_of_dates:
        # All tickers should resolve to the same last complete US trading day.
        candidate["asOf"] = min(as_of_dates)

    # Curated qualitative fields stay unchanged until a research pass updates them.
    candidate["automation"] = {
        "marketData": "yfinance",
        "schedule": "Tue-Sat 08:35 Asia/Taipei",
        "autoFields": list(TECH_FIELDS + FUND_FIELDS),
        "preservedFields": [
            "aiOpportunity",
            "companyQuality",
            "valuation",
            "riskReward",
            "thesis",
            "risk",
            "bearPct",
            "basePct",
            "bullPct"
        ]
    }
    if errors:
        candidate["automation"]["warnings"] = errors

    comparable_old = copy.deepcopy(original)
    comparable_new = copy.deepcopy(candidate)
    comparable_old.pop("updatedAt", None)
    comparable_new.pop("updatedAt", None)

    if comparable_new == comparable_old:
        print("No dashboard data changes; leaving data.json untouched.")
        return

    candidate["updatedAt"] = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M Asia/Taipei")
    DATA_PATH.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print(f"Updated data.json through {candidate.get('asOf')}.")


if __name__ == "__main__":
    main()
