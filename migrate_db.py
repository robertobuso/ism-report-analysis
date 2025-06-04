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
    """Migrate database to add report_type column to all tables and update existing records."""
    conn = None
    try:
        logger.info(f"Starting database migration for {DATABASE_PATH}")
        
        # Connect to the database
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # MIGRATE REPORTS TABLE
        cursor.execute("PRAGMA table_info(reports)")
        reports_columns = [col[1] for col in cursor.fetchall()]
        
        if 'report_type' not in reports_columns:
            logger.info("Adding report_type column to reports table")
            
            cursor.execute('''
            ALTER TABLE reports ADD COLUMN report_type TEXT DEFAULT 'Manufacturing' NOT NULL
            ''')
            
            cursor.execute('''
            UPDATE reports SET report_type = 'Manufacturing'
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type)')
            logger.info("Successfully migrated reports table")
        else:
            logger.info("report_type column already exists in reports table")
        
        # MIGRATE PMI_INDICES TABLE
        cursor.execute("PRAGMA table_info(pmi_indices)")
        pmi_columns = [col[1] for col in cursor.fetchall()]
        
        if 'report_type' not in pmi_columns:
            logger.info("Adding report_type column to pmi_indices table")
            
            cursor.execute('''
            ALTER TABLE pmi_indices ADD COLUMN report_type TEXT DEFAULT 'Manufacturing' NOT NULL
            ''')
            
            cursor.execute('''
            UPDATE pmi_indices SET report_type = 'Manufacturing'
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmi_indices_type ON pmi_indices(report_type)')
            logger.info("Successfully migrated pmi_indices table")
        else:
            logger.info("report_type column already exists in pmi_indices table")
        
        # MIGRATE INDUSTRY_STATUS TABLE
        cursor.execute("PRAGMA table_info(industry_status)")
        industry_columns = [col[1] for col in cursor.fetchall()]
        
        if 'report_type' not in industry_columns:
            logger.info("Adding report_type column to industry_status table")
            
            cursor.execute('''
            ALTER TABLE industry_status ADD COLUMN report_type TEXT DEFAULT 'Manufacturing' NOT NULL
            ''')
            
            cursor.execute('''
            UPDATE industry_status SET report_type = 'Manufacturing'
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_type ON industry_status(report_type)')
            logger.info("Successfully migrated industry_status table")
        else:
            logger.info("report_type column already exists in industry_status table")
        
        conn.commit()
        logger.info("All database migrations completed successfully")
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