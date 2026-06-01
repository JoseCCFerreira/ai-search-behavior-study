import pandas as pd


def forecast_naive(series: pd.Series, periods: int) -> pd.Series:
    return pd.Series([series.iloc[-1]] * periods)


def test_forecast_naive():
    series = pd.Series([10, 12, 14])
    result = forecast_naive(series, 3)
    assert len(result) == 3
    assert all(result == 14)


def test_future_dates():
    today = pd.Timestamp("2024-01-01")
    future = pd.date_range(start=today + pd.offsets.MonthBegin(1), periods=3, freq="MS")
    assert len(future) == 3
    assert future[0].month == 2
