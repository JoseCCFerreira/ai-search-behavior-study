import pandas as pd


def pearson_correlation(df: pd.DataFrame) -> pd.DataFrame:
    return df.corr(method="pearson")


def spearman_correlation(df: pd.DataFrame) -> pd.DataFrame:
    return df.corr(method="spearman")
