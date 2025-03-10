import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4"  # Using GPT-4 for better extraction accuracy

# Google Sheets configuration
GOOGLE_CREDENTIALS_FILE = "credentials.json"
GOOGLE_TOKEN_FILE = "token.pickle"
GOOGLE_SHEET_NAME = "ISM Manufacturing Report Analysis"

# ISM Report configuration
ISM_INDICES = [
    "New Orders", 
    "Production", 
    "Employment", 
    "Supplier Deliveries",
    "Inventories", 
    "Customers' Inventories", 
    "Prices", 
    "Backlog of Orders",
    "New Export Orders", 
    "Imports"
]

# Category mappings for each index
INDEX_CATEGORIES = {
    "New Orders": ["Growing", "Declining"],
    "Production": ["Growing", "Declining"],
    "Employment": ["Growing", "Declining"],
    "Supplier Deliveries": ["Slower", "Faster"],
    "Inventories": ["Higher", "Lower"],
    "Customers' Inventories": ["Too High", "Too Low"],
    "Prices": ["Increasing", "Decreasing"],
    "Backlog of Orders": ["Growing", "Declining"],
    "New Export Orders": ["Growing", "Declining"],
    "Imports": ["Growing", "Declining"]
}

# Logging configuration
LOG_FILE = "logs/ism_analysis.log"
LOG_LEVEL = "INFO"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds