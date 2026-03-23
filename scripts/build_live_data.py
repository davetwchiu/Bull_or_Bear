#!/usr/bin/env python3
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests


FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()
POLYMARKET_RECESSION_PROB = os.environ.get("POLYMARKET_RECESSION_PROB", "").strip()


def fred_series(series_id: str):
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY is missing")

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "sort_order": "asc",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    out = []
    for obs in data.get("observations", []):
        v = obs.get("value", ".")
        if v in (".", "", None):
            continue
        try:
            out.append((obs["date"], float(v)))
        except Exception:
            continue
    return out


def last_value(series):
    if not series:
        return None
    return series[-1][1]


def moving_average(values, window: int):
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def trailing_drawdown_pct(values, lookback: int = 252):
    if not values:
        return None
    chunk = values[-lookback:] if len(values) >= lookback else values[:]
    peak = max(chunk)
    last = chunk[-1]
    if peak <= 0:
        return None
    return (peak - last) / peak * 100.0


def hold_days_above_200dma(spx_values):
    if len(spx_values) < 201:
        return None

    ma200_list = []
    for i in range(len(spx_values)):
        if i + 1 < 200:
            ma200_list.append(None)
        else:
            ma200_list.append(sum(spx_values[i - 199:i + 1]) / 200.0)

    if ma200_list[-1] is None:
        return None

    last_price = spx_values[-1]
    last_ma = ma200_list[-1]

    if last_price >= last_ma:
        count = 0
        i = len(spx_values) - 1
        while i >= 0 and ma200_list[i] is not None and spx_values[i] >= ma200_list[i]:
            count += 1
            i -= 1
        return count

    count = 0
    i = len(spx_values) - 2
    while i >= 0 and ma200_list[i] is not None and spx_values[i] >= ma200_list[i]:
        count += 1
        i -= 1
    return count


def compute_sos_from_iursa(iursa_values):
    if len(iursa_values) < 26:
        return None

    ma26 = []
    for i in range(len(iursa_values)):
        if i + 1 < 26:
            ma26.append(None)
        else:
            ma26.append(sum(iursa_values[i - 25:i + 1]) / 26.0)

    valid_ma26 = [x for x in ma26 if x is not None]
    if not valid_ma26:
        return None

    current_ma26 = valid_ma26[-1]

    trailing = valid_ma26[-52:] if len(valid_ma26) >= 52 else valid_ma26[:]
    trailing_min = min(trailing)

    return current_ma26 - trailing_min


def safe_round(x, n=3):
    if x is None:
        return None
    return round(float(x), n)


def main():
    sp500 = fred_series("SP500")
    vix = fred_series("VIXCLS")
    hy = fred_series("BAMLH0A0HYM2")
    iursa = fred_series("IURSA")

    sp500_values = [v for _, v in sp500]
    iursa_values = [v for _, v in iursa]

    sp500_last = last_value(sp500)
    vix_last = last_value(vix)
    hy_last = last_value(hy)

    ma200 = moving_average(sp500_values, 200)
    drawdown = trailing_drawdown_pct(sp500_values, 252)
    hold_days = hold_days_above_200dma(sp500_values)
    sos = compute_sos_from_iursa(iursa_values)

    as_of_candidates = []
    if sp500:
        as_of_candidates.append(sp500[-1][0])
    if vix:
        as_of_candidates.append(vix[-1][0])
    if hy:
        as_of_candidates.append(hy[-1][0])
    if iursa:
        as_of_candidates.append(iursa[-1][0])

    as_of = max(as_of_candidates) if as_of_candidates else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    payload = {
        "as_of": as_of,
        "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sp500": safe_round(sp500_last, 2),
        "ma200": safe_round(ma200, 2),
        "vix": safe_round(vix_last, 2),
        "creditSpreadBp": int(round(hy_last)) if hy_last is not None else None,
        "sos": safe_round(sos, 3),
        "polymarketRecessionProb": float(POLYMARKET_RECESSION_PROB) if POLYMARKET_RECESSION_PROB else None,
        "drawdownPct": safe_round(drawdown, 2),
        "holdDaysAbove200": hold_days,
        "sources": {
            "sp500": "FRED: SP500",
            "vix": "FRED: VIXCLS",
            "creditSpreadBp": "FRED: BAMLH0A0HYM2",
            "sos_input": "FRED: IURSA",
            "sos_method": "26-week moving average minus the minimum prior 26-week average over the trailing 52 weeks",
        },
    }

    out = Path("data/live.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} for {payload['as_of']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
