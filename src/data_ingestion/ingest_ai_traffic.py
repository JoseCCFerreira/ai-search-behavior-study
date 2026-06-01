import pandas as pd
from pathlib import Path


def read_ai_traffic_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["date"]).fillna(0)
