import os
import sqlite3
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/migration.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Import db_utils to get database path
from db_utils import DATABASE_PATH

def migrate_database():
    """Migrate database to add report_type column and update existing records."""
    conn = None
    try:
        logger.info(f"Starting database migration for {DATABASE_PATH}")
        
        # Connect to the database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Check if report_type column exists in reports table
        cursor.execute("PRAGMA table_info(reports)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'report_type' not in columns:
            logger.info("Adding report_type column to reports table")
            
            # Add the report_type column
            cursor.execute('''
            ALTER TABLE reports ADD COLUMN report_type TEXT DEFAULT 'Manufacturing' NOT NULL
            ''')
            
            # Update existing records to Manufacturing
            cursor.execute('''
            UPDATE reports SET report_type = 'Manufacturing'
            ''')
            
            # Create index for report_type column
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type)')
            
            conn.commit()
            logger.info("Successfully added report_type column and updated existing records")
        else:
            logger.info("report_type column already exists in reports table")
        
        return True
    except sqlite3.Error as e:
        logger.error(f"Database migration error: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()
            logger.debug("Database connection closed after migration")

if __name__ == "__main__":
    logger.info("Starting database migration script")
    if migrate_database():
        logger.info("Database migration completed successfully")
    else:
        logger.error("Database migration failed")
        sys.exit(1)