import pandas as pd


def calculate_mom(series: pd.Series) -> pd.Series:
    return series.pct_change()


def calculate_yoy(series: pd.Series) -> pd.Series:
    return series.pct_change(periods=12)


def test_calculate_mom():
    series = pd.Series([100, 110, 121])
    expected = [None, 0.1, 0.1]
    result = calculate_mom(series)
    assert round(result.iloc[1], 2) == expected[1]
    assert round(result.iloc[2], 2) == expected[2]


def test_calculate_yoy():
    series = pd.Series(list(range(1, 14)))
    result = calculate_yoy(series)
    # For a series 1..13, YoY pct_change over 12 periods is (13-1)/1 = 12.0
    assert round(result.iloc[12], 2) == 12.0
