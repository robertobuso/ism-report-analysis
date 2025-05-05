import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Google Custom Search API settings - use the specific key for search
GOOGLE_API_KEY = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

# OpenAI API settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o"

# Database settings
DB_PATH = os.environ.get('ISM_DB_PATH', '/data/ism_data.db')

# Search settings
MAX_SEARCH_RESULTS = 5
MAX_ARTICLE_LENGTH = 5000  # Maximum characters to extract from an article

# Web Insight settings
SIGNIFICANT_CHANGE_THRESHOLD = 1.0  # Minimum change to consider significant
MAX_TRENDS_TO_DISPLAY = 5  # Maximum number of trends to display