import pandas as pd


def add_rolling_features(df: pd.DataFrame, column: str, window: int = 3) -> pd.DataFrame:
    df = df.sort_values("date")
    df[f"rolling_{window}m"] = df[column].rolling(window=window, min_periods=1).mean()
    return df


def add_growth_features(df: pd.DataFrame, column: str) -> pd.DataFrame:
    df = df.sort_values("date")
    df[f"mom_{column}"] = df[column].pct_change()
    df[f"yoy_{column}"] = df[column].pct_change(periods=12)
    return df
