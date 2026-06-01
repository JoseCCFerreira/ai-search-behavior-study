import pandas as pd
from sklearn.cluster import KMeans


def kmeans_cluster(df: pd.DataFrame, n_clusters: int = 3, random_state: int = 42) -> pd.DataFrame:
    features = df.select_dtypes(include=["number"]).fillna(0)
    model = KMeans(n_clusters=n_clusters, random_state=random_state)
    labels = model.fit_predict(features)
    df["cluster"] = labels
    return df
