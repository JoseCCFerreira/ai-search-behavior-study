import pandas as pd


def naive_forecast(series: pd.Series, periods: int) -> pd.Series:
    return pd.Series([series.iloc[-1]] * periods)


def moving_average_forecast(series: pd.Series, window: int = 3) -> pd.Series:
    return series.rolling(window=window, min_periods=1).mean()


def prepare_forecast_horizon(series: pd.Series, periods: int) -> pd.Series:
    last_date = series.index[-1]
    return pd.date_range(start=last_date + pd.offsets.MonthBegin(1), periods=periods, freq="MS")
