import sqlite3
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database file path
DB_PATH = os.environ.get('ISM_DB_PATH', '/data/ism_data.db')

def add_rank_column():
    """Add rank column to industry_status table."""
    conn = None
    try:
        # Connect to the database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if rank column already exists
        cursor.execute("PRAGMA table_info(industry_status)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'rank' not in columns:
            logger.info("Adding rank column to industry_status table")
            cursor.execute("ALTER TABLE industry_status ADD COLUMN rank INTEGER")
            
            # Update existing rows with rank based on id
            cursor.execute("""
                UPDATE industry_status
                SET rank = id
                WHERE rank IS NULL
            """)
            
            conn.commit()
            logger.info("Successfully added rank column")
        else:
            logger.info("Rank column already exists")
        
        return True
    except Exception as e:
        logger.error(f"Error adding rank column: {str(e)}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    add_rank_column()