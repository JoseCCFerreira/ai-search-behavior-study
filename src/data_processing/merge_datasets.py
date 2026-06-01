import pandas as pd


def merge_trend_and_share(trends: pd.DataFrame, share: pd.DataFrame, on: list[str]) -> pd.DataFrame:
    return trends.merge(share, on=on, how="outer")
