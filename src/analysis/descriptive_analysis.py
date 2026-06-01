import pandas as pd


def compare_interest(df: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    return df[df["keyword"].isin(keywords)]


def top_growth_by_region(df: pd.DataFrame, value_column: str, top_n: int = 5) -> pd.DataFrame:
    return df.groupby("region")[value_column].mean().nlargest(top_n).reset_index()
