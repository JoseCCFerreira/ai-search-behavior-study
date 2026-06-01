import plotly.express as px
import pandas as pd


def line_chart(df: pd.DataFrame, x: str, y: str, color: str, title: str):
    return px.line(df, x=x, y=y, color=color, title=title)


def bar_chart(df: pd.DataFrame, x: str, y: str, color: str, title: str):
    return px.bar(df, x=x, y=y, color=color, title=title)
