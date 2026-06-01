import pandas as pd


def standardize_dates(df: pd.DataFrame, date_column: str = "date") -> pd.DataFrame:
    df[date_column] = pd.to_datetime(df[date_column], errors="coerce").dt.to_period("M").dt.to_timestamp()
    # ensure consistent dtype (nanoseconds) across environments
    df[date_column] = df[date_column].astype("datetime64[ns]")
    return df


def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop_duplicates()


def fill_missing(df: pd.DataFrame) -> pd.DataFrame:
    return df.ffill().fillna(0)
