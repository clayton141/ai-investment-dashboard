#!/usr/bin/env python3
import copy
import io
import json
import math
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal
import requests
import yfinance as yf

DATA_PATH = Path("data.json")
TAIPEI = ZoneInfo("Asia/Taipei")
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


def expected_complete_session():
    now_utc = pd.Timestamp.now(tz="UTC")
    calendar = mcal.get_calendar("NYSE")
    start = (now_utc - pd.Timedelta(days=14)).date()
    end = (now_utc + pd.Timedelta(days=1)).date()
    schedule = calendar.schedule(start_date=start, end_date=end)
    completed = schedule[schedule["market_close"] <= now_utc]
    if completed.empty:
        raise RuntimeError("could not resolve latest completed NYSE session")
    return completed.index[-1].date().isoformat()


def yahoo_history(symbol):
    hist = yf.Ticker(symbol).history(period="2y", interval="1d", auto_adjust=True)
    if hist is None or hist.empty:
        raise RuntimeError("Yahoo returned no price history")
    return hist.dropna(subset=["Close"]).copy()


def stooq_history(symbol):
    end = datetime.now(TAIPEI).date()
    start = end - timedelta(days=800)
    url = (
        "https://stooq.com/q/d/l/"
        f"?s={symbol.lower()}.us&i=d&d1={start:%Y%m%d}&d2={end:%Y%m%d}"
    )
    response = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "ai-investment-dashboard/1.0"},
    )
    response.raise_for_status()
    frame = pd.read_csv(io.StringIO(response.text))
    if frame.empty or "Date" not in frame or "Close" not in frame:
        raise RuntimeError("Stooq returned no usable price history")
    frame["Date"] = pd.to_datetime(frame["Date"])
    frame = frame.set_index("Date").sort_index()
    return frame.dropna(subset=["Close"]).copy()


def truncate_to_expected(hist, expected):
    dates = pd.Index([pd.Timestamp(i).date().isoformat() for i in hist.index])
    if expected not in set(dates):
        return None
    mask = dates <= expected
    return hist.loc[mask].copy()


def validated_history(symbol, expected):
    problems = []
    for attempt in range(3):
        try:
            hist = yahoo_history(symbol)
            valid = truncate_to_expected(hist, expected)
            if valid is not None and len(valid) >= 210:
                return valid, "yfinance"
            last = pd.Timestamp(hist.index[-1]).date().isoformat()
            problems.append(f"Yahoo latest={last}, expected={expected}")
        except Exception as exc:
            problems.append(f"Yahoo error: {exc}")
        if attempt < 2:
            time.sleep(4 * (attempt + 1))

    try:
        hist = stooq_history(symbol)
        valid = truncate_to_expected(hist, expected)
        if valid is not None and len(valid) >= 210:
            return valid, "stooq"
        last = pd.Timestamp(hist.index[-1]).date().isoformat()
        problems.append(f"Stooq latest={last}, expected={expected}")
    except Exception as exc:
        problems.append(f"Stooq error: {exc}")

    raise RuntimeError("; ".join(problems))


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

    fcf_ttm = ttm(pick_row(cashflow, ("Free Cash Flow",)))
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
    expected = expected_complete_session()

    # Market data is atomic: either every ticker reaches the same completed session,
    # or we write nothing and let the later scheduled retry handle provider lag.
    histories = {}
    sources = {}
    failures = {}
    for stock in candidate.get("watchlist", []):
        symbol = stock["ticker"]
        try:
            histories[symbol], sources[symbol] = validated_history(symbol, expected)
        except Exception as exc:
            failures[symbol] = str(exc)

    if failures:
        raise RuntimeError(
            "Market data incomplete; data.json left untouched. "
            + json.dumps(failures, ensure_ascii=False)
        )

    warnings = {}
    for stock in candidate.get("watchlist", []):
        symbol = stock["ticker"]
        stock.update(technicals(histories[symbol]))
        try:
            stock.update(fundamentals(symbol))
        except Exception as exc:
            warnings.setdefault(symbol, []).append(f"fundamentals preserved: {exc}")

    candidate["asOf"] = expected
    candidate["automation"] = {
        "marketData": "Yahoo Finance with Stooq fallback",
        "schedule": "Tue-Sat 09:35 and 11:35 Asia/Taipei",
        "marketSources": sources,
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
            "bullPct",
            "ARR/cRPO/billings"
        ]
    }
    if warnings:
        candidate["automation"]["warnings"] = warnings

    comparable_old = copy.deepcopy(original)
    comparable_new = copy.deepcopy(candidate)
    comparable_old.pop("updatedAt", None)
    comparable_new.pop("updatedAt", None)

    if comparable_new == comparable_old:
        print(f"No changes; data.json already reflects {expected}.")
        return

    candidate["updatedAt"] = datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M Asia/Taipei")
    DATA_PATH.write_text(
        json.dumps(candidate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print(f"Updated data.json through {expected}.")


if __name__ == "__main__":
    main()
