from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DB_PATH = DATA_DIR / "database" / "ai_search_behavior.duckdb"

GOOGLE_TRENDS_OUTPUT = RAW_DIR / "google_trends" / "google_trends_demo.csv"
SEARCH_ENGINE_CSV = RAW_DIR / "statcounter" / "search_engine_share_demo.csv"
BROWSER_CSV = RAW_DIR / "statcounter" / "browser_share_demo.csv"
AI_TRAFFIC_CSV = RAW_DIR / "similarweb" / "ai_tool_traffic_demo.csv"
EVENTS_CSV = RAW_DIR / "events" / "events.csv"

REGIONS = [
    "Portugal",
    "United States",
    "Germany",
    "Brazil",
    "United Kingdom",
    "India",
    "Worldwide",
]

GOOGLE_TRENDS_KEYWORDS = [
    "ChatGPT",
    "Google",
    "Gemini AI",
    "Microsoft Copilot",
    "Perplexity AI",
    "Claude AI",
    "DeepSeek",
    "Grok AI",
    "search engine",
    "AI chatbot",
    "how to use ChatGPT",
    "best AI tool",
]

SEARCH_ENGINES = ["Google", "Bing", "Yahoo", "DuckDuckGo", "Yandex", "Baidu"]
BROWSERS = ["Chrome", "Safari", "Edge", "Firefox", "Samsung Internet", "Opera"]
AI_TOOLS = ["ChatGPT", "Gemini", "Copilot", "Perplexity", "Claude", "DeepSeek", "Grok"]

HYPOTHESIS = {
    "H1": "AI tool interest growth is associated with relative decline in traditional search behavior.",
    "H2": "ChatGPT, Gemini, and Perplexity show different regional patterns.",
    "H3": "AI tool adoption correlates more with search engine market share change than browser market share.",
    "H4": "Some countries have accelerated AI adoption compared to others.",
    "H5": "Lagged relationships exist between AI adoption and search engine trends.",
    "H6": "Future distribution may fragment across multiple AI tools, not a single dominant platform.",
    "H7": "AI integration in search engines may blur traditional search vs assistant roles.",
    "H8": "AI-first platforms may gradually shift how users seek information.",
}
