import pandas as pd
from pathlib import Path


def read_events_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["event_date"]).fillna("")
