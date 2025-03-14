import os
import re
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

def check_report_exists_in_db(month_year):
    """
    Check if a report for the given month and year exists in the database.
    
    Args:
        month_year: Month and year string (e.g., "January 2025")
        
    Returns:
        Boolean indicating if the report exists
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Try with exact match
        cursor.execute(
            """
            SELECT COUNT(*) FROM reports
            WHERE month_year = ?
            """,
            (month_year,)
        )
        
        count = cursor.fetchone()[0]
        
        if count > 0:
            return True
            
        # Try with case-insensitive match
        cursor.execute(
            """
            SELECT COUNT(*) FROM reports
            WHERE LOWER(month_year) = LOWER(?)
            """,
            (month_year,)
        )
        
        count = cursor.fetchone()[0]
        
        if count > 0:
            return True
            
        # Parse the date and try with date match
        from datetime import datetime
        try:
            date_obj = parse_date(month_year)
            if date_obj:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM reports
                    WHERE report_date = ?
                    """,
                    (date_obj.isoformat(),)
                )
                
                count = cursor.fetchone()[0]
                if count > 0:
                    return True
        except:
            pass
            
        # Try with partial match (case insensitive)
        cursor.execute(
            """
            SELECT COUNT(*) FROM reports
            WHERE LOWER(month_year) LIKE ?
            """,
            (f"%{month_year.lower()}%",)
        )
        
        count = cursor.fetchone()[0]
        
        return count > 0
    except Exception as e:
        logger.error(f"Error checking if report exists: {str(e)}")
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
        
        # Normalize case
        date_str = date_str.strip()
        
        # Try parsing with dateutil
        try:
            dt = parser.parse(date_str)
            return dt.date()
        except:
            # Continue to manual parsing
            pass
            
        # Try manual parsing for common formats
        try:
            # Try Month Year format (e.g., "January 2025")
            import re
            month_year_match = re.match(r'(\w+)\s+(\d{4})', date_str, re.IGNORECASE)
            if month_year_match:
                month_name = month_year_match.group(1).lower()
                year = int(month_year_match.group(2))
                
                month_map = {
                    'january': 1, 'february': 2, 'march': 3, 'april': 4,
                    'may': 5, 'june': 6, 'july': 7, 'august': 8,
                    'september': 9, 'october': 10, 'november': 11, 'december': 12
                }
                
                month_num = month_map.get(month_name.lower(), 1)
                return datetime.date(year, month_num, 1)
                
            # Try all caps format (e.g., "JANUARY 2025")
            month_year_match = re.match(r'([A-Z]+)\s+(\d{4})', date_str)
            if month_year_match:
                month_name = month_year_match.group(1).lower()
                year = int(month_year_match.group(2))
                
                month_map = {
                    'january': 1, 'february': 2, 'march': 3, 'april': 4,
                    'may': 5, 'june': 6, 'july': 7, 'august': 8,
                    'september': 9, 'october': 10, 'november': 11, 'december': 12
                }
                
                month_num = month_map.get(month_name, 1)
                return datetime.date(year, month_num, 1)
        except Exception as e:
            logger.warning(f"Manual date parsing failed: {str(e)}")
            
        # Last resort: return current date
        logger.error(f"Could not parse date '{date_str}', using current date")
        return datetime.date.today()
    except Exception as e:
        logger.error(f"Failed to parse date '{date_str}': {str(e)}")
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

import os
import re
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

def check_report_exists_in_db(month_year):
    """
    Check if a report for the given month and year exists in the database.
    
    Args:
        month_year: Month and year string (e.g., "January 2025")
        
    Returns:
        Boolean indicating if the report exists
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Try with exact match
        cursor.execute(
            """
            SELECT COUNT(*) FROM reports
            WHERE month_year = ?
            """,
            (month_year,)
        )
        
        count = cursor.fetchone()[0]
        
        if count > 0:
            return True
            
        # Try with case-insensitive match
        cursor.execute(
            """
            SELECT COUNT(*) FROM reports
            WHERE LOWER(month_year) = LOWER(?)
            """,
            (month_year,)
        )
        
        count = cursor.fetchone()[0]
        
        if count > 0:
            return True
            
        # Parse the date and try with date match
        from datetime import datetime
        try:
            date_obj = parse_date(month_year)
            if date_obj:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM reports
                    WHERE report_date = ?
                    """,
                    (date_obj.isoformat(),)
                )
                
                count = cursor.fetchone()[0]
                if count > 0:
                    return True
        except:
            pass
            
        # Try with partial match (case insensitive)
        cursor.execute(
            """
            SELECT COUNT(*) FROM reports
            WHERE LOWER(month_year) LIKE ?
            """,
            (f"%{month_year.lower()}%",)
        )
        
        count = cursor.fetchone()[0]
        
        return count > 0
    except Exception as e:
        logger.error(f"Error checking if report exists: {str(e)}")
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
        
        # Normalize case
        date_str = date_str.strip()
        
        # Try parsing with dateutil
        try:
            dt = parser.parse(date_str)
            return dt.date()
        except:
            # Continue to manual parsing
            pass
            
        # Try manual parsing for common formats
        try:
            # Try Month Year format (e.g., "January 2025")
            import re
            month_year_match = re.match(r'(\w+)\s+(\d{4})', date_str, re.IGNORECASE)
            if month_year_match:
                month_name = month_year_match.group(1).lower()
                year = int(month_year_match.group(2))
                
                month_map = {
                    'january': 1, 'february': 2, 'march': 3, 'april': 4,
                    'may': 5, 'june': 6, 'july': 7, 'august': 8,
                    'september': 9, 'october': 10, 'november': 11, 'december': 12
                }
                
                month_num = month_map.get(month_name.lower(), 1)
                return datetime.date(year, month_num, 1)
                
            # Try all caps format (e.g., "JANUARY 2025")
            month_year_match = re.match(r'([A-Z]+)\s+(\d{4})', date_str)
            if month_year_match:
                month_name = month_year_match.group(1).lower()
                year = int(month_year_match.group(2))
                
                month_map = {
                    'january': 1, 'february': 2, 'march': 3, 'april': 4,
                    'may': 5, 'june': 6, 'july': 7, 'august': 8,
                    'september': 9, 'october': 10, 'november': 11, 'december': 12
                }
                
                month_num = month_map.get(month_name, 1)
                return datetime.date(year, month_num, 1)
        except Exception as e:
            logger.warning(f"Manual date parsing failed: {str(e)}")
            
        # Last resort: return current date
        logger.error(f"Could not parse date '{date_str}', using current date")
        return datetime.date.today()
    except Exception as e:
        logger.error(f"Failed to parse date '{date_str}': {str(e)}")
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

def store_report_data_in_db(extracted_data, pdf_path):
    """
    Store the extracted report data in the SQLite database.
    
    Args:
        extracted_data: Dictionary containing the extracted report data
        pdf_path: Path to the PDF file
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not extracted_data:
        logger.error(f"No data to store for {pdf_path}")
        return False
        
    conn = None
    try:
        # Ensure database is initialized
        initialize_database()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Extract necessary data
        month_year = extracted_data.get('month_year', 'Unknown')
        
        # Parse the date from month_year
        report_date = parse_date(month_year)
        if not report_date:
            logger.error(f"Could not parse date from '{month_year}' for {pdf_path}")
            return False
            
        # Insert into reports table
        cursor.execute(
            """
            INSERT OR REPLACE INTO reports
            (report_date, file_path, processing_date, month_year)
            VALUES (?, ?, ?, ?)
            """,
            (
                report_date.isoformat(),
                pdf_path,
                datetime.datetime.now().isoformat(),
                month_year
            )
        )
        
        # Process pmi_indices data
        indices_data = {}
        
        # CRITICAL FIX: First check manufacturing_table.indices which contains Manufacturing PMI
        if 'manufacturing_table' in extracted_data and isinstance(extracted_data['manufacturing_table'], dict):
            mfg_table = extracted_data['manufacturing_table']
            if 'indices' in mfg_table and isinstance(mfg_table['indices'], dict):
                logger.info(f"Processing {len(mfg_table['indices'])} indices from manufacturing table")
                logger.info(f"Raw manufacturing_table indices: {mfg_table['indices']}")
                for index_name, data in mfg_table['indices'].items():
                    try:
                        # Get value from either current or value field
                        value = data.get("current", data.get("value"))
                        direction = data.get("direction")
                        
                        if value and direction:
                            indices_data[index_name] = {
                                'value': float(value),
                                'direction': direction
                            }
                            logger.info(f"Added index {index_name}: {value} ({direction}) from manufacturing table")
                    except Exception as e:
                        logger.error(f"Error processing index {index_name} from manufacturing table: {str(e)}")
        
        # Then try to extract from index_summaries as a fallback
        if 'index_summaries' in extracted_data:
            index_summaries = extracted_data.get('index_summaries', {})
            for index_name, summary in index_summaries.items():
                # Only process if not already extracted from manufacturing table
                if index_name not in indices_data:
                    try:
                        # Pattern for values like "PMI® registered 50.9 percent in January"
                        import re
                        value_pattern = r'(?:registered|was|at)\s+(\d+\.\d+)'
                        value_match = re.search(value_pattern, summary, re.IGNORECASE)
                        
                        direction_pattern = r'(growing|growth|expanding|expansion|contracting|contraction|declining|increasing|decreasing|faster|slower)'
                        direction_match = re.search(direction_pattern, summary, re.IGNORECASE)
                        
                        if value_match:
                            value = float(value_match.group(1))
                            direction = direction_match.group(1).capitalize() if direction_match else "Unknown"
                            
                            # Standardize direction terms
                            if direction.lower() in ['growing', 'growth', 'expanding', 'expansion', 'increasing']:
                                direction = 'Growing'
                            elif direction.lower() in ['contracting', 'contraction', 'declining', 'decreasing']:
                                direction = 'Contracting'
                            elif direction.lower() == 'slower':
                                direction = 'Slowing'
                            elif direction.lower() == 'faster':
                                direction = 'Faster'
                            
                            indices_data[index_name] = {
                                'value': value,
                                'direction': direction
                            }
                    except Exception as e:
                        logger.warning(f"Error extracting index data for {index_name}: {str(e)}")
        
        # Also check for direct pmi_data
        if 'pmi_data' in extracted_data and extracted_data['pmi_data']:
            for index_name, data in extracted_data['pmi_data'].items():
                # Only add if not already in indices_data
                if index_name not in indices_data:
                    try:
                        indices_data[index_name] = {
                            'value': float(data.get('current', data.get('value'))),
                            'direction': data.get('direction')
                        }
                        logger.info(f"Added index {index_name} from pmi_data")
                    except Exception as e:
                        logger.error(f"Error processing index {index_name} from pmi_data: {str(e)}")
        
        logger.info(f"Final indices_data before insertion: {indices_data}")

        # Insert pmi_indices data
        indices_processed = 0
        for index_name, data in indices_data.items():
            try:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO pmi_indices
                    (report_date, index_name, index_value, direction)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        report_date.isoformat(),
                        index_name,
                        data.get('value', 0.0),
                        data.get('direction', 'Unknown')
                    )
                )
                indices_processed += 1
                logger.info(f"Successfully inserted {index_name} with value {data.get('value')} ({data.get('direction')})")
            except Exception as e:
                logger.error(f"Error inserting pmi_indices data for {index_name}: {str(e)}")
        
        logger.info(f"Successfully processed {indices_processed} out of {len(indices_data)} indices")
        
        # Process industry_status data
        industry_data = extracted_data.get('industry_data', {})
        for index_name, categories in industry_data.items():
            for category, industries in categories.items():
                # Determine status based on category
                if index_name == 'Supplier Deliveries':
                    status = 'Slowing' if category == 'Slower' else 'Faster'
                elif index_name == 'Inventories':
                    status = 'Higher' if category == 'Higher' else 'Lower'
                elif index_name == "Customers' Inventories":
                    status = category  # 'Too High' or 'Too Low'
                elif index_name == 'Prices':
                    status = 'Increasing' if category == 'Increasing' else 'Decreasing'
                else:
                    status = 'Growing' if category == 'Growing' else 'Contracting'
                
                for industry in industries:
                    # Clean and validate the industry name
                    cleaned_industry = clean_industry_name(industry)
                    if not cleaned_industry:
                        continue
                    
                    try:
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO industry_status
                            (report_date, index_name, industry_name, status, category)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                report_date.isoformat(),
                                index_name,
                                cleaned_industry,
                                status,
                                category
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error inserting industry_status data for {cleaned_industry}: {str(e)}")
                        
        conn.commit()
        logger.info(f"Successfully stored data for report {month_year} in database")
        return True
        
    except Exception as e:
        logger.error(f"Error storing report data in database: {str(e)}")
        logger.error(traceback.format_exc())
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def clean_industry_name(industry):
    """Clean industry name to remove common artifacts."""
    if not industry or not isinstance(industry, str):
        return None

    # Remove leading/trailing whitespace
    industry = industry.strip()

    # Skip parsing artifacts
    artifacts = [
        "following order",
        "are:",
        "in order",
        "listed in order",
        "in the following order",
        "reporting",
        "november" # also remove this artifact
    ]

    industry_lower = industry.lower()
    for artifact in artifacts:
        if artifact in industry_lower:
            return None

    # Remove common prefixes and suffixes
    industry = re.sub(r"^(the\s+|and\s+|november\s+)", "", industry, flags=re.IGNORECASE)
    industry = re.sub(r"(\s+products)$", "", industry, flags=re.IGNORECASE)
    
    # Normalize whitespace
    industry = re.sub(r'\s+', ' ', industry).strip()  # remove multi-space

    # Remove any parsing leftovers at the beginning, like stray letters/symbols
    industry = re.sub(r"^[s]\s+", "", industry, flags=re.IGNORECASE) # s
    industry = re.sub(r"^[-—]\s+", "", industry, flags=re.IGNORECASE) # dashes
    industry = re.sub(r"^[a-z]\s+", "", industry, flags=re.IGNORECASE) # stray letters
    
    # Remove number + character
    industry = re.sub(r"^\d+[a-zA-Z]", "", industry, flags=re.IGNORECASE)
     # Fix "andPrimary Metals" issue
    industry = re.sub(r"andprimarymetals", "and Primary Metals", industry, flags=re.IGNORECASE)

    # Skip if starts with punctuation
    if re.match(r'^[,;:.]+', industry):
        return None

    # Skip if too short
    if len(industry) < 3:
        return None
    
    return industry
