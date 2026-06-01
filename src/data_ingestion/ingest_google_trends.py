import pandas as pd
from pathlib import Path
from pytrends.request import TrendReq


def fetch_google_trends(keywords, region="Worldwide", timeframe="today 5-y") -> pd.DataFrame:
    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload(keywords, cat=0, timeframe=timeframe, geo="", gprop="")
    data = pytrends.interest_over_time()
    if data.empty:
        return pd.DataFrame()
    data = data.reset_index().rename(columns={"date": "date"})
    data["region"] = region
    return data


def read_google_trends_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["date"])
