#!/usr/bin/env python3
import os
import sqlite3
import logging
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

def find_database_path():
    """Find the correct database path in Railway environment."""
    possible_paths = [
        '/data/ism_data.db',                    # Railway volume mount
        os.environ.get('ISM_DB_PATH'),          # Environment variable
        os.path.join(os.getcwd(), 'ism_data.db'), # Current directory
        '/app/ism_data.db',                     # App directory
    ]
    
    for path in possible_paths:
        if path and os.path.exists(path):
            logger.info(f"Found database at: {path}")
            return path
        elif path:
            logger.info(f"Checked path (not found): {path}")
    
    # If no existing database found, use the Railway volume path
    railway_volume = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '/data')
    db_path = os.path.join(railway_volume, 'ism_data.db')
    logger.info(f"No existing database found, will use: {db_path}")
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    return db_path

def check_tables_exist(db_path):
    """Check if the main tables exist in the database."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Found tables: {tables}")
        
        conn.close()
        
        required_tables = ['reports', 'pmi_indices', 'industry_status']
        return all(table in tables for table in required_tables)
    except Exception as e:
        logger.error(f"Error checking tables: {e}")
        return False

def initialize_database_schema(db_path):
    """Initialize database with the correct schema including report_type columns."""
    conn = None
    try:
        logger.info(f"Initializing database schema at: {db_path}")
        
        # Ensure database directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")
        
        # Create reports table with report_type column
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            report_date DATE NOT NULL,
            file_path TEXT,
            processing_date DATETIME NOT NULL,
            month_year TEXT NOT NULL,
            report_type TEXT DEFAULT 'Manufacturing' NOT NULL,
            UNIQUE(report_date, report_type)
        )
        ''')
        
        # Create pmi_indices table with report_type column
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS pmi_indices (
            id INTEGER PRIMARY KEY,
            report_date DATE NOT NULL,
            index_name TEXT NOT NULL,
            index_value DECIMAL(5,1) NOT NULL,
            direction TEXT NOT NULL,
            report_type TEXT NOT NULL,
            UNIQUE(report_date, index_name, report_type),
            FOREIGN KEY(report_date) REFERENCES reports(report_date)
        )
        ''')
        
        # Create industry_status table with report_type column
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS industry_status (
            id INTEGER PRIMARY KEY,
            report_date DATE NOT NULL,
            index_name TEXT NOT NULL,
            industry_name TEXT NOT NULL,
            status TEXT NOT NULL,
            category TEXT NOT NULL,
            rank INTEGER,
            report_type TEXT NOT NULL,
            UNIQUE(report_date, index_name, industry_name, report_type),
            FOREIGN KEY(report_date) REFERENCES reports(report_date)
        )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmi_indices_date ON pmi_indices(report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmi_indices_name ON pmi_indices(index_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmi_indices_type ON pmi_indices(report_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_date ON industry_status(report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_index ON industry_status(index_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_industry ON industry_status(industry_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_type ON industry_status(report_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type)')
        
        conn.commit()
        logger.info("Database schema initialized successfully with report_type columns")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing database schema: {str(e)}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def migrate_existing_database(db_path):
    """Migrate existing database to add report_type columns."""
    conn = None
    try:
        logger.info(f"Migrating existing database: {db_path}")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        migrations_applied = 0
        
        # Migrate reports table
        cursor.execute("PRAGMA table_info(reports)")
        reports_columns = [col[1] for col in cursor.fetchall()]
        
        if 'report_type' not in reports_columns:
            logger.info("Adding report_type column to reports table")
            cursor.execute('ALTER TABLE reports ADD COLUMN report_type TEXT DEFAULT "Manufacturing" NOT NULL')
            cursor.execute('UPDATE reports SET report_type = "Manufacturing" WHERE report_type IS NULL')
            migrations_applied += 1
        else:
            logger.info("reports table already has report_type column")
        
        # Migrate pmi_indices table
        cursor.execute("PRAGMA table_info(pmi_indices)")
        pmi_columns = [col[1] for col in cursor.fetchall()]
        
        if 'report_type' not in pmi_columns:
            logger.info("Adding report_type column to pmi_indices table")
            cursor.execute('ALTER TABLE pmi_indices ADD COLUMN report_type TEXT DEFAULT "Manufacturing" NOT NULL')
            cursor.execute('UPDATE pmi_indices SET report_type = "Manufacturing" WHERE report_type IS NULL')
            migrations_applied += 1
        else:
            logger.info("pmi_indices table already has report_type column")
        
        # Migrate industry_status table
        cursor.execute("PRAGMA table_info(industry_status)")
        industry_columns = [col[1] for col in cursor.fetchall()]
        
        if 'report_type' not in industry_columns:
            logger.info("Adding report_type column to industry_status table")
            cursor.execute('ALTER TABLE industry_status ADD COLUMN report_type TEXT DEFAULT "Manufacturing" NOT NULL')
            cursor.execute('UPDATE industry_status SET report_type = "Manufacturing" WHERE report_type IS NULL')
            migrations_applied += 1
        else:
            logger.info("industry_status table already has report_type column")
        
        # Add rank column to industry_status if missing
        if 'rank' not in industry_columns:
            logger.info("Adding rank column to industry_status table")
            cursor.execute('ALTER TABLE industry_status ADD COLUMN rank INTEGER')
            cursor.execute('UPDATE industry_status SET rank = id WHERE rank IS NULL')
            migrations_applied += 1
        
        # Create/update indexes
        logger.info("Creating/updating indexes...")
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmi_indices_type ON pmi_indices(report_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_type ON industry_status(report_type)')
        
        conn.commit()
        logger.info(f"Migration completed successfully! Applied {migrations_applied} migrations.")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def main():
    """Main migration function."""
    logger.info("Starting Railway database migration...")
    
    # Find database
    db_path = find_database_path()
    
    if not db_path:
        logger.error("Could not determine database path")
        return False
    
    # Check if tables exist
    tables_exist = check_tables_exist(db_path)
    
    if not tables_exist:
        logger.info("Tables don't exist - initializing new database with correct schema")
        success = initialize_database_schema(db_path)
    else:
        logger.info("Tables exist - running migration to add missing columns")
        success = migrate_existing_database(db_path)
    
    if success:
        logger.info("✅ Migration completed successfully!")
        return True
    else:
        logger.error("❌ Migration failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)