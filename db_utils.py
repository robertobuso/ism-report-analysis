import os
import re
import sqlite3
import logging
from datetime import date, datetime
from dateutil import parser
from typing import Optional, Dict, List, Any, Tuple
import traceback

# Configure logging
logger = logging.getLogger(__name__)

DATABASE_NAME = 'ism_data.db'

# Constants for indices
MANUFACTURING_PMI_INDEX = "Manufacturing PMI"
SERVICES_PMI_INDEX = "Services PMI"

# --- CORRECTED Path Determination ---
# Check if running in Railway by looking for the volume mount path env var
railway_volume_path = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH')

if railway_volume_path:
    # Running in Railway, use the provided volume path
    # Note: RAILWAY_VOLUME_MOUNT_PATH points to the *directory* (e.g., /data)
    DB_DIR = railway_volume_path
    DATABASE_PATH = os.path.join(DB_DIR, DATABASE_NAME)
    logger.info(f"Detected Railway environment. Using DB path: {DATABASE_PATH}")
else:
    # Running locally (or Railway env var not found), use current working directory
    # This assumes you run 'flask run' from your project's root directory
    DB_DIR = os.getcwd()
    DATABASE_PATH = os.path.join(DB_DIR, DATABASE_NAME)
    logger.info(f"Running in local environment. Using DB path: {DATABASE_PATH}")
# --- End Path Determination ---

def initialize_database():
    """Initialize the SQLite database with the required schema."""
    conn = None
    try:
        # Check if directory exists
        db_dir = os.path.dirname(DATABASE_PATH)
        if not os.path.exists(db_dir):
             logger.info(f"Attempting to create database directory: {db_dir}")
             os.makedirs(db_dir, exist_ok=True)

        logger.info(f"Initializing database connection at: {DATABASE_PATH}")
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        logger.debug("Executing CREATE TABLE IF NOT EXISTS statements...")
        
        # Create reports table with report_type column
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            report_date DATE UNIQUE NOT NULL,
            file_path TEXT,
            processing_date DATETIME NOT NULL,
            month_year TEXT NOT NULL,
            report_type TEXT DEFAULT 'Manufacturing' NOT NULL
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
            rank INTEGER,
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
        
        # Add index for report_type column for efficient filtering
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_reports_type ON reports(report_type)')
        
        conn.commit()
        logger.info(f"Database schema initialized successfully at {DATABASE_PATH}")

    except (sqlite3.Error, OSError, Exception) as e:
        logger.error(f"Error during database initialization for {DATABASE_PATH}: {e}", exc_info=True)
    finally:
        if conn:
            try:
                conn.close()
                logger.debug("DB connection closed after initialization.")
            except sqlite3.Error as e:
                 logger.error(f"Error closing connection post-initialization: {e}")

def get_db_connection():
    """Create a connection to the SQLite database."""
    conn = None
    try:
        # Ensure directory exists (might be redundant if initialize_database called first, but safe)
        db_dir = os.path.dirname(DATABASE_PATH)
        if not os.path.exists(db_dir):
             os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        logger.debug(f"Database connection opened successfully to {DATABASE_PATH}")
        return conn
    except (sqlite3.Error, OSError, Exception) as e:
        logger.error(f"Error connecting to database {DATABASE_PATH}: {e}", exc_info=True)
        # Re-raise the exception so the calling code knows connection failed
        raise

def check_report_exists_in_db(month_year, report_type='Manufacturing'):
    """
    Check if a report for the given month and year exists in the database.

    Args:
        month_year: Month and year string (e.g., "January 2025")
        report_type: Type of report to check for (Manufacturing or Services)

    Returns:
        Boolean indicating if the report exists
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Construct base query
        query = """
            SELECT COUNT(*) FROM reports
            WHERE month_year = ? AND report_type = ?
        """

        # Try with exact match
        cursor.execute(query, (month_year, report_type))
        count = cursor.fetchone()[0]
        if count > 0:
            return True

        # Try with case-insensitive match
        query_lower = """
            SELECT COUNT(*) FROM reports
            WHERE LOWER(month_year) = LOWER(?) AND report_type = ?
        """
        cursor.execute(query_lower, (month_year, report_type))
        count = cursor.fetchone()[0]
        if count > 0:
            return True

        # Parse the date and try with date match
        from datetime import datetime
        try:
            date_obj = parse_date(month_year)
            if date_obj:
                query_date = """
                   SELECT COUNT(*) FROM reports
                    WHERE report_date = ? AND report_type = ?
                """
                cursor.execute(query_date, (date_obj.isoformat(), report_type))
                count = cursor.fetchone()[0]
                if count > 0:
                    return True
        except Exception as de:
            logger.warning(f"Date parsing error for month_year '{month_year}': {de}") # Log the error, use a more descriptive variable name 'de'

        # Try with partial match (case insensitive)
        query_like = """
             SELECT COUNT(*) FROM reports
                WHERE LOWER(month_year) LIKE ? AND report_type = ?
        """
        cursor.execute(query_like, (f"%{month_year.lower()}%", report_type))
        count = cursor.fetchone()[0]

        return count > 0

    except Exception as e:
        logger.error(f"Error checking if report exists: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def parse_date(date_str: str) -> Optional[date]:
    """
    Parse a date string into a date object.
    Always returns the 1st day of the month for consistency.
    
    Args:
        date_str: Date string in various possible formats
        
    Returns:
        date object (always with day=1) or None if parsing fails
    """
    try:
        if not date_str or date_str == "Unknown":
            # Return current date instead of None when unknown
            today = date.today()
            return date(today.year, today.month, 1)
        
        # Normalize case
        date_str = date_str.strip()
        
        # Try parsing with dateutil
        try:
            dt = parser.parse(date_str)
            # Always set day to 1 for consistency
            return date(dt.year, dt.month, 1)
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
                # Return with day=1
                return date(year, month_num, 1)
                
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
                # Return with day=1
                return date(year, month_num, 1)
                
            # Try date format like Sep-24 or Oct-13
            abbr_match = re.match(r'(\w{3})-(\d{2})', date_str)
            if abbr_match:
                month_abbr = abbr_match.group(1).capitalize()
                year_short = int(abbr_match.group(2))
                
                month_map = {
                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                }
                
                month_num = month_map.get(month_abbr, 1)
                
                # Convert 2-digit year to 4-digit
                year = 2000 + year_short if year_short < 50 else 1900 + year_short
                
                # Return with day=1
                return date(year, month_num, 1)
        except Exception as e:
            logger.warning(f"Manual date parsing failed: {str(e)}")
            
        # Last resort: return current date with day=1
        logger.error(f"Could not parse date '{date_str}', using current date")
        today = date.today()
        return date(today.year, today.month, 1)
    except Exception as e:
        logger.error(f"Failed to parse date '{date_str}': {str(e)}")
        today = date.today()
        return date(today.year, today.month, 1)
    
def get_all_report_dates(report_type=None):
    """
    Get all report dates in descending order.
    
    Args:
        report_type: Optional filter by report type ('Manufacturing' or 'Services')
        
    Returns:
        List of dictionaries with report_date and month_year
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = """
            SELECT report_date, month_year, report_type
            FROM reports 
            {}
            ORDER BY report_date DESC
        """
        
        if report_type:
            query = query.format("WHERE report_type = ?")
            cursor.execute(query, (report_type,))
        else:
            query = query.format("")
            cursor.execute(query)
        
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting report dates: {str(e)}")
        return []
    finally:
        if conn:
            conn.close()

def get_pmi_data_by_month(num_months=12, report_type=None):
    """
    Get PMI data for all indices by month, for the last N months.
    
    Args:
        num_months: Number of most recent months to include
        report_type: Type of report ('Manufacturing' or 'Services')
        
    Returns:
        List of dictionaries with report_date and PMI values by index
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build the query based on whether report_type is provided
        query = """
            SELECT report_date, month_year
            FROM reports 
            {}
            ORDER BY report_date DESC 
            LIMIT ?
        """
        
        params = []
        if report_type:
            query = query.format("WHERE report_type = ?")
            params = [report_type, num_months]
        else:
            query = query.format("")
            params = [num_months]
            
        cursor.execute(query, params)
        
        report_dates = [{'report_date': row['report_date'], 'month_year': row['month_year']} for row in cursor.fetchall()]
        
        if not report_dates:
            logger.warning(f"No report dates found for {report_type if report_type else 'any type'}")
            return []
        
        # Get PMI data for each report date
        result = []
        for date_info in report_dates:
            report_date = date_info['report_date']
            month_year = date_info['month_year']
            
            # Get all indices for this report date
            cursor.execute("""
                SELECT index_name, index_value, direction 
                FROM pmi_indices 
                WHERE report_date = ?
            """, (report_date,))
            
            indices = {}
            for row in cursor.fetchall():
                indices[row['index_name']] = {
                    'value': row['index_value'],
                    'direction': row['direction']
                }
            
            # Skip if no indices found
            if not indices:
                logger.warning(f"No PMI data found for report date {report_date}")
                continue
                
            # Add to result
            result.append({
                'report_date': report_date,
                'month_year': month_year,
                'indices': indices,
                'report_type': report_type  # Include report_type in the response
            })
        
        logger.info(f"Retrieved PMI data for {len(result)} report dates")
        return result
    except Exception as e:
        logger.error(f"Error getting PMI data by month: {str(e)}")
        logger.error(traceback.format_exc())
        return []
    finally:
        if conn:
            conn.close()

def get_index_time_series(index_name, num_months=24, report_type=None):
    """
    Get time series data for a specific index.
    
    Args:
        index_name: Name of the index (e.g., "Manufacturing PMI")
        num_months: Number of most recent months to include
        report_type: Type of report ('Manufacturing' or 'Services')
        
    Returns:
        List of dictionaries with date, value, and month-over-month change
    """
    conn = None
    try:
        conn = get_db_connection()
        
        # Modify query to include report_type filtering
        query = """
        WITH IndexData AS (
            SELECT 
                r.report_date,
                r.month_year,
                r.report_type,
                p.index_value,
                p.direction,
                LAG(p.index_value) OVER (ORDER BY r.report_date) AS prev_value
            FROM pmi_indices p
            JOIN reports r ON p.report_date = r.report_date
            WHERE p.index_name = ?
            {}
            ORDER BY r.report_date DESC
            LIMIT ?
        )
        SELECT 
            report_date,
            month_year,
            report_type,
            index_value,
            direction,
            ROUND(index_value - prev_value, 1) AS change
        FROM IndexData
        ORDER BY report_date DESC
        """
        
        params = []
        if report_type:
            query = query.format("AND r.report_type = ?")
            params = [index_name, report_type, num_months]
        else:
            query = query.format("")
            params = [index_name, num_months]
        
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting time series for {index_name}: {str(e)}")
        return []
    finally:
        if conn:
            conn.close()

def get_industry_status_over_time(index_name, num_months=12, report_type=None):
    """
    Get industry status over time for a specific index.
    
    Args:
        index_name: Name of the index (e.g., "New Orders")
        num_months: Number of most recent months to include
        report_type: Type of report ('Manufacturing' or 'Services')
        
    Returns:
        Dictionary with industries as keys and lists of status by month as values
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get the most recent report dates with optional report_type filter
        query = """
            SELECT report_date, month_year 
            FROM reports 
            {}
            ORDER BY report_date DESC 
            LIMIT ?
        """
        
        params = []
        if report_type:
            query = query.format("WHERE report_type = ?")
            params = [report_type, num_months]
        else:
            query = query.format("")
            params = [num_months]
            
        cursor.execute(query, params)
        
        date_records = [dict(row) for row in cursor.fetchall()]
        if not date_records:
            return {'dates': [], 'industries': {}, 'ranks': {}, 'report_type': report_type}
            
        # Get all unique industries for this index
        cursor.execute("""
            SELECT DISTINCT i.industry_name 
            FROM industry_status i
            JOIN reports r ON i.report_date = r.report_date
            WHERE i.index_name = ?
            {}
            ORDER BY i.rank
        """.format("AND r.report_type = ?" if report_type else ""), 
        [index_name] + ([report_type] if report_type else []))

        industries = [row['industry_name'] for row in cursor.fetchall()]
        
        # Also get the most recent ranks for these industries
        most_recent_date = date_records[0]['report_date']
        cursor.execute("""
            SELECT industry_name, rank
            FROM industry_status
            WHERE report_date = ? AND index_name = ?
        """, (most_recent_date, index_name))
        
        ranks = {row['industry_name']: row['rank'] for row in cursor.fetchall()}
        
        # For each industry, get status for each date
        industry_data = {}
        for industry in industries:
            status_by_date = {}
            
            for date_record in date_records:
                report_date = date_record['report_date']
                month_year = date_record['month_year']
                
                cursor.execute("""
                    SELECT status, category, rank
                    FROM industry_status
                    WHERE report_date = ? AND index_name = ? AND industry_name = ?
                """, (report_date, index_name, industry))
                
                row = cursor.fetchone()
                if row:
                    status_by_date[month_year] = {
                        'status': row['status'],
                        'category': row['category'],
                        'rank': row['rank']
                    }
                else:
                    status_by_date[month_year] = {
                        'status': 'Neutral',
                        'category': 'Not Reported',
                        'rank': 0 
                    }
            
            industry_data[industry] = status_by_date
        
        return {
            'dates': [record['month_year'] for record in date_records],
            'industries': industry_data,
            'ranks': ranks,
            'report_type': report_type  # Include report_type in the response
        }
    except Exception as e:
        logger.error(f"Error getting industry status for {index_name}: {str(e)}")
        return {'dates': [], 'industries': {}, 'ranks': {}, 'report_type': report_type}
    finally:
        if conn:
            conn.close()

def get_all_indices(report_type=None):
    """
    Get a list of all indices in the database.
    
    Args:
        report_type: Type of report ('Manufacturing' or 'Services')
        
    Returns:
        List of index names
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if report_type:
            # Get indices specific to the report type
            query = """
                SELECT DISTINCT i.index_name 
                FROM pmi_indices i
                JOIN reports r ON i.report_date = r.report_date
                WHERE r.report_type = ?
                ORDER BY i.index_name
            """
            cursor.execute(query, (report_type,))
        else:
            # Get all indices
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

def extract_pmi_data(data: dict) -> dict or None:
        value = data.get("current", data.get("value"))
        direction = data.get("direction")

        if value and direction:
            return {
                'value': float(value),
                'direction': direction
            }
        return None

def store_report_data_in_db(extracted_data, pdf_path, report_type="Manufacturing"):
    """
    Store the extracted report data in the SQLite database.
    
    Args:
        extracted_data: Dictionary containing the extracted report data
        pdf_path: Path to the PDF file
        report_type: Type of report (Manufacturing or Services), defaults to Manufacturing
        
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

        # Ensure report_type is valid
        if not report_type or not isinstance(report_type, str):
            logger.warning(f"Invalid report_type '{report_type}', using 'Manufacturing'")
            report_type = "Manufacturing"  # Default
        
        # Insert into reports table
        cursor.execute(
            """
            INSERT OR REPLACE INTO reports
            (report_date, file_path, processing_date, month_year, report_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                report_date.isoformat(),
                pdf_path,
                datetime.now().isoformat(),
                month_year,
                report_type
            )
        )

        # Process indices data - MODIFIED to handle both report types
        indices_data = {}
        
        # First, try to get indices directly from the extracted data
        if 'indices' in extracted_data and extracted_data['indices']:
            indices_data = extracted_data['indices']
            logger.info(f"Using indices directly - found {len(indices_data)} indices")
        
        # If not available, check for report-specific table data
        elif not indices_data:
            # Define possible table keys based on report type
            possible_table_keys = []
            
            # Add report-specific keys
            if report_type.lower() == 'manufacturing':
                possible_table_keys.extend(['manufacturing_table', 'mfg_table', 'pmi_data'])
            elif report_type.lower() == 'services':
                possible_table_keys.extend(['services_table', 'service_table', 'services_data'])
            
            # Add generic keys that might be used
            possible_table_keys.extend(['at_a_glance', 'table_data', 'index_data'])
            
            # Check each possible key
            for key in possible_table_keys:
                if key in extracted_data and isinstance(extracted_data[key], dict):
                    # Check if this dict contains index data
                    has_indices = False
                    key_count = 0
                    
                    # List of common indices to check for
                    index_indicators = ['PMI', 'New Orders', 'Production', 'Employment', 
                                       'Business Activity', 'Supplier Deliveries']
                    
                    for index in index_indicators:
                        if index in extracted_data[key]:
                            has_indices = True
                            key_count += 1
                    
                    # If we found multiple indices, use this data
                    if has_indices and key_count >= 2:
                        indices_data = extracted_data[key]
                        logger.info(f"Using {key} - found {len(indices_data)} indices")
                        break
        
        # If we still have no indices, try pmi_data
        if not indices_data and 'pmi_data' in extracted_data and extracted_data['pmi_data']:
            indices_data = extracted_data['pmi_data']
            logger.info(f"Using pmi_data - found {len(indices_data)} indices")
            
        # Last resort: try to extract from index_summaries
        if not indices_data and 'index_summaries' in extracted_data and extracted_data['index_summaries']:
            logger.info("Trying to extract indices from index_summaries")
            index_summaries = extracted_data['index_summaries']
            
            for index_name, summary in index_summaries.items():
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
                        
                        if not indices_data:
                            indices_data = {}
                        indices_data[index_name] = {
                            'value': value,
                            'direction': direction
                        }
                except Exception as e:
                    logger.warning(f"Error extracting index data for {index_name}: {str(e)}")
        
        # Insert indices data with improved extraction logic
        for index_name, data in indices_data.items():
            try:
                if index_name.upper() in ["OVERALL ECONOMY", "MANUFACTURING SECTOR", "SERVICES SECTOR"]:
                    logger.info(f"DB_STORE: Skipping non-PMI summary item '{index_name}' for pmi_indices table.")
                    continue  # This will skip the rest of the current iteration of THIS loop and go to the next index_name

                # IMPROVED INDEX VALUE EXTRACTION LOGIC
                index_value = None
                
                # Identify the primary value field and avoid using percent_point_change
                if isinstance(data, dict):
                    # Priority order for value fields
                    priority_fields = ['current', 'value', 'series_index', 'index']
                    
                    # Fields to avoid
                    avoid_fields = ['percent_point_change', 'change', 'delta']
                    
                    # First try priority fields
                    for field in priority_fields:
                        if field in data and data[field] is not None:
                            index_value = data[field]
                            break
                    
                    # If still not found, try any numeric field except those to avoid
                    if index_value is None:
                        for field, val in data.items():
                            if field not in avoid_fields and field != 'direction' and val is not None:
                                try:
                                    # Test if it can be converted to float
                                    float_test = float(val)
                                    index_value = val
                                    break
                                except (ValueError, TypeError):
                                    continue
                else:
                    # If data is not a dict, try using it directly
                    index_value = data
                
                # Ensure value is a float
                if index_value is not None:
                    try:
                        if isinstance(index_value, str):
                            # If string has percentage sign, remove it
                            index_value = index_value.replace('%', '')
                            index_value = float(index_value)
                        else:
                            index_value = float(index_value)
                    except (ValueError, TypeError):
                        logger.warning(f"Invalid index value '{index_value}' for {index_name}, using 0.0")
                        index_value = 0.0
                else:
                    logger.warning(f"No valid index value for {index_name}, using 0.0")
                    index_value = 0.0
                
                # IMPROVED DIRECTION EXTRACTION LOGIC
                direction = None
                
                # Identify the primary direction and avoid using rate_of_change
                if isinstance(data, dict):
                    # Priority order for direction fields
                    priority_fields = ['direction', 'status', 'trend']
                    
                    # Fields to avoid
                    avoid_fields = ['rate_of_change', 'pace', 'speed']
                    
                    # First try priority fields
                    for field in priority_fields:
                        if field in data and data[field] is not None:
                            direction = data[field]
                            break
                    
                    # If not found, use default
                    if direction is None:
                        direction = 'Unknown'
                else:
                    direction = 'Unknown'
                    
                # Ensure direction is a string
                if not isinstance(direction, str):
                    direction = str(direction)
                
                # Standardize direction
                direction = standardize_direction(direction)
                
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO pmi_indices
                    (report_date, index_name, index_value, direction)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        report_date.isoformat(),
                        index_name,
                        index_value,
                        direction
                    )
                )
                logger.info(f"Inserted index data for {index_name}: {index_value} ({direction})")
            except Exception as e:
                logger.error(f"Error inserting pmi_indices data for {index_name}: {str(e)}")
        
        # Process industry_status data (unchanged)
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
                
                # Insert each industry
                for idx, industry in enumerate(industries):
                    if not industry or not isinstance(industry, str):
                        continue
                        
                    # Clean industry name
                    industry = clean_industry_name(industry)
                    if not industry:
                        continue
                        
                    try:
                        cursor.execute(
                            """
                            INSERT OR REPLACE INTO industry_status
                            (report_date, index_name, industry_name, status, category, rank)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                report_date.isoformat(),
                                index_name,
                                industry,
                                status,
                                category,
                                idx  # Use the order in the list as the rank
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error inserting industry_status data for {industry}: {str(e)}")
        
        conn.commit()
        logger.info(f"Successfully stored data for report {month_year} (type: {report_type}) in database")
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
            
def standardize_direction(direction):
    """Standardize direction terms."""
    direction = direction.lower()
    if direction in ['growing', 'growth', 'expanding', 'expansion', 'increasing']:
        return 'Growing'
    elif direction in ['contracting', 'contraction', 'declining', 'decreasing']:
        return 'Contracting'
    elif direction == 'slower':
        return 'Slowing'
    elif direction == 'faster':
        return 'Faster'
    return direction  # if None of the above apply

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
        "november", # also remove this artifact
        "categories"
    ]

    industry_lower = industry.lower()
    for artifact in artifacts:
        if artifact in industry_lower:
            return None

    # Remove common prefixes and suffixes
    industry = re.sub(r"^(the\s+|and\s+|november\s+|order\s+)", "", industry, flags=re.IGNORECASE)
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
    industry = re.sub(r"andprimarymetals", "Primary Metals", industry, flags=re.IGNORECASE)
    industry = re.sub(r"AndPrimary", "Primary", industry, flags=re.IGNORECASE)

    # Skip if starts with punctuation
    if re.match(r'^[,;:.]+', industry):
        return None

    # Skip if too short
    if len(industry) < 3:
        return None
    
    return industry

def standardize_direction(direction):
    """Standardize direction terms."""
    if not direction or not isinstance(direction, str):
        return 'Unknown'
        
    direction = direction.lower()
    if direction in ['growing', 'growth', 'expanding', 'expansion', 'increasing']:
        return 'Growing'
    elif direction in ['contracting', 'contraction', 'declining', 'decreasing']:
        return 'Contracting'
    elif direction in ['slower', 'slowing']:
        return 'Slowing'
    elif direction in ['faster']:
        return 'Faster'
    
    # Convert first letter to uppercase for other directions
    return direction.capitalize()

def clean_industry_name(industry: Optional[str]) -> Optional[str]: # Added type hints
    """Clean industry name to remove common artifacts, but NOT canonical parts like 'Products'."""
    if not industry or not isinstance(industry, str):
        return None

    cleaned = industry.strip()

    # Regex for artifacts (more specific to start/end of string or whole string matches)
    # These should target non-industry text often appearing in lists
    artifact_patterns = [
        r"^\s*in\s+(the\s+)?following\s+order\s*:?.*$",
        r"^\s*industries\s+reporting.*$",
        r"^\s*reporting\s+(?:growth|decline|contraction|expansion|increase|decrease|slower|faster).*$",
        r"^\s*are\s*:?\s*$",
        r"^\s*listed\s+in\s+order\s*:?.*$",
        r"^\s*\d+\.\s+",  # e.g., "1. "
        r"^\s*-\s*",      # e.g., "- "
        r"\s*\(\d+\)$",   # e.g., " (3)"
        # Common months that might be extracted as part of an industry list if parsing is poor
        r"^(january|february|march|april|may|june|july|august|september|october|november|december)\s*:?\s*$",
        r"^\s*categories\s*:?\s*$"
    ]

    for pattern in artifact_patterns:
        if re.match(pattern, cleaned, flags=re.IGNORECASE):
            logger.debug(f"Industry '{industry}' matched artifact pattern '{pattern}', cleaning to None.")
            return None # If it's clearly an artifact, discard

    # Remove common prefixes ONLY if they are followed by significant text
    cleaned = re.sub(r"^(the|and|only|of|in|is|are|november|order)\s+", "", cleaned, flags=re.IGNORECASE).strip()
    
    # DO NOT STRIP " Products" here as it's part of the canonical name.
    # industry = re.sub(r"(\s+products)$", "", industry, flags=re.IGNORECASE) # <-- REMOVED THIS LINE

    # Normalize internal whitespace (e.g., multiple spaces to one)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # Remove stray leading/trailing specific characters if they are isolated
    cleaned = re.sub(r"^[sS]\s+(?=\w)", "", cleaned) # "s Textile Mills" -> "Textile Mills"
    cleaned = re.sub(r"^[-—]\s+", "", cleaned)

    # Fix "andPrimary Metals" type issues if they occur before standardization
    # This should ideally be handled by better LLM output or more robust standardization
    cleaned = cleaned.replace("andPrimary", "Primary") # Example specific fix
    cleaned = cleaned.replace("AndPrimary", "Primary")

    if not cleaned or len(cleaned) < 3: # Check length AFTER cleaning
        logger.debug(f"Industry '{industry}' cleaned to too short ('{cleaned}'). Returning None.")
        return None
        
    non_industry_phrases = ["no change", "none reported", "not applicable", "none"]
    if cleaned.lower() in non_industry_phrases:
        logger.debug(f"Industry '{industry}' identified as non-industry phrase ('{cleaned}'). Returning None.")
        return None

    return cleaned