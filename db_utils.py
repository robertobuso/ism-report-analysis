import os
import sqlite3
import logging
import datetime
from dateutil import parser
from typing import Optional, Dict, List, Any, Tuple
import traceback

# Configure logging
logger = logging.getLogger(__name__)

# Database file path
DB_PATH = os.environ.get('ISM_DB_PATH', 'ism_data.db')

def get_db_connection():
    """Create a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Configure connection to return rows as dictionaries
        conn.row_factory = sqlite3.Row
        
        return conn
    except Exception as e:
        logger.error(f"Error connecting to database: {str(e)}")
        raise

def initialize_database():
    """Initialize the SQLite database with the required schema."""
    try:
        # Check if directory exists
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create reports table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            report_date DATE UNIQUE NOT NULL,
            file_path TEXT,
            processing_date DATETIME NOT NULL,
            month_year TEXT NOT NULL
        )
        ''')
        
        # Create pmi_indices table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS pmi_indices (
            id INTEGER PRIMARY KEY,
            report_date DATE NOT NULL,
            index_name TEXT NOT NULL,
            index_value DECIMAL(5,1) NOT NULL,
            direction TEXT NOT NULL,
            UNIQUE(report_date, index_name),
            FOREIGN KEY(report_date) REFERENCES reports(report_date)
        )
        ''')
        
        # Create industry_status table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS industry_status (
            id INTEGER PRIMARY KEY,
            report_date DATE NOT NULL,
            index_name TEXT NOT NULL,
            industry_name TEXT NOT NULL,
            status TEXT NOT NULL,
            category TEXT NOT NULL,
            UNIQUE(report_date, index_name, industry_name),
            FOREIGN KEY(report_date) REFERENCES reports(report_date)
        )
        ''')
        
        # Create indices for common query patterns
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmi_indices_date ON pmi_indices(report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmi_indices_name ON pmi_indices(index_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_date ON industry_status(report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_index ON industry_status(index_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_industry ON industry_status(industry_name)')
        
        conn.commit()
        logger.info("Database schema initialized successfully")
        
        return True
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        logger.error(traceback.format_exc())
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def parse_date(date_str: str) -> Optional[datetime.date]:
    """
    Parse a date string into a datetime.date object.
    Handles various formats of date strings.
    
    Args:
        date_str: Date string in various possible formats
        
    Returns:
        datetime.date object or None if parsing fails
    """
    try:
        if not date_str or date_str == "Unknown":
            return None
            
        # Try parsing with dateutil
        dt = parser.parse(date_str)
        return dt.date()
    except Exception as e:
        logger.warning(f"Failed to parse date '{date_str}': {str(e)}")
        
        # Try manual parsing for common formats
        try:
            # Try Month Year format (e.g., "January 2025")
            import re
            month_year_match = re.match(r'(\w+)\s+(\d{4})', date_str)
            if month_year_match:
                month_name = month_year_match.group(1)
                year = int(month_year_match.group(2))
                
                month_map = {
                    'january': 1, 'february': 2, 'march': 3, 'april': 4,
                    'may': 5, 'june': 6, 'july': 7, 'august': 8,
                    'september': 9, 'october': 10, 'november': 11, 'december': 12
                }
                
                month_num = month_map.get(month_name.lower(), 1)
                return datetime.date(year, month_num, 1)
        except Exception:
            pass
            
        # Last resort: return current date
        logger.error(f"Could not parse date '{date_str}', using current date")
        return datetime.date.today()
    
def get_all_report_dates():
    """Get all report dates in descending order."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT report_date, month_year 
            FROM reports 
            ORDER BY report_date DESC
        """)
        
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting report dates: {str(e)}")
        return []
    finally:
        if conn:
            conn.close()

def get_pmi_data_by_month(num_months=12):
    """
    Get PMI data for all indices by month, for the last N months.
    This is used for the monthly heatmap summary.
    
    Args:
        num_months: Number of most recent months to include
        
    Returns:
        List of dictionaries with report_date and PMI values by index
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get the most recent report dates
        cursor.execute("""
            SELECT report_date 
            FROM reports 
            ORDER BY report_date DESC 
            LIMIT ?
        """, (num_months,))
        
        report_dates = [row['report_date'] for row in cursor.fetchall()]
        
        if not report_dates:
            return []
            
        # For each report date, get all PMI indices
        result = []
        for date in report_dates:
            # Get the month_year for this date
            cursor.execute("""
                SELECT month_year FROM reports WHERE report_date = ?
            """, (date,))
            month_year = cursor.fetchone()['month_year']
            
            # Get all indices for this date
            cursor.execute("""
                SELECT index_name, index_value, direction
                FROM pmi_indices
                WHERE report_date = ?
            """, (date,))
            
            indices = {row['index_name']: {
                'value': row['index_value'], 
                'direction': row['direction']
            } for row in cursor.fetchall()}
            
            row_data = {
                'report_date': date,
                'month_year': month_year,
                'indices': indices
            }
            
            result.append(row_data)
            
        return result
    except Exception as e:
        logger.error(f"Error getting PMI data by month: {str(e)}")
        return []
    finally:
        if conn:
            conn.close()

def get_index_time_series(index_name, num_months=24):
    """
    Get time series data for a specific index.
    This is used for the Index Time-Series Analysis.
    
    Args:
        index_name: Name of the index (e.g., "Manufacturing PMI")
        num_months: Number of most recent months to include
        
    Returns:
        List of dictionaries with date, value, and month-over-month change
    """
    conn = None
    try:
        conn = get_db_connection()
        
        # Use a raw SQL query with window functions for efficiency
        query = """
        WITH IndexData AS (
            SELECT 
                r.report_date,
                r.month_year,
                p.index_value,
                p.direction,
                LAG(p.index_value) OVER (ORDER BY r.report_date) AS prev_value
            FROM pmi_indices p
            JOIN reports r ON p.report_date = r.report_date
            WHERE p.index_name = ?
            ORDER BY r.report_date DESC
            LIMIT ?
        )
        SELECT 
            report_date,
            month_year,
            index_value,
            direction,
            ROUND(index_value - prev_value, 1) AS change
        FROM IndexData
        ORDER BY report_date DESC
        """
        
        cursor = conn.cursor()
        cursor.execute(query, (index_name, num_months))
        
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting time series for {index_name}: {str(e)}")
        return []
    finally:
        if conn:
            conn.close()

def get_industry_status_over_time(index_name, num_months=12):
    """
    Get industry status over time for a specific index.
    This is used for the Industry Growth/Contraction visualization.
    
    Args:
        index_name: Name of the index (e.g., "New Orders")
        num_months: Number of most recent months to include
        
    Returns:
        Dictionary with industries as keys and lists of status by month as values
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get the most recent report dates
        cursor.execute("""
            SELECT report_date, month_year 
            FROM reports 
            ORDER BY report_date DESC 
            LIMIT ?
        """, (num_months,))
        
        date_records = [dict(row) for row in cursor.fetchall()]
        if not date_records:
            return {'dates': [], 'industries': {}}
            
        # Get all unique industries for this index
        cursor.execute("""
            SELECT DISTINCT industry_name 
            FROM industry_status 
            WHERE index_name = ?
            ORDER BY industry_name
        """, (index_name,))
        
        industries = [row['industry_name'] for row in cursor.fetchall()]
        
        # For each industry, get status for each date
        industry_data = {}
        for industry in industries:
            status_by_date = {}
            
            for date_record in date_records:
                report_date = date_record['report_date']
                month_year = date_record['month_year']
                
                cursor.execute("""
                    SELECT status, category
                    FROM industry_status
                    WHERE report_date = ? AND index_name = ? AND industry_name = ?
                """, (report_date, index_name, industry))
                
                row = cursor.fetchone()
                if row:
                    status_by_date[month_year] = {
                        'status': row['status'],
                        'category': row['category']
                    }
                else:
                    status_by_date[month_year] = {
                        'status': 'Neutral',
                        'category': 'Not Reported'
                    }
            
            industry_data[industry] = status_by_date
        
        return {
            'dates': [record['month_year'] for record in date_records],
            'industries': industry_data
        }
    except Exception as e:
        logger.error(f"Error getting industry status for {index_name}: {str(e)}")
        return {'dates': [], 'industries': {}}
    finally:
        if conn:
            conn.close()

def get_all_indices():
    """Get a list of all indices in the database."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT index_name 
            FROM pmi_indices 
            ORDER BY index_name
        """)
        
        return [row['index_name'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting all indices: {str(e)}")
        return []
    finally:
        if conn:
            conn.close()