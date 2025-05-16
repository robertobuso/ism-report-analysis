import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_NAME = 'ism_data.db' # Define DB name consistently

# --- Use the SAME Correct Path Determination Logic ---
railway_volume_path = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH')

if railway_volume_path:
    # Running in Railway
    DB_DIR = railway_volume_path
    DB_PATH = os.path.join(DB_DIR, DATABASE_NAME) # Assign to DB_PATH used by config
    logger.info(f"Config: Detected Railway environment. Using DB path: {DB_PATH}")
else:
    # Running locally
    DB_DIR = os.getcwd()
    DB_PATH = os.path.join(DB_DIR, DATABASE_NAME) # Assign to DB_PATH used by config
    logger.info(f"Config: Running in local environment. Using DB path: {DB_PATH}")

# Google Custom Search API settings - use the specific key for search
GOOGLE_API_KEY = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

# OpenAI API settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o"

# Search settings
MAX_SEARCH_RESULTS = 5
MAX_ARTICLE_LENGTH = 5000  # Maximum characters to extract from an article

# Web Insight settings
SIGNIFICANT_CHANGE_THRESHOLD = 1.0  # Minimum change to consider significant
MAX_TRENDS_TO_DISPLAY = 5  # Maximum number of trends to display