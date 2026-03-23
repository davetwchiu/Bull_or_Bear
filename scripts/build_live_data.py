#!/usr/bin/env python3
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_BASE = "https://api.stlouisfed.org/fred/series/observations"


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def fetch_fred_series(series_id: str, api_key: str, observation_start: str):
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "asc",
        "observation_start": observation_start,
    }
    url = API_BASE + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        payload = json.load(resp)
    observations = []
    for row in payload.get("observations", []):
        value = row.get("value")
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            observations.append({"date": row.get("date"), "value": number})
    if not observations:
        raise RuntimeError(f"No observations returned for {series_id}")
    return observations


def mean(values):
    return sum(values) / len(values)


def compute_ma(values, period):
    if len(values) < period:
        return None
    return mean(values[-period:])


def compute_drawdown(values, lookback=252):
    if not values:
        return None
    window = values[-lookback:] if len(values) >= lookback else values
    peak = max(window)
    last = window[-1]
    if peak <= 0:
        return None
    return ((peak - last) / peak) * 100.0


def compute_hold_days_around_200(prices):
    if len(prices) < 220:
        return None
    ma = []
    for i in range(len(prices)):
        if i < 199:
            ma.append(None)
        else:
            ma.append(mean(prices[i - 199:i + 1]))
    above = [None if ma[i] is None else prices[i] >= ma[i] for i in range(len(prices))]
    idx = len(above) - 1
    while idx >= 0 and above[idx] is None:
        idx -= 1
    if idx < 0:
        return None
    if above[idx] is False:
        count = 0
        idx -= 1
        while idx >= 0 and above[idx] is True:
            count += 1
            idx -= 1
        return count
    count = 0
    while idx >= 0 and above[idx] is True:
        count += 1
        idx -= 1
    return count


def compute_sos_from_iursa(series):
    values = [row["value"] for row in series]
    if len(values) < 78:
        return None
    ma26 = []
    for i in range(len(values)):
        if i < 25:
            ma26.append(None)
        else:
            ma26.append(mean(values[i - 25:i + 1]))
    last_idx = len(ma26) - 1
    while last_idx >= 0 and ma26[last_idx] is None:
        last_idx -= 1
    if last_idx < 77:
        return None
    current = ma26[last_idx]
    prior = [v for v in ma26[last_idx - 52:last_idx] if v is not None]
    if len(prior) < 52:
        return None
    return current - min(prior)


def last(series):
    return series[-1]


def maybe_float_env(name: str):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def main():
    api_key = require_env("FRED_API_KEY")

    sp500 = fetch_fred_series("SP500", api_key, "2023-01-01")
    vix = fetch_fred_series("VIXCLS", api_key, "2024-01-01")
    spread = fetch_fred_series("BAMLH0A0HYM2", api_key, "2024-01-01")
    iursa = fetch_fred_series("IURSA", api_key, "2023-01-01")

    sp_values = [row["value"] for row in sp500]
    ma200 = compute_ma(sp_values, 200)
    drawdown = compute_drawdown(sp_values, 252)
    hold_days = compute_hold_days_around_200(sp_values)
    sos = compute_sos_from_iursa(iursa)

    if ma200 is None or drawdown is None or hold_days is None or sos is None:
        raise RuntimeError("Failed to compute one or more derived metrics")

    payload = {
        "as_of": last(sp500)["date"],
"marketAsOf": min(last(sp500)["date"], last(vix)["date"], last(spread)["date"]),
"sosAsOf": last(iursa)["date"],
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sp500": round(last(sp500)["value"], 2),
        "ma200": round(ma200, 2),
        "vix": round(last(vix)["value"], 2),
        "creditSpreadBp": int(round(last(spread)["value"]*100)),
        "sos": round(sos, 3),
        "drawdownPct": round(drawdown, 2),
        "holdDaysAbove200": int(hold_days),
        "polymarketRecessionProb": maybe_float_env("POLYMARKET_RECESSION_PROB"),
        "latestDates": {
            "sp500": last(sp500)["date"],
            "vix": last(vix)["date"],
            "spread": last(spread)["date"],
            "iursa": last(iursa)["date"],
        },
        "sources": {
            "sp500": "FRED SP500",
            "vix": "FRED VIXCLS",
            "spread": "FRED BAMLH0A0HYM2",
            "iursa": "FRED IURSA",
            "sos_method": "26-week moving average of IURSA minus prior 52-week minimum 26-week average",
        },
    }

    out = Path("data/live.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} for {payload['as_of']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
