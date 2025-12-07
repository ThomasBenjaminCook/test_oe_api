import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, List
from contextlib import asynccontextmanager

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

API_BASE = "https://api.openelectricity.org.au/v4/market/network/NEM"
NETWORK_REGION = "NSW1"
INTERVAL = "5m"
METRIC = "price"
MIN_POINTS = 3

load_dotenv(".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = httpx.AsyncClient(timeout=10.0)
    try:
        yield
    finally:
        client: httpx.AsyncClient | None = getattr(app.state, "client", None)
        if client:
            await client.aclose()


app = FastAPI(title="Open Electricity proxy", version="0.1.0", lifespan=lifespan)


def _get_auth_header() -> dict[str, str]:
    token = os.getenv("OPENELECTRICITY_API_TOKEN") or os.getenv("OPEN_ELECTRICITY_API_KEY")
    if not token:
        raise HTTPException(
            status_code=500,
            detail="OPENELECTRICITY_API_TOKEN or OPEN_ELECTRICITY_API_KEY is not set",
        )
    return {"Authorization": f"Bearer {token}"}


def _time_window_minutes(minutes: int = 30) -> tuple[str, str]:
    """Return naive (date_start, date_end) ISO strings in network local time (AEST/AEDT)."""
    tz = ZoneInfo("Australia/Sydney")
    end_dt = datetime.now(tz) - timedelta(minutes=30)
    start_dt = end_dt - timedelta(minutes=minutes)
    # API expects timezone-naive timestamps in network local time.
    end_local = end_dt.replace(tzinfo=None)
    start_local = start_dt.replace(tzinfo=None)
    return start_local.isoformat(timespec="seconds"), end_local.isoformat(timespec="seconds")


def _extract_prices(payload: dict[str, Any]) -> List[float]:
    data = payload.get("data") if isinstance(payload, dict) else []
    series_list = data if isinstance(data, list) else []

    numeric_values: list[float] = []

    for series in series_list:
        if not isinstance(series, dict):
            continue
        if series.get("metric") != METRIC:
            continue

        results = series.get("results")
        if not isinstance(results, list):
            continue

        for result in results:
            if not isinstance(result, dict):
                continue
            cols = result.get("columns") or {}
            region = cols.get("region") or cols.get("network_region") or cols.get("code")
            if region and str(region).upper() != NETWORK_REGION:
                continue

            rows = result.get("data") or []
            if not isinstance(rows, list):
                continue
            for row in rows:
                # Expecting [timestamp, value]
                if isinstance(row, (list, tuple)) and len(row) >= 2 and isinstance(row[1], (int, float)):
                    numeric_values.append(float(row[1]))
                elif isinstance(row, dict):
                    val = row.get("value") or row.get("price") or row.get("v")
                    if isinstance(val, (int, float)):
                        numeric_values.append(float(val))
                elif isinstance(row, (int, float)):
                    numeric_values.append(float(row))

    return numeric_values


@app.get("/average-price")
async def get_average_price() -> dict[str, Any]:
    client: httpx.AsyncClient = app.state.client
    date_start, date_end = _time_window_minutes(45)
    params = {
        "metrics": METRIC,
        "interval": INTERVAL,
        "network_region": NETWORK_REGION,
        "primary_grouping": "network_region",
        "date_start": date_start,
        "date_end": date_end,
    }

    try:
        response = await client.get(API_BASE, params=params, headers=_get_auth_header())
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream request failed: {exc}") from exc

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    payload = response.json()
    values = _extract_prices(payload)
    if len(values) < MIN_POINTS:
        raise HTTPException(status_code=502, detail="Upstream response did not contain enough price points")

    last_three = values[-MIN_POINTS:]
    average_price = sum(last_three) / len(last_three)

    return {
        "network_region": NETWORK_REGION,
        "interval": INTERVAL,
        "points_used": len(last_three),
        "price_points": last_three,
        "average_price": average_price,
        "units": "$ / MWh",
    }


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Use /average-price to fetch the latest NSW average price"}


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
