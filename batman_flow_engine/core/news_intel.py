from __future__ import annotations
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone


def gdelt_fetch(keyword: str, lookback_hours: int = 48, max_records: int = 250) -> pd.DataFrame:
    """
    Public GDELT 2.1 DOC API query (news articles index).
    This is a lightweight narrative-intensity signal (counts + sources + timestamps).
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=lookback_hours)
    # GDELT expects format: YYYYMMDDHHMMSS
    fmt = "%Y%m%d%H%M%S"
    query = {
        "query": keyword,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": str(max_records),
        "startdatetime": start.strftime(fmt),
        "enddatetime": now.strftime(fmt),
        "sort": "datedesc",
    }
    r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=query, timeout=20)
    r.raise_for_status()
    js = r.json()
    arts = js.get("articles", [])
    if not arts:
        return pd.DataFrame()
    df = pd.DataFrame(
        [
            {
                "datetime": a.get("seendate"),
                "title": a.get("title"),
                "sourceCountry": a.get("sourceCountry"),
                "sourceCommonName": a.get("sourceCommonName"),
                "url": a.get("url"),
            }
            for a in arts
        ]
    )
    return df


def narrative_intensity(keywords: list[str], lookback_hours: int = 48, max_records: int = 250) -> dict:
    total = 0
    by_kw = {}
    samples = {}
    for kw in keywords:
        try:
            df = gdelt_fetch(kw, lookback_hours, max_records)
            c = int(len(df))
            total += c
            by_kw[kw] = c
            if c:
                samples[kw] = df.head(3).to_dict(orient="records")
        except Exception:
            by_kw[kw] = None
    return {"total_hits": total, "by_keyword": by_kw, "samples": samples}
