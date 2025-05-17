import os
from dotenv import load_dotenv
from config_loader import config_loader

# Load environment variables
load_dotenv()

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o"  # Using GPT-4 for better extraction accuracy

# Google Sheets configuration
GOOGLE_CREDENTIALS_FILE = "credentials.json"
GOOGLE_TOKEN_FILE = "token.pickle"
GOOGLE_SHEET_NAME = "ISM Report Analysis"

# Get ISM Report configuration from config loader
MANUFACTURING_INDICES = config_loader.get_indices("Manufacturing")
SERVICES_INDICES = config_loader.get_indices("Services")

# Add configuration for Manufacturing at a Glance table
MANUFACTURING_TABLE_TAB_NAME = "Manufacturing at a Glance"
SERVICES_TABLE_TAB_NAME = "Services at a Glance"

# Logging configuration
LOG_FILE = "logs/ism_analysis.log"
LOG_LEVEL = "INFO"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# Ensure all required directories exist
os.makedirs("logs", exist_ok=True)
os.makedirs("pdfs", exist_ok=True)
os.makedirs("uploads", exist_ok=True)
os.makedirs("config", exist_ok=True)

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