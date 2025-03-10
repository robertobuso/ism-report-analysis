# setup.py
import os
import sys
import argparse
import logging
from google_auth import get_google_sheets_service
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/setup.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def setup_environment():
    """Set up the environment for the ISM Report Analysis system."""
    # Create directories if they don't exist
    os.makedirs("pdfs", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)
    
    # Load existing environment
    load_dotenv()
    
    # Check for API keys
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        logger.info("OPENAI_API_KEY not found in environment variables.")
        key = input("Enter your OpenAI API key: ")
        with open(".env", "a") as env_file:
            env_file.write(f"OPENAI_API_KEY={key}\n")
    
    # Generate a secret key for Flask
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        import secrets
        secret_key = secrets.token_hex(16)
        with open(".env", "a") as env_file:
            env_file.write(f"SECRET_KEY={secret_key}\n")
    
    # Set up Google authentication
    try:
        logger.info("Setting up Google Sheets authentication...")
        service = get_google_sheets_service()
        logger.info("Google Sheets authentication successful!")
    except Exception as e:
        logger.error(f"Error with Google Sheets authentication: {str(e)}")
        logger.info("Please ensure you have downloaded the credentials.json file from Google Cloud Console.")
        logger.info("1. Go to https://console.cloud.google.com/")
        logger.info("2. Create a new project or select an existing one")
        logger.info("3. Enable the Google Sheets API")
        logger.info("4. Create OAuth credentials (Desktop app)")
        logger.info("5. Download the credentials and save as 'credentials.json' in this directory")
    
    logger.info("\nSetup complete!\n")
    logger.info("To process a single PDF:")
    logger.info("python main.py --pdf path/to/your/ism_report.pdf")
    logger.info("\nTo process all PDFs in a directory:")
    logger.info("python main.py --dir path/to/your/pdf_directory")
    logger.info("\nTo run the web application:")
    logger.info("flask run")

if __name__ == "__main__":
    # Create directories first
    os.makedirs("logs", exist_ok=True)
    
    parser = argparse.ArgumentParser(description="Set up the ISM Report Analysis system")
    parser.add_argument("--force", action="store_true", help="Force setup even if already configured")
    args = parser.parse_args()
    
    if args.force or not os.path.exists(".env") or not os.path.exists("token.pickle"):
        setup_environment()
    else:
        logger.info("Environment already set up. Use --force to reconfigure.")