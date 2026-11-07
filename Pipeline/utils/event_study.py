"""Estimate abnormal returns using adjusted daily closing prices."""
from pathlib import Path
from datetime import date, timedelta
import re

import numpy as np
import pandas as pd
import yfinance as yf

from Data_Classes.event import DailyRow, Study
from Pipeline.utils.event_files import atomic_write

DEFAULT_CACHE = Path(__file__).resolve().parents[2] / "Data_Cache"


def _prices(ticker, start, end, cache):
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=\-]{0,31}", ticker):
        raise ValueError("Invalid ticker for price history")
    path = Path(cache) / "prices" / f"{ticker}.csv"
    prices = pd.Series(dtype=float, name="Close", index=pd.DatetimeIndex([]))
    if path.exists():
        prices = pd.read_csv(path, index_col=0, parse_dates=True)["Close"].dropna()
        if not prices.empty and prices.index.min().date() <= start + timedelta(days=7) and prices.index.max().date() >= end - timedelta(days=4):
            return prices.sort_index()

    try:
        history = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True, timeout=15)
    except Exception as error:
        if prices.empty:
            raise ValueError(f"Could not fetch price history for {ticker}") from error
        return prices.sort_index()
    if not history.empty:
        fresh = history["Close"].dropna()
        fresh.index = fresh.index.tz_localize(None).normalize()
        prices = fresh if prices.empty else pd.concat([prices, fresh])
        prices = prices[~prices.index.duplicated(keep="last")].sort_index()
        atomic_write(path, lambda file: prices.to_csv(file, header=["Close"]))
    return prices.loc[(prices.index >= pd.Timestamp(start)) & (prices.index < pd.Timestamp(end))]


def run_event_study(ticker, event_date, days_after=10, market_ticker=None, *, cache=DEFAULT_CACHE):
    if market_ticker is None:
        market_ticker = "^GSPC"
        if ticker.endswith(".L"):
            market_ticker = "^FTSE"
        elif ticker.endswith((".PA", ".DE", ".AS")):
            market_ticker = "^STOXX50E"

    incident = date.fromisoformat(event_date)
    start = incident - timedelta(days=200)
    end = min(date.today() + timedelta(days=1), incident + timedelta(days=30))
    if end <= incident:
        raise ValueError("No trading days available after the event")
    stock = _prices(ticker, start, end, cache)
    market = _prices(market_ticker, start, end, cache)
    # Use the same interval for both returns when exchange holidays differ.
    closes = pd.concat({"actual": stock, "market": market}, axis=1, join="inner").dropna()
    closes = closes.loc[(closes.index >= pd.Timestamp(start)) & (closes.index < pd.Timestamp(end))]
    returns = closes.pct_change(fill_method=None).dropna() * 100
    returns = returns[np.isfinite(returns).all(axis=1)]
    event_index = returns.index.searchsorted(pd.Timestamp(incident))
    if event_index < 120 or event_index == len(returns):
        raise ValueError("Insufficient trading history for the event study")

    estimation_window = returns.iloc[event_index - 120:event_index - 9]
    if estimation_window["market"].std() <= 0:
        raise ValueError("Benchmark returns have no variation")
    beta, alpha = np.polyfit(estimation_window["market"], estimation_window["actual"], 1)
    sigma = (estimation_window["actual"] - alpha - beta * estimation_window["market"]).std(ddof=2)
    if not np.isfinite(sigma) or sigma <= 1e-10:
        raise ValueError("Insufficient residual variation for the event study")

    window = returns.iloc[event_index - 10:event_index + days_after + 1].copy()
    window["expected"] = alpha + beta * window["market"]
    cumulative = window[["actual", "expected"]].cumsum()
    cumulative -= cumulative.iloc[9].copy()
    daily = []
    for day, (timestamp, row) in enumerate(window.iterrows(), start=-10):
        actual, expected = cumulative.loc[timestamp].map(lambda value: round(float(value), 2))
        daily.append(DailyRow(
            day=day, date=timestamp.date().isoformat(), actual_pct=round(float(row.actual), 2),
            expected_pct=round(float(row.expected), 2), abnormal_pct=round(float(row.actual - row.expected), 2),
            cum_actual_pct=actual, cum_expected_pct=expected,
            car_pct=round(actual - expected, 2) if day >= 0 else None,
        ))
    last = daily[-1]
    post_event_day_count = last.day + 1
    cumulative_abnormal_return = float(cumulative.iloc[-1]["actual"] - cumulative.iloc[-1]["expected"])
    t_statistic = round(cumulative_abnormal_return / (float(sigma) * post_event_day_count ** 0.5), 2)
    return Study(
        market_ticker=market_ticker, event_day=daily[10].date, days_after=last.day,
        beta=round(float(beta), 2), raw_return_pct=last.cum_actual_pct,
        market_return_pct=round(float(window["market"].iloc[10:].sum()), 2),
        expected_return_pct=last.cum_expected_pct, car_pct=last.car_pct,
        t_stat=t_statistic, is_significant=abs(t_statistic) >= 2, daily=daily,
    )
