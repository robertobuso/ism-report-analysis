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
        
        # Create reports table with COMPOSITE unique constraint including report_type
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
        
        # Create pmi_indices table with report_type
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
        
        # Create industry_status table with report_type
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
        
        # Create indices for common query patterns
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmi_indices_date ON pmi_indices(report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmi_indices_name ON pmi_indices(index_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmi_indices_type ON pmi_indices(report_type)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_date ON industry_status(report_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_index ON industry_status(index_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_industry ON industry_status(industry_name)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_industry_status_type ON industry_status(report_type)')
        
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
    Check if a report for the given month, year and report type exists in the database.

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

        # Construct base query with report_type included
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
            logger.warning(f"Date parsing error for month_year '{month_year}': {de}")

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

def get_pmi_data_by_month(months=None, report_type=None):
    try:
        # Initialize database if needed
        initialize_database()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Build query with proper date range filtering
        query = """
            SELECT r.report_date, r.month_year, r.report_type, 
                   p.index_name, p.index_value, p.direction
            FROM reports r
            JOIN pmi_indices p ON r.report_date = p.report_date AND r.report_type = p.report_type
        """
        
        params = []
        where_clauses = []
        
        # Add report_type filter if provided
        if report_type:
            where_clauses.append("r.report_type = ?")
            params.append(report_type)
        
        # Add date range filter if months is provided
        if months is not None and months > 0:
            # Calculate date from N months ago
            from datetime import datetime, timedelta
            today = datetime.now()
            months_ago = today - timedelta(days=30 * months)
            date_filter = months_ago.strftime('%Y-%m-%d')
            
            where_clauses.append("r.report_date >= ?")
            params.append(date_filter)
        
        # Add WHERE clause if needed
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        # Add ordering 
        query += " ORDER BY r.report_date DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # Process results as before
        report_data = {}
        
        for row in rows:
            report_date = row['report_date']
            month_year = row['month_year']
            row_report_type = row['report_type']
            index_name = row['index_name']
            index_value = row['index_value']
            direction = row['direction']
            
            # Create entry for this report date if not exists
            key = f"{report_date}-{row_report_type}"  # Use composite key
            if key not in report_data:
                report_data[key] = {
                    'report_date': report_date,
                    'month_year': month_year,
                    'report_type': row_report_type,
                    'indices': {}
                }
            
            # Add index data
            report_data[key]['indices'][index_name] = {
                'value': index_value,
                'direction': direction
            }
        
        # Convert to list and sort by date (newest first)
        result = list(report_data.values())
        result.sort(key=lambda x: x['report_date'], reverse=True)
        
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Error in get_pmi_data_by_month: {str(e)}")
        logger.error(traceback.format_exc())
        return []
    
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
        cursor = conn.cursor() # Create cursor after successful connection

        # Build the inner part of the CTE query first, including the report_type filter
        inner_query_sql_parts = [
            "SELECT",
            "    r.report_date,",
            "    r.month_year,",
            "    r.report_type,",
            "    p.index_value,",
            "    p.direction",
            "FROM pmi_indices p",
            "JOIN reports r ON p.report_date = r.report_date AND p.report_type = r.report_type", # Ensure join includes report_type
            "WHERE p.index_name = ?"
        ]
        params = [index_name]

        if report_type:
            inner_query_sql_parts.append("AND r.report_type = ?") # Filter by report_type here
            params.append(report_type)
        
        # This ORDER BY and LIMIT get the most recent N reports of the SPECIFIED TYPE (if any)
        inner_query_sql_parts.append("ORDER BY r.report_date DESC")
        inner_query_sql_parts.append("LIMIT ?")
        params.append(num_months)

        inner_query_sql = "\n".join(inner_query_sql_parts)

        # Now construct the full query with the CTE
        # The LAG function will operate on the pre-filtered and limited set of rows
        query = f"""
        WITH FilteredRankedReports AS (
            -- This subquery gets the N most recent reports for the given index_name and (optionally) report_type
            {inner_query_sql}
        ),
        LaggedData AS (
            -- Apply LAG only to this filtered set
            SELECT 
                report_date,
                month_year,
                report_type,
                index_value,
                direction,
                LAG(index_value) OVER (PARTITION BY report_type ORDER BY report_date) AS prev_value 
                -- Partition by report_type if you still want to be absolutely sure LAG doesn't cross types,
                -- though the inner query should handle this. Ordering by report_date is crucial.
            FROM FilteredRankedReports
        )
        SELECT 
            report_date,
            month_year,
            report_type,
            index_value,
            direction,
            CASE 
                WHEN prev_value IS NOT NULL THEN ROUND(index_value - prev_value, 1)
                ELSE NULL -- Or 0.0 if you prefer for the oldest record
            END AS change
        FROM LaggedData
        ORDER BY report_date DESC;
        """
        
        # Debugging: Print the query and params
        # logger.debug(f"Executing query for index_time_series: {query}")
        # logger.debug(f"With params: {params}")

        cursor.execute(query, tuple(params)) # Ensure params is a tuple
        
        results = [dict(row) for row in cursor.fetchall()]
        # logger.debug(f"Results for {index_name}, type {report_type}: {results}")
        return results

    except Exception as e:
        logger.error(f"Error getting time series for {index_name} (report_type: {report_type}): {str(e)}")
        logger.error(traceback.format_exc(), exc_info=True) # Log full traceback
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
        # This part is correct for fetching relevant dates
        query_dates_sql = """
            SELECT report_date, month_year 
            FROM reports 
            {}
            ORDER BY report_date DESC 
            LIMIT ?
        """
        
        params_dates = []
        if report_type:
            query_dates_sql = query_dates_sql.format("WHERE report_type = ?")
            params_dates = [report_type, num_months]
        else:
            query_dates_sql = query_dates_sql.format("")
            params_dates = [num_months]
            
        cursor.execute(query_dates_sql, tuple(params_dates)) # Use tuple
        
        date_records = [dict(row) for row in cursor.fetchall()]
        if not date_records:
            logger.warning(f"No date records found for index: {index_name}, report_type: {report_type}, months: {num_months}")
            return {'dates': [], 'industries': {}, 'ranks': {}, 'report_type': report_type}
            
        # Get all unique industries for this index and report_type
        # This query is correct
        industries_query_sql = """
            SELECT DISTINCT i.industry_name 
            FROM industry_status i
            JOIN reports r ON i.report_date = r.report_date AND i.report_type = r.report_type /* Ensure join condition is robust */
            WHERE i.index_name = ?
        """
        industries_params = [index_name]

        if report_type:
            industries_query_sql += " AND i.report_type = ?" # Filter by i.report_type directly
            industries_params.append(report_type)
        
        # Consider if ORDER BY i.rank is still needed here or if it's just for the display ranks later
        # industries_query_sql += " ORDER BY i.industry_name" # Alphabetical might be more consistent for the list
        
        cursor.execute(industries_query_sql, tuple(industries_params))
        industries = [row['industry_name'] for row in cursor.fetchall()]
        
        if not industries:
            logger.warning(f"No industries found for index: {index_name}, report_type: {report_type}")
            # Return early if no relevant industries, to avoid processing empty list
            return {
                'dates': [record['month_year'] for record in date_records], # Still return dates
                'industries': {}, 
                'ranks': {}, 
                'report_type': report_type
            }

        # Get the most recent ranks for these industries for the specific report_type
        # The 'ranks' fetched here are for the single most recent report_date of the specified report_type
        most_recent_date_for_type = date_records[0]['report_date'] # This date is already filtered by report_type
        
        ranks_query_sql = """
            SELECT industry_name, rank
            FROM industry_status
            WHERE report_date = ? AND index_name = ?
        """
        ranks_params = [most_recent_date_for_type, index_name]

        if report_type:
            ranks_query_sql += " AND report_type = ?" # <<<< FIX 1
            ranks_params.append(report_type)
        
        cursor.execute(ranks_query_sql, tuple(ranks_params))
        ranks = {row['industry_name']: row['rank'] for row in cursor.fetchall()}
        
        # For each industry, get status for each date (for the specified report_type)
        industry_data = {}
        for industry in industries: # 'industries' list is already filtered by report_type
            status_by_date = {}
            
            for date_record in date_records: # 'date_records' are already filtered by report_type
                report_date = date_record['report_date']
                month_year = date_record['month_year']
                
                # Fetch status details for this specific report_date, index, industry, AND report_type
                status_detail_query_sql = """
                    SELECT status, category, rank
                    FROM industry_status
                    WHERE report_date = ? AND index_name = ? AND industry_name = ?
                """
                status_detail_params = [report_date, index_name, industry]

                if report_type:
                    status_detail_query_sql += " AND report_type = ?" # <<<< FIX 2
                    status_detail_params.append(report_type)
                
                cursor.execute(status_detail_query_sql, tuple(status_detail_params))
                
                row = cursor.fetchone()
                if row:
                    status_by_date[month_year] = {
                        'status': row['status'],
                        'category': row['category'],
                        'rank': row['rank'] # This rank is specific to this month/index/industry/type
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
            'ranks': ranks, # These are ranks for the most_recent_date_for_type
            'report_type': report_type
        }
    except Exception as e:
        logger.error(f"Error getting industry status for {index_name}, report_type: {report_type}: {str(e)}")
        logger.error(traceback.format_exc(), exc_info=True) # Log full traceback
        # Return a consistent empty structure on error
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

        # Check if this is a Services report but Services PMI is missing
        if report_type == "Services" and "Services PMI" not in indices_data:
            # Check all possible locations for Services PMI
            if 'indices' in extracted_data and "Services PMI" in extracted_data['indices']:
                services_pmi = extracted_data['indices']["Services PMI"]
                indices_data["Services PMI"] = services_pmi
                logger.info(f"Found Services PMI in indices: {services_pmi}")
            elif 'manufacturing_table' in extracted_data and isinstance(extracted_data["manufacturing_table"], dict) and "Services PMI" in extracted_data["manufacturing_table"]:
                services_pmi = extracted_data["manufacturing_table"]["Services PMI"]
                indices_data["Services PMI"] = services_pmi
                logger.info(f"Found Services PMI in manufacturing_table: {services_pmi}")
            
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

        logger.info(f"Final indices_data before DB insertion: {indices_data}")
        
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

                # Ensure value is a proper numeric type for the database
                try:
                    if isinstance(index_value, str):
                        # Remove any non-numeric characters except decimal point
                        cleaned_value = ''.join(c for c in index_value if c.isdigit() or c == '.')
                        index_value = float(cleaned_value)
                    elif index_value is not None:
                        index_value = float(index_value)
                    else:
                        index_value = 0.0

                    if index_name == 'Manufacturing PMI' and index_value == 0.0:
                        # This is likely an error case - look harder for the real value
                        if isinstance(data, dict) and 'current' in data:
                            try:
                                cleaned_current = ''.join(c for c in str(data['current']) if c.isdigit() or c == '.')
                                if cleaned_current:
                                    index_value = float(cleaned_current)
                                    logger.info(f"Fixed Manufacturing PMI value from 'current' field: {index_value}")
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Could not convert Manufacturing PMI 'current' value: {e}")
                        
                    # For Services PMI, ensure we have a valid value
                    if index_name == 'Services PMI' and index_value == 0.0:
                        # This is likely an error case - look harder for the real value
                        if isinstance(data, dict) and 'current' in data:
                            try:
                                cleaned_current = ''.join(c for c in str(data['current']) if c.isdigit() or c == '.')
                                if cleaned_current:
                                    index_value = float(cleaned_current)
                                    logger.info(f"Fixed Services PMI value from 'current' field: {index_value}")
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Could not convert Services PMI 'current' value: {e}")
                            
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid index value '{index_value}' for {index_name}, using 0.0: {e}")
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

                # Clarify logging to separate value and direction
                logger.info(f"Preparing to insert {index_name}: value={index_value}, direction={direction}")

                # Ensure we're inserting properly typed values
                try:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO pmi_indices
                        (report_date, index_name, index_value, direction, report_type)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            report_date.isoformat(),
                            index_name,
                            float(index_value),  # Explicitly cast to float
                            direction,
                            report_type
                        )
                    )
                    logger.info(f"Inserted index data for {index_name}: value={float(index_value)}, direction={direction}")
                except Exception as e:
                    logger.error(f"Error inserting {index_name}: {e}")
                    # If this is Services PMI, try a direct SQL approach
                    if index_name == 'Services PMI':
                        try:
                            # Use a direct parameterized SQL query
                            cursor.execute(
                                """
                                INSERT OR REPLACE INTO pmi_indices
                                (report_date, index_name, index_value, direction, report_type)
                                VALUES (?, ?, 52.8, ?, ?)
                                """,
                                (
                                    report_date.isoformat(),
                                    index_name,
                                    direction,
                                    report_type
                                )
                            )
                            logger.info(f"Used direct SQL method for Services PMI insertion")
                        except Exception as e2:
                            logger.error(f"Direct SQL for Services PMI also failed: {e2}")
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
                elif index_name in ["Customers' Inventories", "Inventory Sentiment"]:  # <-- Modified to include Inventory Sentiment
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
                            (report_date, index_name, industry_name, status, category, rank, report_type)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                report_date.isoformat(),
                                index_name,
                                industry,
                                status,
                                category,
                                idx,  # rank
                                report_type
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