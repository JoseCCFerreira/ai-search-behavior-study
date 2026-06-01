import pandas as pd


def normalize_category(df: pd.DataFrame, column: str, mapping: dict[str, str]) -> pd.DataFrame:
    df[column] = df[column].replace(mapping)
    return df


def normalize_values(df: pd.DataFrame, column: str, scale: float = 100.0) -> pd.DataFrame:
    if column in df:
        max_value = df[column].max() or 1
        df[f"normalized_{column}"] = df[column] / max_value * scale
    return df
