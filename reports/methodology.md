# Methodology

## Objective

This study investigates the relationship between traditional search behavior, browser usage, search engine market share, and AI assistant adoption.

## Data sources

- Google Trends synthetic data and manual CSV imports.
- StatCounter GlobalStats search engine and browser share data.
- Similarweb-style AI traffic metrics.
- Event annotations for product launches and feature updates.

## Cleaning and normalization

- Convert dates to monthly periods.
- Standardize region and platform naming.
- Create dimension tables for dates, regions and platforms.
- Build fact tables for trends, market share, browser share, AI traffic and events.

## Analysis

- Use descriptive analytics to compare trends and distributions.
- Apply correlation and lag analysis to identify lead/lag relationships.
- Use industry-standard metrics such as moving averages and growth rates.

## Clustering

- Use clustering methods to group countries, platforms or periods by behavior.
- Provide PCA visualizations for cluster interpretation.

## Forecasting

- Use baseline, moving average and time-series model templates.
- Evaluate using MAE, RMSE and MAPE.
