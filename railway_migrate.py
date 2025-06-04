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

def check_database_structure(db_path):
    """Check the current database structure."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Found tables: {tables}")
        
        # Check each table's columns
        for table in ['reports', 'pmi_indices', 'industry_status']:
            if table in tables:
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [col[1] for col in cursor.fetchall()]
                logger.info(f"Table {table} columns: {columns}")
            else:
                logger.warning(f"Table {table} not found")
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error checking database structure: {e}")
        return False

def migrate_database(db_path):
    """Migrate database to add report_type columns."""
    conn = None
    try:
        logger.info(f"Starting migration for database: {db_path}")
        
        # Ensure database directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys = ON")
        
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
        
        # Create indexes
        logger.info("Creating/updating indexes...")
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmi_indices_type ON pmi_indices(report_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_type ON industry_status(report_type)')
        
        # Add rank column to industry_status if missing
        if 'rank' not in industry_columns:
            logger.info("Adding rank column to industry_status table")
            cursor.execute('ALTER TABLE industry_status ADD COLUMN rank INTEGER')
            cursor.execute('UPDATE industry_status SET rank = id WHERE rank IS NULL')
            migrations_applied += 1
        
        conn.commit()
        logger.info(f"Migration completed successfully! Applied {migrations_applied} migrations.")
        
        # Verify the migration
        check_database_structure(db_path)
        
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
    
    # Check current structure
    logger.info("Checking current database structure...")
    if os.path.exists(db_path):
        check_database_structure(db_path)
    else:
        logger.info("Database file does not exist yet - will be created")
    
    # Run migration
    success = migrate_database(db_path)
    
    if success:
        logger.info("✅ Migration completed successfully!")
        return True
    else:
        logger.error("❌ Migration failed!")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)