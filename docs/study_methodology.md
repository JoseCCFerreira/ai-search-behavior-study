# Study Methodology

## Objective

This study evaluates the relationship between traditional search, browser usage, search engine market share, and conversational AI assistant adoption.

## Hypotheses

- H1: Growth in AI interest is associated with relative decline in traditional search.
- H2: ChatGPT, Gemini, and Perplexity show different regional adoption patterns.
- H3: AI adoption is more tightly linked to search engine share changes than browser share.
- H4: Certain countries exhibit accelerated AI adoption.
- H5: Lagged relationships exist between AI tool interest and search engine behavior.
- H6: Future distribution may fragment across several AI tools.
- H7: AI integration in search may blur the distinction between search engines and assistants.
- H8: AI-first platforms may gradually change how users look for information.

## Data methodology

- Use monthly periods to align Google Trends, StatCounter, and AI traffic data.
- Normalize region and platform names across sources.
- Create dimension tables for dates, regions, and platforms in DuckDB.
- Build raw fact tables and a consolidated analytical mart for monthly comparison.

## Analytical methodology

- Apply descriptive analysis to compare search engines, browsers, and AI tools.
- Compute growth rates, rolling averages, and volatility metrics.
- Use correlation and lag analysis to identify lead/lag behavior.
- Support clustering and forecasting via an analytical mart.

## Limitations

- Google Trends is a relative search interest index, not absolute volume.
- Browser and search share are not perfect proxies for intent.
- AI traffic data may be incomplete without paid or manual sources.
- Correlation does not imply causation.
