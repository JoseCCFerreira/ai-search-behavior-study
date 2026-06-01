import pandas as pd
from src.data_processing.clean_data import fill_missing, remove_duplicates, standardize_dates


def test_standardize_dates():
    df = pd.DataFrame({"date": ["2024-01-15", "2024-02-20"]})
    result = standardize_dates(df.copy())
    assert result["date"].dtype == "datetime64[ns]"
    assert result["date"].iloc[0].month == 1


def test_remove_duplicates():
    df = pd.DataFrame({"a": [1, 1, 2]})
    result = remove_duplicates(df)
    assert len(result) == 2


def test_fill_missing():
    df = pd.DataFrame({"a": [1, None, 3]})
    result = fill_missing(df)
    assert result["a"].iloc[1] == 1
