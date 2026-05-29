import os
from dotenv import load_dotenv

load_dotenv(override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

MODEL = "claude-sonnet-4-5-20250929"  # high-quality final responses
MODEL_FAST = "claude-haiku-4-5"        # cheap+fast for routing/classification/summarization
MAX_TOKENS = 1024
MAX_TOKENS_FAST = 512                  # smaller cap for fast model calls

# SYSTEM_PROMPT e NEWS_FEEDS rimossi: mai usati.
# Il system prompt reale è in personality.py (build_static_system_prompt).
# I feed RSS reali sono in news_feeds.json (letti da news.py/news_graph.py).
